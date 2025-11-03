"""
Error handling and recovery system for audio processing services.

This module provides comprehensive error handling, recovery strategies,
and fault tolerance mechanisms for the audio processing system.
"""

import asyncio
import time
from typing import Dict, Any, Optional, Callable, List, Tuple
from enum import Enum
from dataclasses import dataclass, field
import structlog

from .interfaces import IEventHandler
from .exceptions import (
    AudioProcessingError, ServiceError, ConfigError, ProcessingError,
    DeviceError, ProcessingTimeoutError, DependencyError, PluginError
)

logger = structlog.get_logger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecoveryAction(Enum):
    """Available recovery actions."""
    IGNORE = "ignore"
    RETRY = "retry"
    RESTART_SERVICE = "restart_service"
    DEGRADE_SERVICE = "degrade_service"
    FAILOVER = "failover"
    EMERGENCY_STOP = "emergency_stop"


@dataclass
class ErrorContext:
    """Context information for error handling."""
    service_name: str
    error_type: str
    error_message: str
    timestamp: float
    severity: ErrorSeverity
    metadata: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3


@dataclass
class RecoveryStrategy:
    """Recovery strategy configuration."""
    error_types: List[str]
    action: RecoveryAction
    max_attempts: int = 3
    backoff_delay: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_delay: float = 30.0
    condition_check: Optional[Callable[[ErrorContext], bool]] = None
    custom_handler: Optional[Callable[[ErrorContext], Any]] = None


class ErrorHandler(IEventHandler):
    """
    Comprehensive error handling system for audio processing services.
    
    Provides error classification, recovery strategies, and automatic
    error handling with configurable policies.
    """
    
    def __init__(self):
        self._error_counts: Dict[str, int] = {}
        self._error_history: List[ErrorContext] = []
        self._recovery_strategies: Dict[str, RecoveryStrategy] = {}
        self._service_health: Dict[str, bool] = {}
        self._recovery_callbacks: Dict[RecoveryAction, Callable] = {}
        self._max_history_size = 1000
        
        # Setup default recovery strategies
        self._setup_default_strategies()
    
    def register_recovery_callback(self, action: RecoveryAction, 
                                 callback: Callable[[ErrorContext], Any]) -> None:
        """
        Register callback for recovery action.
        
        Args:
            action: Recovery action type
            callback: Callback function to execute
        """
        self._recovery_callbacks[action] = callback
        logger.debug("Recovery callback registered", action=action.value)
    
    def add_recovery_strategy(self, strategy: RecoveryStrategy) -> None:
        """
        Add custom recovery strategy.
        
        Args:
            strategy: Recovery strategy configuration
        """
        for error_type in strategy.error_types:
            self._recovery_strategies[error_type] = strategy
        
        logger.info(
            "Recovery strategy added",
            error_types=strategy.error_types,
            action=strategy.action.value
        )
    
    async def handle_error(self, error: Exception, service_name: str,
                          metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Handle an error with appropriate recovery strategy.
        
        Args:
            error: Exception that occurred
            service_name: Name of service where error occurred
            metadata: Additional error context
            
        Returns:
            True if error was handled and recovery attempted, False otherwise
        """
        # Create error context
        context = self._create_error_context(error, service_name, metadata)
        
        # Log error
        logger.error(
            "Error occurred",
            service=service_name,
            error_type=context.error_type,
            error_message=context.error_message,
            severity=context.severity.value
        )
        
        # Update error statistics
        self._update_error_statistics(context)
        
        # Add to history
        self._add_to_history(context)
        
        # Determine recovery strategy
        strategy = self._get_recovery_strategy(context)
        
        if strategy:
            # Execute recovery strategy
            success = await self._execute_recovery_strategy(context, strategy)
            
            # Emit error event
            await self._emit_error_event(context, strategy, success)
            
            return success
        else:
            logger.warning(
                "No recovery strategy found",
                service=service_name,
                error_type=context.error_type
            )
            return False
    
    async def handle_service_failure(self, service_name: str, 
                                   failure_reason: str) -> RecoveryAction:
        """
        Handle complete service failure.
        
        Args:
            service_name: Name of failed service
            failure_reason: Reason for failure
            
        Returns:
            Recovery action taken
        """
        logger.critical(
            "Service failure detected",
            service=service_name,
            reason=failure_reason
        )
        
        # Mark service as unhealthy
        self._service_health[service_name] = False
        
        # Create failure context
        context = ErrorContext(
            service_name=service_name,
            error_type="ServiceFailure",
            error_message=failure_reason,
            timestamp=time.time(),
            severity=ErrorSeverity.CRITICAL,
            metadata={"failure_type": "complete_failure"}
        )
        
        # Get recovery strategy for service failures
        strategy = self._recovery_strategies.get("ServiceFailure")
        
        if strategy:
            await self._execute_recovery_strategy(context, strategy)
            return strategy.action
        else:
            # Default to emergency stop for critical failures
            await self._execute_emergency_stop(context)
            return RecoveryAction.EMERGENCY_STOP
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """
        Get error statistics and health information.
        
        Returns:
            Dictionary with error statistics
        """
        total_errors = sum(self._error_counts.values())
        
        # Calculate error rates by type
        error_rates = {}
        for error_type, count in self._error_counts.items():
            error_rates[error_type] = count / max(total_errors, 1)
        
        # Get recent error trends
        recent_errors = [
            ctx for ctx in self._error_history[-100:]
            if time.time() - ctx.timestamp < 300  # Last 5 minutes
        ]
        
        return {
            "total_errors": total_errors,
            "error_counts": self._error_counts.copy(),
            "error_rates": error_rates,
            "recent_errors": len(recent_errors),
            "service_health": self._service_health.copy(),
            "recovery_strategies": len(self._recovery_strategies)
        }
    
    def reset_error_statistics(self, service_name: Optional[str] = None) -> None:
        """
        Reset error statistics.
        
        Args:
            service_name: Service to reset, or None for all services
        """
        if service_name:
            # Reset for specific service
            keys_to_remove = [
                key for key in self._error_counts.keys()
                if key.startswith(f"{service_name}:")
            ]
            for key in keys_to_remove:
                del self._error_counts[key]
            
            # Remove from history
            self._error_history = [
                ctx for ctx in self._error_history
                if ctx.service_name != service_name
            ]
            
            logger.info("Error statistics reset", service=service_name)
        else:
            # Reset all statistics
            self._error_counts.clear()
            self._error_history.clear()
            self._service_health.clear()
            
            logger.info("All error statistics reset")
    
    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Handle system events (implements IEventHandler)."""
        if event_type == "service_error":
            service_name = event_data.get("service_name", "unknown")
            error_message = event_data.get("error", "Unknown error")
            
            # Create synthetic error for handling
            error = ServiceError(error_message, service_name)
            await self.handle_error(error, service_name, event_data)
        
        elif event_type == "service_health_changed":
            service_name = event_data.get("service_name")
            is_healthy = event_data.get("healthy", False)
            
            if service_name:
                self._service_health[service_name] = is_healthy
                
                if not is_healthy:
                    await self.handle_service_failure(
                        service_name, "Health check failed"
                    )
    
    def get_supported_events(self) -> List[str]:
        """Get supported event types."""
        return ["service_error", "service_health_changed"]
    
    def _create_error_context(self, error: Exception, service_name: str,
                            metadata: Optional[Dict[str, Any]]) -> ErrorContext:
        """Create error context from exception."""
        error_type = type(error).__name__
        severity = self._classify_error_severity(error)
        
        context = ErrorContext(
            service_name=service_name,
            error_type=error_type,
            error_message=str(error),
            timestamp=time.time(),
            severity=severity,
            metadata=metadata or {}
        )
        
        # Add stack trace for debugging
        import traceback
        context.stack_trace = traceback.format_exc()
        
        return context
    
    def _classify_error_severity(self, error: Exception) -> ErrorSeverity:
        """Classify error severity based on exception type."""
        if isinstance(error, (DeviceError, DependencyError)):
            return ErrorSeverity.CRITICAL
        elif isinstance(error, (ServiceError, ProcessingTimeoutError)):
            return ErrorSeverity.HIGH
        elif isinstance(error, (ConfigError, PluginError)):
            return ErrorSeverity.MEDIUM
        elif isinstance(error, ProcessingError):
            return ErrorSeverity.LOW
        else:
            return ErrorSeverity.MEDIUM
    
    def _update_error_statistics(self, context: ErrorContext) -> None:
        """Update error statistics with new error."""
        # Count by error type
        self._error_counts[context.error_type] = (
            self._error_counts.get(context.error_type, 0) + 1
        )
        
        # Count by service and error type
        service_error_key = f"{context.service_name}:{context.error_type}"
        self._error_counts[service_error_key] = (
            self._error_counts.get(service_error_key, 0) + 1
        )
    
    def _add_to_history(self, context: ErrorContext) -> None:
        """Add error context to history."""
        self._error_history.append(context)
        
        # Limit history size
        if len(self._error_history) > self._max_history_size:
            self._error_history = self._error_history[-self._max_history_size:]
    
    def _get_recovery_strategy(self, context: ErrorContext) -> Optional[RecoveryStrategy]:
        """Get recovery strategy for error context."""
        # Try exact error type match first
        strategy = self._recovery_strategies.get(context.error_type)
        
        if strategy:
            # Check condition if specified
            if strategy.condition_check and not strategy.condition_check(context):
                return None
            return strategy
        
        # Try base class matches
        for error_type, strategy in self._recovery_strategies.items():
            if error_type in context.error_type or context.error_type in error_type:
                if strategy.condition_check and not strategy.condition_check(context):
                    continue
                return strategy
        
        return None
    
    async def _execute_recovery_strategy(self, context: ErrorContext,
                                       strategy: RecoveryStrategy) -> bool:
        """Execute recovery strategy for error context."""
        if context.recovery_attempts >= strategy.max_attempts:
            logger.warning(
                "Max recovery attempts reached",
                service=context.service_name,
                error_type=context.error_type,
                attempts=context.recovery_attempts
            )
            return False
        
        context.recovery_attempts += 1
        
        logger.info(
            "Executing recovery strategy",
            service=context.service_name,
            action=strategy.action.value,
            attempt=context.recovery_attempts
        )
        
        try:
            if strategy.custom_handler:
                # Use custom handler
                result = await strategy.custom_handler(context)
                return bool(result)
            else:
                # Use built-in recovery actions
                return await self._execute_recovery_action(context, strategy)
        
        except Exception as e:
            logger.error(
                "Recovery strategy failed",
                service=context.service_name,
                action=strategy.action.value,
                error=str(e)
            )
            return False
    
    async def _execute_recovery_action(self, context: ErrorContext,
                                     strategy: RecoveryStrategy) -> bool:
        """Execute built-in recovery action."""
        action = strategy.action
        
        if action == RecoveryAction.IGNORE:
            return True
        
        elif action == RecoveryAction.RETRY:
            # Wait with exponential backoff
            delay = min(
                strategy.backoff_delay * (strategy.backoff_multiplier ** (context.recovery_attempts - 1)),
                strategy.max_backoff_delay
            )
            await asyncio.sleep(delay)
            return True
        
        elif action == RecoveryAction.RESTART_SERVICE:
            callback = self._recovery_callbacks.get(RecoveryAction.RESTART_SERVICE)
            if callback:
                return await callback(context)
            return False
        
        elif action == RecoveryAction.DEGRADE_SERVICE:
            callback = self._recovery_callbacks.get(RecoveryAction.DEGRADE_SERVICE)
            if callback:
                return await callback(context)
            return False
        
        elif action == RecoveryAction.FAILOVER:
            callback = self._recovery_callbacks.get(RecoveryAction.FAILOVER)
            if callback:
                return await callback(context)
            return False
        
        elif action == RecoveryAction.EMERGENCY_STOP:
            return await self._execute_emergency_stop(context)
        
        return False
    
    async def _execute_emergency_stop(self, context: ErrorContext) -> bool:
        """Execute emergency stop procedure."""
        logger.critical(
            "Executing emergency stop",
            service=context.service_name,
            reason=context.error_message
        )
        
        callback = self._recovery_callbacks.get(RecoveryAction.EMERGENCY_STOP)
        if callback:
            return await callback(context)
        
        return True
    
    async def _emit_error_event(self, context: ErrorContext, 
                              strategy: RecoveryStrategy, success: bool) -> None:
        """Emit error event for external handlers."""
        # This would integrate with the event bus system
        # For now, just log the event
        logger.info(
            "Error recovery completed",
            service=context.service_name,
            error_type=context.error_type,
            recovery_action=strategy.action.value,
            success=success,
            attempts=context.recovery_attempts
        )
    
    def _setup_default_strategies(self) -> None:
        """Setup default recovery strategies for common error types."""
        
        # Processing errors - retry with backoff
        self.add_recovery_strategy(RecoveryStrategy(
            error_types=["ProcessingError", "ProcessingTimeoutError"],
            action=RecoveryAction.RETRY,
            max_attempts=3,
            backoff_delay=0.1,
            backoff_multiplier=2.0
        ))
        
        # Configuration errors - restart service
        self.add_recovery_strategy(RecoveryStrategy(
            error_types=["ConfigError"],
            action=RecoveryAction.RESTART_SERVICE,
            max_attempts=2,
            backoff_delay=1.0
        ))
        
        # Device errors - critical, try failover
        self.add_recovery_strategy(RecoveryStrategy(
            error_types=["DeviceError"],
            action=RecoveryAction.FAILOVER,
            max_attempts=1,
            backoff_delay=0.5
        ))
        
        # Service errors - restart service
        self.add_recovery_strategy(RecoveryStrategy(
            error_types=["ServiceError"],
            action=RecoveryAction.RESTART_SERVICE,
            max_attempts=2,
            backoff_delay=2.0
        ))
        
        # Dependency errors - emergency stop
        self.add_recovery_strategy(RecoveryStrategy(
            error_types=["DependencyError"],
            action=RecoveryAction.EMERGENCY_STOP,
            max_attempts=1
        ))
        
        # Plugin errors - degrade service
        self.add_recovery_strategy(RecoveryStrategy(
            error_types=["PluginError"],
            action=RecoveryAction.DEGRADE_SERVICE,
            max_attempts=2,
            backoff_delay=1.0
        ))