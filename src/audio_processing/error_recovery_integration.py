"""
Integration module for error handling and fault tolerance system.

This module provides a unified interface for integrating error handling,
fault tolerance, and recovery mechanisms into the audio processing system.
"""

import asyncio
from typing import Dict, Any, Optional, List
import structlog

from .fault_tolerance import FaultToleranceCoordinator, SystemHealthLevel
from .error_handler import ErrorHandler, ErrorSeverity, RecoveryAction
from .classroom_failsafe import ClassroomFailsafeManager, OperationMode, FailsafeConfig
from .retry_mechanism import AutoRecoveryManager, RetryConfig, RetryStrategy
from .interfaces import IEventHandler
from .models import AudioConfig
from .exceptions import ServiceError

logger = structlog.get_logger(__name__)


class ErrorRecoverySystem(IEventHandler):
    """
    Unified error recovery system for audio processing.
    
    Integrates all error handling, fault tolerance, and recovery
    mechanisms into a single, coordinated system.
    """
    
    def __init__(self, audio_config: AudioConfig, 
                 failsafe_config: Optional[FailsafeConfig] = None):
        self._audio_config = audio_config
        self._failsafe_config = failsafe_config or FailsafeConfig()
        
        # Initialize core components
        self._fault_coordinator = FaultToleranceCoordinator(
            audio_config, self._failsafe_config
        )
        self._auto_recovery = AutoRecoveryManager()
        
        # System state
        self._is_initialized = False
        self._service_manager: Optional[Any] = None
        self._registered_services: Dict[str, Any] = {}
        
        logger.info("Error recovery system created")
    
    async def initialize(self, service_manager: Any) -> None:
        """
        Initialize the error recovery system.
        
        Args:
            service_manager: Reference to the service manager
        """
        if self._is_initialized:
            logger.warning("Error recovery system already initialized")
            return
        
        logger.info("Initializing error recovery system")
        
        self._service_manager = service_manager
        
        # Initialize fault tolerance coordinator
        self._fault_coordinator.set_service_manager(service_manager)
        await self._fault_coordinator.initialize()
        
        # Setup default retry configurations for different service types
        await self._setup_default_retry_configs()
        
        # Register system event handlers
        await self._register_event_handlers()
        
        self._is_initialized = True
        
        logger.info("Error recovery system initialized successfully")
    
    async def shutdown(self) -> None:
        """Shutdown the error recovery system."""
        if not self._is_initialized:
            return
        
        logger.info("Shutting down error recovery system")
        
        # Stop all monitoring
        for service_name in self._registered_services.keys():
            await self._auto_recovery.stop_monitoring(service_name)
        
        # Shutdown fault coordinator
        await self._fault_coordinator.shutdown()
        
        self._is_initialized = False
        
        logger.info("Error recovery system shutdown complete")
    
    def register_service(self, service_name: str, service: Any,
                        custom_retry_config: Optional[RetryConfig] = None) -> None:
        """
        Register a service for error recovery monitoring.
        
        Args:
            service_name: Name of the service
            service: Service instance
            custom_retry_config: Custom retry configuration
        """
        if not self._is_initialized:
            raise ServiceError("Error recovery system not initialized")
        
        logger.info("Registering service for error recovery", service=service_name)
        
        # Store service reference
        self._registered_services[service_name] = service
        
        # Get retry config for service type
        retry_config = custom_retry_config or self._get_retry_config_for_service(service_name)
        
        # Register with auto-recovery manager
        self._auto_recovery.register_service(
            service_name, service, retry_config,
            recovery_strategy=self._create_recovery_strategy(service_name)
        )
        
        # Register with failsafe manager
        failsafe_manager = self._fault_coordinator._failsafe_manager
        failsafe_manager.register_service(service_name, service)
        
        logger.debug("Service registered successfully", service=service_name)
    
    async def start_monitoring(self, service_name: str) -> None:
        """
        Start error recovery monitoring for a service.
        
        Args:
            service_name: Name of service to monitor
        """
        if service_name not in self._registered_services:
            raise ServiceError(f"Service {service_name} not registered")
        
        await self._auto_recovery.start_monitoring(service_name)
        
        logger.info("Error recovery monitoring started", service=service_name)
    
    async def stop_monitoring(self, service_name: str) -> None:
        """
        Stop error recovery monitoring for a service.
        
        Args:
            service_name: Name of service to stop monitoring
        """
        await self._auto_recovery.stop_monitoring(service_name)
        
        logger.info("Error recovery monitoring stopped", service=service_name)
    
    async def handle_error(self, error: Exception, service_name: str,
                          metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Handle an error through the integrated recovery system.
        
        Args:
            error: Exception that occurred
            service_name: Service where error occurred
            metadata: Additional error context
            
        Returns:
            True if error was handled successfully
        """
        logger.info(
            "Handling error through recovery system",
            service=service_name,
            error_type=type(error).__name__
        )
        
        # Handle through fault tolerance coordinator
        return await self._fault_coordinator.handle_system_error(
            error, service_name, metadata
        )
    
    async def trigger_emergency(self, reason: str) -> None:
        """
        Trigger emergency procedures.
        
        Args:
            reason: Reason for emergency
        """
        await self._fault_coordinator.trigger_emergency_procedures(reason)
    
    async def recover_service(self, service_name: str, reason: str = "Manual recovery") -> bool:
        """
        Manually trigger service recovery.
        
        Args:
            service_name: Name of service to recover
            reason: Reason for recovery
            
        Returns:
            True if recovery was successful
        """
        return await self._auto_recovery.trigger_recovery(service_name, reason)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        fault_status = self._fault_coordinator.get_system_status()
        recovery_status = self._auto_recovery.get_recovery_status()
        
        return {
            "initialized": self._is_initialized,
            "registered_services": list(self._registered_services.keys()),
            "fault_tolerance": fault_status,
            "auto_recovery": recovery_status,
            "timestamp": fault_status.get("timestamp")
        }
    
    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Handle system events (implements IEventHandler)."""
        # Forward events to fault tolerance coordinator
        await self._fault_coordinator.handle_event(event_type, event_data)
    
    def get_supported_events(self) -> List[str]:
        """Get supported event types."""
        return self._fault_coordinator.get_supported_events()
    
    # Private methods
    
    async def _setup_default_retry_configs(self) -> None:
        """Setup default retry configurations for different service types."""
        logger.debug("Setting up default retry configurations")
        
        # These would be stored for use when registering services
        self._default_retry_configs = {
            "CaptureService": RetryConfig(
                max_attempts=2,
                base_delay=0.5,
                strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
                retry_on_exceptions=[ServiceError, ConnectionError]
            ),
            "AECService": RetryConfig(
                max_attempts=3,
                base_delay=0.1,
                strategy=RetryStrategy.JITTERED_BACKOFF,
                retry_on_exceptions=[ServiceError]
            ),
            "BeamformerService": RetryConfig(
                max_attempts=3,
                base_delay=0.2,
                strategy=RetryStrategy.EXPONENTIAL_BACKOFF
            ),
            "SSLService": RetryConfig(
                max_attempts=2,
                base_delay=0.3,
                strategy=RetryStrategy.LINEAR_BACKOFF
            ),
            "AGCService": RetryConfig(
                max_attempts=3,
                base_delay=0.1,
                strategy=RetryStrategy.FIXED_DELAY
            )
        }
    
    async def _register_event_handlers(self) -> None:
        """Register event handlers with the service manager."""
        if self._service_manager and hasattr(self._service_manager, 'subscribe_to_events'):
            # Register for relevant events
            events = self.get_supported_events()
            for event_type in events:
                self._service_manager.subscribe_to_events(event_type, self)
            
            logger.debug("Event handlers registered", events=events)
    
    def _get_retry_config_for_service(self, service_name: str) -> RetryConfig:
        """Get retry configuration for a service type."""
        return self._default_retry_configs.get(service_name, RetryConfig())
    
    def _create_recovery_strategy(self, service_name: str) -> callable:
        """Create recovery strategy function for a service."""
        async def recovery_strategy(name: str) -> bool:
            logger.info("Executing recovery strategy", service=name)
            
            if not self._service_manager:
                logger.error("No service manager available for recovery")
                return False
            
            try:
                # Attempt to restart the service
                await self._service_manager.restart_service(name)
                
                # Verify service is running
                service_status = self._service_manager.get_service_status()
                service_info = service_status.get(name, {})
                
                is_healthy = service_info.get("running", False) and service_info.get("healthy", False)
                
                if is_healthy:
                    logger.info("Service recovery successful", service=name)
                    return True
                else:
                    logger.warning("Service recovery incomplete", service=name)
                    return False
                    
            except Exception as e:
                logger.error("Service recovery failed", service=name, error=str(e))
                return False
        
        return recovery_strategy


# Convenience function for easy integration
def create_error_recovery_system(audio_config: AudioConfig,
                                failsafe_config: Optional[FailsafeConfig] = None) -> ErrorRecoverySystem:
    """
    Create and configure an error recovery system.
    
    Args:
        audio_config: Audio system configuration
        failsafe_config: Failsafe configuration (optional)
        
    Returns:
        Configured ErrorRecoverySystem instance
    """
    return ErrorRecoverySystem(audio_config, failsafe_config)