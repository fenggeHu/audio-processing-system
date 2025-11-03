"""
Comprehensive fault tolerance coordinator for audio processing system.

This module integrates error handling, classroom failsafe management,
and multi-level service degradation strategies.
"""

import asyncio
import time
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
import structlog

from .error_handler import ErrorHandler, ErrorSeverity, RecoveryAction
from .classroom_failsafe import ClassroomFailsafeManager, OperationMode, FailsafeConfig
from .interfaces import IEventHandler
from .models import AudioConfig
from .exceptions import ServiceError

logger = structlog.get_logger(__name__)


class SystemHealthLevel(Enum):
    """Overall system health levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class FaultToleranceCoordinator(IEventHandler):
    """
    Main coordinator for fault tolerance and error recovery.
    
    Integrates error handling, classroom failsafe management,
    and provides unified fault tolerance strategies.
    """
    
    def __init__(self, audio_config: AudioConfig, failsafe_config: FailsafeConfig):
        self._audio_config = audio_config
        self._error_handler = ErrorHandler()
        self._failsafe_manager = ClassroomFailsafeManager(failsafe_config, audio_config)
        
        self._system_health = SystemHealthLevel.HEALTHY
        self._service_manager: Optional[Any] = None
        self._health_monitors: Dict[str, Callable] = {}
        self._recovery_in_progress = False
        
        # Setup integration between components
        self._setup_integration()
        
        logger.info("Fault tolerance coordinator initialized")
    
    def _setup_integration(self) -> None:
        """Setup integration between error handler and failsafe manager."""
        # Connect failsafe manager to error handler
        self._failsafe_manager.set_error_handler(self._error_handler)
        
        # Register this coordinator as event handler for both components
        # This would be done through an event bus in a real implementation
    
    def set_service_manager(self, service_manager: Any) -> None:
        """Set service manager reference."""
        self._service_manager = service_manager
        self._failsafe_manager.set_service_manager(service_manager)
    
    async def initialize(self) -> None:
        """Initialize the fault tolerance system."""
        logger.info("Initializing fault tolerance system")
        
        # Setup default recovery strategies
        await self._setup_recovery_strategies()
        
        # Start health monitoring
        await self._start_health_monitoring()
        
        logger.info("Fault tolerance system initialized successfully")
    
    async def shutdown(self) -> None:
        """Shutdown the fault tolerance system."""
        logger.info("Shutting down fault tolerance system")
        
        # Stop health monitoring
        await self._stop_health_monitoring()
        
        logger.info("Fault tolerance system shutdown complete")  
  async def handle_system_error(self, error: Exception, service_name: str,
                                 metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Handle system-wide error with coordinated response.
        
        Args:
            error: Exception that occurred
            service_name: Service where error occurred
            metadata: Additional error context
            
        Returns:
            True if error was handled successfully
        """
        logger.error(
            "System error detected",
            service=service_name,
            error_type=type(error).__name__,
            error_message=str(error)
        )
        
        # Update system health based on error severity
        await self._update_system_health(error, service_name)
        
        # Handle through error handler first
        error_handled = await self._error_handler.handle_error(error, service_name, metadata)
        
        # If error handler couldn't resolve, escalate to failsafe manager
        if not error_handled or self._system_health in [SystemHealthLevel.CRITICAL, SystemHealthLevel.EMERGENCY]:
            failsafe_action = await self._failsafe_manager.handle_service_failure(
                service_name, str(error)
            )
            
            logger.info(
                "Escalated to failsafe manager",
                service=service_name,
                action=failsafe_action.value
            )
        
        return True
    
    async def trigger_emergency_procedures(self, reason: str) -> None:
        """
        Trigger emergency procedures across the system.
        
        Args:
            reason: Reason for emergency activation
        """
        logger.critical("Emergency procedures triggered", reason=reason)
        
        self._system_health = SystemHealthLevel.EMERGENCY
        
        # Immediate volume reduction
        await self._failsafe_manager.emergency_volume_reduction()
        
        # Switch to emergency mode
        await self._failsafe_manager.switch_operation_mode(
            OperationMode.EMERGENCY_MODE, f"Emergency: {reason}"
        )
        
        # Emit emergency event
        await self._emit_event("emergency_activated", {
            "reason": reason,
            "timestamp": time.time()
        })
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        error_stats = self._error_handler.get_error_statistics()
        failsafe_status = self._failsafe_manager.get_system_status()
        
        return {
            "system_health": self._system_health.value,
            "recovery_in_progress": self._recovery_in_progress,
            "error_statistics": error_stats,
            "failsafe_status": failsafe_status,
            "timestamp": time.time()
        }
    
    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Handle system events (implements IEventHandler)."""
        if event_type == "service_error":
            service_name = event_data.get("service_name", "unknown")
            error_message = event_data.get("error", "Unknown error")
            
            # Create synthetic error for handling
            error = ServiceError(error_message, service_name)
            await self.handle_system_error(error, service_name, event_data)
        
        elif event_type == "system_overload":
            # Handle system overload by degrading services
            await self._handle_system_overload(event_data)
        
        elif event_type == "feedback_detected":
            # Immediate emergency response for feedback
            await self.trigger_emergency_procedures("Audio feedback detected")
    
    def get_supported_events(self) -> List[str]:
        """Get supported event types."""
        return [
            "service_error", "system_overload", "feedback_detected",
            "emergency_activated", "recovery_completed"
        ]
    
    async def _setup_recovery_strategies(self) -> None:
        """Setup coordinated recovery strategies."""
        # This integrates the error handler and failsafe manager strategies
        logger.debug("Setting up recovery strategies")
        
        # Add custom recovery strategies that coordinate between components
        from .error_handler import RecoveryStrategy
        
        # Critical device errors - immediate failsafe response
        critical_strategy = RecoveryStrategy(
            error_types=["DeviceError", "DependencyError"],
            action=RecoveryAction.EMERGENCY_STOP,
            max_attempts=1,
            custom_handler=self._handle_critical_error
        )
        self._error_handler.add_recovery_strategy(critical_strategy)
    
    async def _handle_critical_error(self, context) -> bool:
        """Handle critical errors with immediate failsafe response."""
        logger.critical(
            "Critical error - activating emergency procedures",
            service=context.service_name,
            error=context.error_message
        )
        
        await self.trigger_emergency_procedures(
            f"Critical error in {context.service_name}: {context.error_message}"
        )
        
        return True
    
    async def _update_system_health(self, error: Exception, service_name: str) -> None:
        """Update overall system health based on error."""
        from .exceptions import DeviceError, DependencyError, ServiceError
        
        if isinstance(error, (DeviceError, DependencyError)):
            self._system_health = SystemHealthLevel.EMERGENCY
        elif isinstance(error, ServiceError) and service_name in ["CaptureService", "AECService"]:
            self._system_health = SystemHealthLevel.CRITICAL
        elif self._system_health == SystemHealthLevel.HEALTHY:
            self._system_health = SystemHealthLevel.DEGRADED
        
        logger.info("System health updated", health=self._system_health.value)
    
    async def _start_health_monitoring(self) -> None:
        """Start system health monitoring."""
        logger.debug("Starting health monitoring")
        # Implementation would start background monitoring tasks
    
    async def _stop_health_monitoring(self) -> None:
        """Stop system health monitoring."""
        logger.debug("Stopping health monitoring")
        # Implementation would stop background monitoring tasks
    
    async def _handle_system_overload(self, event_data: Dict[str, Any]) -> None:
        """Handle system overload by degrading services."""
        cpu_usage = event_data.get("cpu_usage", 0)
        memory_usage = event_data.get("memory_usage", 0)
        
        logger.warning(
            "System overload detected",
            cpu_usage=cpu_usage,
            memory_usage=memory_usage
        )
        
        # Degrade to simpler processing mode
        await self._failsafe_manager.switch_operation_mode(
            OperationMode.SIMPLE_AGC, "System overload"
        )
    
    async def _emit_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Emit system event."""
        # This would integrate with the system event bus
        logger.info("Event emitted", event_type=event_type, data=event_data)