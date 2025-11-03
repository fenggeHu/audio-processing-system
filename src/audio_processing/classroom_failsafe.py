"""
Classroom-specific failsafe and fault tolerance manager.

This module provides specialized fault tolerance mechanisms for
classroom audio processing scenarios, including emergency procedures,
service degradation, and automatic recovery strategies.
"""

import asyncio
import time
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
from dataclasses import dataclass
import structlog

from .interfaces import IEventHandler, IAudioService
from .error_handler import ErrorHandler, ErrorContext, RecoveryAction
from .exceptions import ServiceError, DeviceError
from .models import AudioConfig

logger = structlog.get_logger(__name__)


class OperationMode(Enum):
    """Classroom operation modes."""
    FULL_SYSTEM = "full_system"          # All features enabled
    BASIC_AEC = "basic_aec"              # Basic echo cancellation only
    SIMPLE_AGC = "simple_agc"            # Simple gain control only
    BYPASS_MODE = "bypass_mode"          # Direct audio passthrough
    EMERGENCY_MODE = "emergency_mode"    # Emergency safe mode


class ClassroomZone(Enum):
    """Classroom audio zones."""
    TEACHER_AREA = "teacher_area"        # Lectern/front area
    STUDENT_AREA = "student_area"        # Student seating area
    FULL_COVERAGE = "full_coverage"      # Entire classroom


@dataclass
class FailsafeConfig:
    """Configuration for failsafe operations."""
    emergency_volume_reduction_db: float = 10.0
    max_feedback_threshold_dbfs: float = -6.0
    service_restart_timeout_s: float = 30.0
    degradation_timeout_s: float = 300.0  # 5 minutes
    auto_recovery_enabled: bool = True
    emergency_contact_enabled: bool = False


class ClassroomFailsafeManager(IEventHandler):
    """
    Specialized failsafe manager for classroom audio processing.
    
    Provides classroom-specific fault tolerance including:
    - Emergency volume control to prevent feedback
    - Service degradation strategies for teaching continuity
    - Automatic recovery with minimal disruption
    - Zone-based audio management
    """
    
    def __init__(self, config: FailsafeConfig, audio_config: AudioConfig):
        self._config = config
        self._audio_config = audio_config
        self._current_mode = OperationMode.FULL_SYSTEM
        self._previous_mode = OperationMode.FULL_SYSTEM
        self._degradation_start_time: Optional[float] = None
        self._emergency_active = False
        
        # Service references (will be injected)
        self._services: Dict[str, IAudioService] = {}
        self._service_manager: Optional[Any] = None
        self._error_handler: Optional[ErrorHandler] = None
        
        # Failsafe state
        self._failed_services: List[str] = []
        self._recovery_tasks: Dict[str, asyncio.Task] = {}
        self._emergency_callbacks: List[Callable] = []
        
        # Audio safety parameters
        self._original_volumes: Dict[str, float] = {}
        self._current_beam_direction = ClassroomZone.FULL_COVERAGE
        self._feedback_detection_active = True
        
        logger.info("Classroom failsafe manager initialized", mode=self._current_mode.value)
    
    def set_service_manager(self, service_manager: Any) -> None:
        """Set reference to service manager."""
        self._service_manager = service_manager
    
    def set_error_handler(self, error_handler: ErrorHandler) -> None:
        """Set reference to error handler."""
        self._error_handler = error_handler
        
        # Register recovery callbacks
        error_handler.register_recovery_callback(
            RecoveryAction.RESTART_SERVICE, self._handle_service_restart
        )
        error_handler.register_recovery_callback(
            RecoveryAction.DEGRADE_SERVICE, self._handle_service_degradation
        )
        error_handler.register_recovery_callback(
            RecoveryAction.FAILOVER, self._handle_service_failover
        )
        error_handler.register_recovery_callback(
            RecoveryAction.EMERGENCY_STOP, self._handle_emergency_stop
        )
    
    def register_service(self, name: str, service: IAudioService) -> None:
        """Register service for failsafe management."""
        self._services[name] = service
        logger.debug("Service registered for failsafe", service=name)
    
    def add_emergency_callback(self, callback: Callable[[], None]) -> None:
        """Add callback to be executed during emergency procedures."""
        self._emergency_callbacks.append(callback)
    
    async def handle_service_failure(self, service_name: str, 
                                   failure_reason: str) -> RecoveryAction:
        """
        Handle service failure with classroom-specific strategies.
        
        Args:
            service_name: Name of failed service
            failure_reason: Reason for failure
            
        Returns:
            Recovery action taken
        """
        logger.warning(
            "Handling service failure",
            service=service_name,
            reason=failure_reason,
            current_mode=self._current_mode.value
        )
        
        self._failed_services.append(service_name)
        
        # Determine recovery strategy based on service type
        if service_name == "AECService":
            return await self._handle_aec_failure()
        elif service_name == "SSLService":
            return await self._handle_ssl_failure()
        elif service_name == "BeamformerService":
            return await self._handle_beamformer_failure()
        elif service_name == "AGCService":
            return await self._handle_agc_failure()
        elif service_name == "CaptureService":
            return await self._handle_capture_failure()
        else:
            # Generic service failure
            return await self._handle_generic_failure(service_name)
    
    async def switch_operation_mode(self, mode: OperationMode, 
                                  reason: str = "Manual switch") -> bool:
        """
        Switch classroom operation mode.
        
        Args:
            mode: Target operation mode
            reason: Reason for mode switch
            
        Returns:
            True if switch was successful
        """
        if mode == self._current_mode:
            logger.info("Already in target mode", mode=mode.value)
            return True
        
        logger.info(
            "Switching operation mode",
            from_mode=self._current_mode.value,
            to_mode=mode.value,
            reason=reason
        )
        
        self._previous_mode = self._current_mode
        
        try:
            success = await self._execute_mode_switch(mode)
            
            if success:
                self._current_mode = mode
                
                # Track degradation time
                if mode != OperationMode.FULL_SYSTEM:
                    self._degradation_start_time = time.time()
                else:
                    self._degradation_start_time = None
                
                # Start auto-recovery if enabled and in degraded mode
                if (self._config.auto_recovery_enabled and 
                    mode != OperationMode.FULL_SYSTEM and
                    mode != OperationMode.EMERGENCY_MODE):
                    await self._schedule_auto_recovery()
                
                logger.info("Operation mode switched successfully", mode=mode.value)
                return True
            else:
                # Revert to previous mode
                self._current_mode = self._previous_mode
                logger.error("Failed to switch operation mode", target_mode=mode.value)
                return False
                
        except Exception as e:
            self._current_mode = self._previous_mode
            logger.error("Error switching operation mode", error=str(e))
            return False
    
    async def emergency_volume_reduction(self, reduction_db: Optional[float] = None) -> None:
        """
        Immediately reduce speaker volume to prevent feedback.
        
        Args:
            reduction_db: Volume reduction in dB (uses config default if None)
        """
        reduction = reduction_db or self._config.emergency_volume_reduction_db
        
        logger.critical(
            "Emergency volume reduction activated",
            reduction_db=reduction
        )
        
        # Store original volumes if not already stored
        if not self._original_volumes:
            # This would interface with the actual audio output services
            # For now, we'll simulate storing current volumes
            self._original_volumes = {
                "main_speakers": 0.0,  # Assume 0dB as current
                "monitor_speakers": -6.0
            }
        
        # Apply volume reduction
        try:
            await self._apply_volume_reduction(reduction)
            self._emergency_active = True
            
            # Execute emergency callbacks
            for callback in self._emergency_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error("Emergency callback failed", error=str(e))
            
            logger.info("Emergency volume reduction applied successfully")
            
        except Exception as e:
            logger.error("Failed to apply emergency volume reduction", error=str(e))
            raise ServiceError(f"Emergency volume reduction failed: {e}")
    
    async def restore_normal_volume(self) -> None:
        """Restore normal speaker volumes after emergency."""
        if not self._emergency_active or not self._original_volumes:
            logger.warning("No emergency volume reduction to restore")
            return
        
        logger.info("Restoring normal speaker volumes")
        
        try:
            await self._apply_volume_restoration()
            self._emergency_active = False
            self._original_volumes.clear()
            
            logger.info("Normal speaker volumes restored")
            
        except Exception as e:
            logger.error("Failed to restore normal volumes", error=str(e))
            raise ServiceError(f"Volume restoration failed: {e}")
    
    async def set_beam_direction(self, zone: ClassroomZone) -> None:
        """
        Set microphone beam direction for classroom zone.
        
        Args:
            zone: Target classroom zone
        """
        logger.info(
            "Setting beam direction",
            from_zone=self._current_beam_direction.value,
            to_zone=zone.value
        )
        
        self._current_beam_direction = zone
        
        # This would interface with the BeamformerService
        # For now, we'll simulate the beam direction change
        if "BeamformerService" in self._services:
            try:
                beamformer = self._services["BeamformerService"]
                # Would call beamformer.set_target_zone(zone) or similar
                logger.debug("Beam direction updated", zone=zone.value)
            except Exception as e:
                logger.error("Failed to update beam direction", error=str(e))
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        Get current failsafe system status.
        
        Returns:
            Dictionary with system status information
        """
        degradation_duration = None
        if self._degradation_start_time:
            degradation_duration = time.time() - self._degradation_start_time
        
        return {
            "operation_mode": self._current_mode.value,
            "previous_mode": self._previous_mode.value,
            "emergency_active": self._emergency_active,
            "failed_services": self._failed_services.copy(),
            "degradation_duration_s": degradation_duration,
            "beam_direction": self._current_beam_direction.value,
            "recovery_tasks_active": len(self._recovery_tasks),
            "auto_recovery_enabled": self._config.auto_recovery_enabled
        }
    
    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Handle system events (implements IEventHandler)."""
        if event_type == "service_error":
            service_name = event_data.get("service_name")
            error = event_data.get("error", "Unknown error")
            
            if service_name:
                await self.handle_service_failure(service_name, error)
        
        elif event_type == "feedback_detected":
            # Handle audio feedback detection
            await self._handle_feedback_detection(event_data)
        
        elif event_type == "service_recovered":
            service_name = event_data.get("service_name")
            if service_name in self._failed_services:
                self._failed_services.remove(service_name)
                await self._check_full_recovery()
    
    def get_supported_events(self) -> List[str]:
        """Get supported event types."""
        return ["service_error", "feedback_detected", "service_recovered"]
    
    # Recovery callback implementations
    
    async def _handle_service_restart(self, context: ErrorContext) -> bool:
        """Handle service restart recovery action."""
        service_name = context.service_name
        
        logger.info("Attempting service restart", service=service_name)
        
        if not self._service_manager:
            logger.error("No service manager available for restart")
            return False
        
        try:
            await self._service_manager.restart_service(service_name)
            
            # Remove from failed services list
            if service_name in self._failed_services:
                self._failed_services.remove(service_name)
            
            return True
            
        except Exception as e:
            logger.error("Service restart failed", service=service_name, error=str(e))
            return False
    
    async def _handle_service_degradation(self, context: ErrorContext) -> bool:
        """Handle service degradation recovery action."""
        service_name = context.service_name
        
        logger.info("Degrading service", service=service_name)
        
        # Determine appropriate degradation mode
        if service_name == "AECService":
            return await self.switch_operation_mode(
                OperationMode.BASIC_AEC, f"AEC service degradation: {context.error_message}"
            )
        elif service_name in ["SSLService", "BeamformerService"]:
            return await self.switch_operation_mode(
                OperationMode.SIMPLE_AGC, f"Spatial processing degradation: {context.error_message}"
            )
        else:
            return await self.switch_operation_mode(
                OperationMode.BYPASS_MODE, f"Service degradation: {context.error_message}"
            )
    
    async def _handle_service_failover(self, context: ErrorContext) -> bool:
        """Handle service failover recovery action."""
        service_name = context.service_name
        
        logger.info("Attempting service failover", service=service_name)
        
        # Implement failover logic based on service type
        if service_name == "CaptureService":
            # Switch to single microphone mode
            await self._switch_to_single_mic_mode()
            return True
        elif service_name == "BeamformerService":
            # Switch to fixed beam direction
            await self.set_beam_direction(ClassroomZone.TEACHER_AREA)
            return True
        else:
            # Generic failover - switch to bypass mode
            return await self.switch_operation_mode(
                OperationMode.BYPASS_MODE, f"Service failover: {context.error_message}"
            )
    
    async def _handle_emergency_stop(self, context: ErrorContext) -> bool:
        """Handle emergency stop recovery action."""
        logger.critical("Executing emergency stop", reason=context.error_message)
        
        # Immediate volume reduction
        await self.emergency_volume_reduction()
        
        # Switch to emergency mode
        await self.switch_operation_mode(
            OperationMode.EMERGENCY_MODE, f"Emergency stop: {context.error_message}"
        )
        
        return True
    
    # Service-specific failure handlers
    
    async def _handle_aec_failure(self) -> RecoveryAction:
        """Handle AEC service failure."""
        logger.warning("AEC service failed - preventing feedback")
        
        # Immediate volume reduction to prevent feedback
        await self.emergency_volume_reduction()
        
        # Switch to basic AEC mode or bypass
        await self.switch_operation_mode(
            OperationMode.BASIC_AEC, "AEC service failure"
        )
        
        return RecoveryAction.DEGRADE_SERVICE
    
    async def _handle_ssl_failure(self) -> RecoveryAction:
        """Handle SSL service failure."""
        logger.warning("SSL service failed - switching to fixed beam")
        
        # Set fixed beam direction to teacher area
        await self.set_beam_direction(ClassroomZone.TEACHER_AREA)
        
        return RecoveryAction.FAILOVER
    
    async def _handle_beamformer_failure(self) -> RecoveryAction:
        """Handle beamformer service failure."""
        logger.warning("Beamformer failed - switching to single mic")
        
        await self._switch_to_single_mic_mode()
        
        return RecoveryAction.FAILOVER
    
    async def _handle_agc_failure(self) -> RecoveryAction:
        """Handle AGC service failure."""
        logger.warning("AGC service failed - manual gain control")
        
        # Switch to simple AGC mode
        await self.switch_operation_mode(
            OperationMode.SIMPLE_AGC, "AGC service failure"
        )
        
        return RecoveryAction.DEGRADE_SERVICE
    
    async def _handle_capture_failure(self) -> RecoveryAction:
        """Handle capture service failure."""
        logger.critical("Capture service failed - critical failure")
        
        # This is critical - try emergency restart
        if self._service_manager:
            try:
                await self._service_manager.restart_service("CaptureService")
                return RecoveryAction.RESTART_SERVICE
            except Exception:
                pass
        
        # If restart fails, emergency stop
        await self.switch_operation_mode(
            OperationMode.EMERGENCY_MODE, "Capture service failure"
        )
        
        return RecoveryAction.EMERGENCY_STOP
    
    async def _handle_generic_failure(self, service_name: str) -> RecoveryAction:
        """Handle generic service failure."""
        logger.warning("Generic service failure", service=service_name)
        
        # Try restart first
        if self._service_manager:
            try:
                await self._service_manager.restart_service(service_name)
                return RecoveryAction.RESTART_SERVICE
            except Exception:
                pass
        
        # If restart fails, degrade
        return RecoveryAction.DEGRADE_SERVICE
    
    # Mode switching implementation
    
    async def _execute_mode_switch(self, mode: OperationMode) -> bool:
        """Execute the actual mode switch."""
        try:
            if mode == OperationMode.FULL_SYSTEM:
                return await self._switch_to_full_system()
            elif mode == OperationMode.BASIC_AEC:
                return await self._switch_to_basic_aec()
            elif mode == OperationMode.SIMPLE_AGC:
                return await self._switch_to_simple_agc()
            elif mode == OperationMode.BYPASS_MODE:
                return await self._switch_to_bypass_mode()
            elif mode == OperationMode.EMERGENCY_MODE:
                return await self._switch_to_emergency_mode()
            else:
                logger.error("Unknown operation mode", mode=mode.value)
                return False
                
        except Exception as e:
            logger.error("Mode switch execution failed", mode=mode.value, error=str(e))
            return False
    
    async def _switch_to_full_system(self) -> bool:
        """Switch to full system mode."""
        logger.info("Switching to full system mode")
        
        # Restore all services to full functionality
        # This would involve reconfiguring services to their optimal settings
        
        # Restore normal volume if emergency was active
        if self._emergency_active:
            await self.restore_normal_volume()
        
        return True
    
    async def _switch_to_basic_aec(self) -> bool:
        """Switch to basic AEC mode."""
        logger.info("Switching to basic AEC mode")
        
        # Configure services for basic echo cancellation only
        # Disable advanced features like SSL, beamforming
        
        return True
    
    async def _switch_to_simple_agc(self) -> bool:
        """Switch to simple AGC mode."""
        logger.info("Switching to simple AGC mode")
        
        # Configure for basic gain control only
        # Disable echo cancellation, spatial processing
        
        return True
    
    async def _switch_to_bypass_mode(self) -> bool:
        """Switch to bypass mode."""
        logger.info("Switching to bypass mode")
        
        # Direct audio passthrough with minimal processing
        
        return True
    
    async def _switch_to_emergency_mode(self) -> bool:
        """Switch to emergency mode."""
        logger.critical("Switching to emergency mode")
        
        # Emergency volume reduction
        await self.emergency_volume_reduction()
        
        # Minimal processing, maximum safety
        
        return True
    
    # Helper methods
    
    async def _apply_volume_reduction(self, reduction_db: float) -> None:
        """Apply volume reduction to speakers."""
        # This would interface with actual audio output services
        logger.info("Applying volume reduction", reduction_db=reduction_db)
        
        # Simulate volume reduction
        await asyncio.sleep(0.1)  # Simulate processing time
    
    async def _apply_volume_restoration(self) -> None:
        """Restore original speaker volumes."""
        # This would interface with actual audio output services
        logger.info("Restoring original volumes", volumes=self._original_volumes)
        
        # Simulate volume restoration
        await asyncio.sleep(0.1)  # Simulate processing time
    
    async def _switch_to_single_mic_mode(self) -> None:
        """Switch to single microphone mode."""
        logger.info("Switching to single microphone mode")
        
        # This would reconfigure the capture service to use only one microphone
        # and disable array processing
    
    async def _handle_feedback_detection(self, event_data: Dict[str, Any]) -> None:
        """Handle audio feedback detection."""
        frequency = event_data.get("frequency", 0)
        level_dbfs = event_data.get("level_dbfs", 0)
        
        logger.warning(
            "Audio feedback detected",
            frequency=frequency,
            level_dbfs=level_dbfs
        )
        
        if level_dbfs > self._config.max_feedback_threshold_dbfs:
            # Emergency volume reduction
            await self.emergency_volume_reduction()
    
    async def _schedule_auto_recovery(self) -> None:
        """Schedule automatic recovery to full system mode."""
        if not self._config.auto_recovery_enabled:
            return
        
        recovery_delay = self._config.degradation_timeout_s
        
        logger.info("Scheduling auto-recovery", delay_s=recovery_delay)
        
        async def recovery_task():
            await asyncio.sleep(recovery_delay)
            
            # Check if we're still in degraded mode
            if self._current_mode != OperationMode.FULL_SYSTEM:
                logger.info("Attempting auto-recovery to full system")
                
                success = await self.switch_operation_mode(
                    OperationMode.FULL_SYSTEM, "Automatic recovery"
                )
                
                if success:
                    logger.info("Auto-recovery successful")
                else:
                    logger.warning("Auto-recovery failed")
        
        # Cancel any existing recovery task
        if "auto_recovery" in self._recovery_tasks:
            self._recovery_tasks["auto_recovery"].cancel()
        
        # Start new recovery task
        self._recovery_tasks["auto_recovery"] = asyncio.create_task(recovery_task())
    
    async def _check_full_recovery(self) -> None:
        """Check if all services have recovered and switch back to full mode."""
        if not self._failed_services and self._current_mode != OperationMode.FULL_SYSTEM:
            logger.info("All services recovered - switching to full system")
            
            await self.switch_operation_mode(
                OperationMode.FULL_SYSTEM, "All services recovered"
            )