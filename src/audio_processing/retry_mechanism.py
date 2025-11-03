"""
Retry and automatic recovery mechanisms for audio processing services.

This module provides configurable retry strategies, exponential backoff,
and automatic recovery mechanisms for transient failures.
"""

import asyncio
import time
import random
from typing import Callable, Any, Optional, Dict, List
from dataclasses import dataclass
from enum import Enum
import structlog

from .exceptions import ServiceError

logger = structlog.get_logger(__name__)


class RetryStrategy(Enum):
    """Available retry strategies."""
    FIXED_DELAY = "fixed_delay"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    JITTERED_BACKOFF = "jittered_backoff"


@dataclass
class RetryConfig:
    """Configuration for retry mechanisms."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    backoff_multiplier: float = 2.0
    jitter_range: float = 0.1
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    retry_on_exceptions: List[type] = None
    stop_on_exceptions: List[type] = None


class RetryMechanism:
    """
    Configurable retry mechanism with multiple backoff strategies.
    
    Provides automatic retry functionality for transient failures
    with configurable backoff strategies and exception handling.
    """
    
    def __init__(self, config: RetryConfig):
        self._config = config
        self._retry_counts: Dict[str, int] = {}
        self._last_attempt_times: Dict[str, float] = {}
        
        # Default exceptions to retry on
        if config.retry_on_exceptions is None:
            self._config.retry_on_exceptions = [
                ServiceError, ConnectionError, TimeoutError
            ]
        
        # Default exceptions to stop on
        if config.stop_on_exceptions is None:
            self._config.stop_on_exceptions = [
                KeyboardInterrupt, SystemExit
            ]
    
    async def execute_with_retry(self, func: Callable, *args, 
                               operation_id: str = None, **kwargs) -> Any:
        """
        Execute function with retry logic.
        
        Args:
            func: Function to execute
            *args: Function arguments
            operation_id: Unique identifier for this operation
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: If all retry attempts fail
        """
        if operation_id is None:
            operation_id = f"{func.__name__}_{id(func)}"
        
        attempt = 0
        last_exception = None
        
        while attempt < self._config.max_attempts:
            attempt += 1
            
            try:
                # Record attempt
                self._retry_counts[operation_id] = attempt
                self._last_attempt_times[operation_id] = time.time()
                
                logger.debug(
                    "Executing operation",
                    operation_id=operation_id,
                    attempt=attempt,
                    max_attempts=self._config.max_attempts
                )
                
                # Execute function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # Success - reset retry count
                if operation_id in self._retry_counts:
                    del self._retry_counts[operation_id]
                
                logger.debug(
                    "Operation succeeded",
                    operation_id=operation_id,
                    attempt=attempt
                )
                
                return result
                
            except Exception as e:
                last_exception = e
                
                # Check if we should stop retrying
                if self._should_stop_retry(e):
                    logger.error(
                        "Stopping retry due to non-retryable exception",
                        operation_id=operation_id,
                        exception=type(e).__name__,
                        message=str(e)
                    )
                    raise e
                
                # Check if we should retry
                if not self._should_retry(e):
                    logger.error(
                        "Not retrying due to exception type",
                        operation_id=operation_id,
                        exception=type(e).__name__,
                        message=str(e)
                    )
                    raise e
                
                logger.warning(
                    "Operation failed, will retry",
                    operation_id=operation_id,
                    attempt=attempt,
                    exception=type(e).__name__,
                    message=str(e)
                )
                
                # Calculate delay before next attempt
                if attempt < self._config.max_attempts:
                    delay = self._calculate_delay(attempt)
                    
                    logger.debug(
                        "Waiting before retry",
                        operation_id=operation_id,
                        delay_seconds=delay
                    )
                    
                    await asyncio.sleep(delay)
        
        # All attempts failed
        logger.error(
            "All retry attempts failed",
            operation_id=operation_id,
            attempts=self._config.max_attempts,
            final_exception=type(last_exception).__name__ if last_exception else "Unknown"
        )
        
        if last_exception:
            raise last_exception
        else:
            raise ServiceError(f"Operation {operation_id} failed after {self._config.max_attempts} attempts")
    
    def get_retry_statistics(self) -> Dict[str, Any]:
        """
        Get retry statistics.
        
        Returns:
            Dictionary with retry statistics
        """
        current_time = time.time()
        
        active_retries = {}
        for operation_id, last_time in self._last_attempt_times.items():
            if current_time - last_time < 300:  # Active in last 5 minutes
                active_retries[operation_id] = {
                    "attempts": self._retry_counts.get(operation_id, 0),
                    "last_attempt": last_time
                }
        
        return {
            "config": {
                "max_attempts": self._config.max_attempts,
                "base_delay": self._config.base_delay,
                "strategy": self._config.strategy.value
            },
            "active_retries": active_retries,
            "total_operations": len(self._retry_counts)
        }
    

    
    def _should_retry(self, exception: Exception) -> bool:
        """Check if exception should trigger a retry."""
        exception_type = type(exception)
        
        # Check if exception type is in retry list
        for retry_type in self._config.retry_on_exceptions:
            if issubclass(exception_type, retry_type):
                return True
        
        return False
    
    def _should_stop_retry(self, exception: Exception) -> bool:
        """Check if exception should stop retrying."""
        exception_type = type(exception)
        
        # Check if exception type is in stop list
        for stop_type in self._config.stop_on_exceptions:
            if issubclass(exception_type, stop_type):
                return True
        
        return False
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay before next retry attempt."""
        if self._config.strategy == RetryStrategy.FIXED_DELAY:
            return self._config.base_delay
        
        elif self._config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self._config.base_delay * (self._config.backoff_multiplier ** (attempt - 1))
            return min(delay, self._config.max_delay)
        
        elif self._config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self._config.base_delay * attempt
            return min(delay, self._config.max_delay)
        
        elif self._config.strategy == RetryStrategy.JITTERED_BACKOFF:
            base_delay = self._config.base_delay * (self._config.backoff_multiplier ** (attempt - 1))
            jitter = base_delay * self._config.jitter_range * (2 * random.random() - 1)
            delay = base_delay + jitter
            return min(max(delay, 0), self._config.max_delay)
        
        else:
            return self._config.base_delay


class AutoRecoveryManager:
    """
    Automatic recovery manager for audio processing services.
    
    Monitors service health and automatically attempts recovery
    using configurable strategies and retry mechanisms.
    """
    
    def __init__(self):
        self._retry_mechanisms: Dict[str, RetryMechanism] = {}
        self._recovery_strategies: Dict[str, Callable] = {}
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._service_health: Dict[str, bool] = {}
        self._recovery_in_progress: Dict[str, bool] = {}
        
        logger.info("Auto-recovery manager initialized")
    
    def register_service(self, service_name: str, service: Any,
                        retry_config: Optional[RetryConfig] = None,
                        recovery_strategy: Optional[Callable] = None) -> None:
        """
        Register service for auto-recovery monitoring.
        
        Args:
            service_name: Name of the service
            service: Service instance
            retry_config: Retry configuration for this service
            recovery_strategy: Custom recovery strategy function
        """
        # Create retry mechanism
        if retry_config is None:
            retry_config = RetryConfig()
        
        self._retry_mechanisms[service_name] = RetryMechanism(retry_config)
        
        # Register recovery strategy
        if recovery_strategy:
            self._recovery_strategies[service_name] = recovery_strategy
        else:
            self._recovery_strategies[service_name] = self._default_recovery_strategy
        
        # Initialize health status
        self._service_health[service_name] = True
        self._recovery_in_progress[service_name] = False
        
        logger.info("Service registered for auto-recovery", service=service_name)
    
    async def start_monitoring(self, service_name: str) -> None:
        """
        Start health monitoring for a service.
        
        Args:
            service_name: Name of service to monitor
        """
        if service_name in self._monitoring_tasks:
            logger.warning("Monitoring already active", service=service_name)
            return
        
        logger.info("Starting health monitoring", service=service_name)
        
        async def monitor_task():
            while True:
                try:
                    await self._check_service_health(service_name)
                    await asyncio.sleep(5.0)  # Check every 5 seconds
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(
                        "Health monitoring error",
                        service=service_name,
                        error=str(e)
                    )
                    await asyncio.sleep(1.0)
        
        self._monitoring_tasks[service_name] = asyncio.create_task(monitor_task())
    
    async def stop_monitoring(self, service_name: str) -> None:
        """
        Stop health monitoring for a service.
        
        Args:
            service_name: Name of service to stop monitoring
        """
        if service_name in self._monitoring_tasks:
            self._monitoring_tasks[service_name].cancel()
            try:
                await self._monitoring_tasks[service_name]
            except asyncio.CancelledError:
                pass
            del self._monitoring_tasks[service_name]
            
            logger.info("Health monitoring stopped", service=service_name)
    
    async def trigger_recovery(self, service_name: str, reason: str = "Manual trigger") -> bool:
        """
        Manually trigger recovery for a service.
        
        Args:
            service_name: Name of service to recover
            reason: Reason for recovery
            
        Returns:
            True if recovery was successful
        """
        if service_name not in self._recovery_strategies:
            logger.error("Service not registered for recovery", service=service_name)
            return False
        
        if self._recovery_in_progress.get(service_name, False):
            logger.warning("Recovery already in progress", service=service_name)
            return False
        
        logger.info("Triggering recovery", service=service_name, reason=reason)
        
        self._recovery_in_progress[service_name] = True
        
        try:
            retry_mechanism = self._retry_mechanisms[service_name]
            recovery_strategy = self._recovery_strategies[service_name]
            
            # Execute recovery with retry
            success = await retry_mechanism.execute_with_retry(
                recovery_strategy,
                service_name,
                operation_id=f"recovery_{service_name}"
            )
            
            if success:
                self._service_health[service_name] = True
                logger.info("Recovery successful", service=service_name)
            else:
                logger.error("Recovery failed", service=service_name)
            
            return success
            
        except Exception as e:
            logger.error("Recovery exception", service=service_name, error=str(e))
            return False
        
        finally:
            self._recovery_in_progress[service_name] = False
    
    def get_recovery_status(self) -> Dict[str, Any]:
        """Get status of all recovery operations."""
        return {
            "services": {
                name: {
                    "healthy": self._service_health.get(name, False),
                    "recovery_in_progress": self._recovery_in_progress.get(name, False),
                    "monitoring_active": name in self._monitoring_tasks
                }
                for name in self._recovery_strategies.keys()
            },
            "retry_statistics": {
                name: mechanism.get_retry_statistics()
                for name, mechanism in self._retry_mechanisms.items()
            }
        }
    
    async def _check_service_health(self, service_name: str) -> None:
        """Check health of a specific service."""
        # This would implement actual health checking logic
        # For now, we'll simulate health checking
        
        current_health = self._service_health.get(service_name, True)
        
        # Simulate health check (in real implementation, this would check actual service)
        # If service is unhealthy and not recovering, trigger recovery
        if not current_health and not self._recovery_in_progress.get(service_name, False):
            logger.warning("Unhealthy service detected", service=service_name)
            await self.trigger_recovery(service_name, "Health check failure")
    
    async def _default_recovery_strategy(self, service_name: str) -> bool:
        """Default recovery strategy for services."""
        logger.info("Executing default recovery strategy", service=service_name)
        
        # Default strategy: restart the service
        # This would interface with the actual service manager
        
        # Simulate recovery delay
        await asyncio.sleep(1.0)
        
        # Simulate success/failure (in real implementation, check actual service state)
        return True