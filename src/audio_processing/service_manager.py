"""
Service manager for coordinating audio processing services.

This module provides the ServiceManager class that orchestrates
the lifecycle and coordination of all audio processing services
in the system.
"""

import asyncio
from typing import Dict, List, Optional, Any, Type
import structlog

from .interfaces import IAudioService, IMetricsCollector, IEventHandler
from .models import AudioConfig, AudioMetrics
from .container import DIContainer
from .exceptions import ServiceError

logger = structlog.get_logger(__name__)


class ServiceManager(IEventHandler):
    """
    Manages the lifecycle and coordination of audio processing services.
    
    The ServiceManager is responsible for:
    - Service registration and dependency injection
    - Service lifecycle management (start/stop)
    - Service health monitoring
    - Event coordination between services
    - Configuration management
    """
    
    def __init__(self, config: AudioConfig):
        self._config = config
        self._container = DIContainer()
        self._services: Dict[str, IAudioService] = {}
        self._service_health: Dict[str, bool] = {}
        self._event_handlers: Dict[str, List[IEventHandler]] = {}
        self._is_running = False
        self._health_check_task: Optional[asyncio.Task] = None
        self._metrics_collector: Optional[IMetricsCollector] = None
        
        # Setup lifecycle hooks
        self._container.add_lifecycle_hook('after_create', self._on_service_created)
        self._container.add_lifecycle_hook('before_destroy', self._on_service_destroyed)
    
    @property
    def is_running(self) -> bool:
        """Check if service manager is running."""
        return self._is_running
    
    @property
    def container(self) -> DIContainer:
        """Get dependency injection container."""
        return self._container
    
    def register_service(self, service_type: Type[IAudioService],
                        implementation: Type[IAudioService] = None,
                        name: str = None,
                        config: Dict[str, Any] = None,
                        singleton: bool = True) -> 'ServiceManager':
        """
        Register an audio processing service.
        
        Args:
            service_type: Service interface type
            implementation: Concrete implementation class
            name: Optional service name
            config: Optional service-specific configuration
            singleton: Whether to register as singleton (default) or transient
            
        Returns:
            Self for method chaining
        """
        if singleton:
            self._container.register_singleton(
                service_type, implementation, name, config
            )
        else:
            self._container.register_transient(
                service_type, implementation, name, config
            )
        
        service_name = name or (implementation or service_type).__name__
        logger.info(
            "Service registered",
            service=service_name,
            type="singleton" if singleton else "transient"
        )
        
        return self
    
    def register_metrics_collector(self, collector: IMetricsCollector) -> 'ServiceManager':
        """
        Register metrics collector.
        
        Args:
            collector: Metrics collector instance
            
        Returns:
            Self for method chaining
        """
        self._metrics_collector = collector
        self._container.register_instance(collector, "MetricsCollector")
        logger.info("Metrics collector registered")
        return self
    
    async def start(self) -> None:
        """
        Start the service manager and all registered services.
        
        Services are started in dependency order to ensure
        proper initialization.
        """
        if self._is_running:
            logger.warning("Service manager already running")
            return
        
        logger.info("Starting service manager")
        
        try:
            # Start all services through container
            await self._container.start_all_services()
            
            # Collect service references
            await self._collect_service_references()
            
            # Start health monitoring
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
            self._is_running = True
            
            # Emit startup event
            await self._emit_event('service_manager_started', {
                'services': list(self._services.keys()),
                'config': self._config.model_dump()
            })
            
            logger.info(
                "Service manager started successfully",
                service_count=len(self._services)
            )
            
        except Exception as e:
            logger.error("Failed to start service manager", error=str(e))
            await self._cleanup()
            raise ServiceError(f"Service manager startup failed: {e}")
    
    async def stop(self) -> None:
        """
        Stop the service manager and all services.
        
        Services are stopped in reverse dependency order.
        """
        if not self._is_running:
            logger.warning("Service manager not running")
            return
        
        logger.info("Stopping service manager")
        
        self._is_running = False
        
        # Stop health monitoring
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Emit shutdown event
        await self._emit_event('service_manager_stopping', {})
        
        # Stop all services
        await self._container.stop_all_services()
        
        # Clear service references
        self._services.clear()
        self._service_health.clear()
        
        logger.info("Service manager stopped")
    
    async def get_service(self, service_type: Type[IAudioService], 
                         name: str = None) -> IAudioService:
        """
        Get service instance by type or name.
        
        Args:
            service_type: Service type
            name: Optional service name
            
        Returns:
            Service instance
        """
        return await self._container.get(service_type, name)
    
    async def get_service_by_name(self, name: str) -> IAudioService:
        """
        Get service instance by name.
        
        Args:
            name: Service name
            
        Returns:
            Service instance
        """
        return await self._container.get_by_name(name)
    
    def get_service_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all services.
        
        Returns:
            Dictionary mapping service names to status info
        """
        status = {}
        
        for name, service in self._services.items():
            status[name] = {
                'running': service.is_running,
                'healthy': self._service_health.get(name, False),
                'metrics': service.get_metrics().model_dump() if hasattr(service, 'get_metrics') else {}
            }
        
        return status
    
    def get_system_metrics(self) -> Dict[str, AudioMetrics]:
        """
        Get metrics for all services.
        
        Returns:
            Dictionary mapping service names to metrics
        """
        if not self._metrics_collector:
            return {}
        
        return self._metrics_collector.get_system_metrics()
    
    async def restart_service(self, service_name: str) -> None:
        """
        Restart a specific service.
        
        Args:
            service_name: Name of service to restart
        """
        if service_name not in self._services:
            raise ServiceError(f"Service not found: {service_name}")
        
        service = self._services[service_name]
        
        logger.info("Restarting service", service=service_name)
        
        try:
            # Stop service
            if service.is_running:
                await service.stop()
            
            # Start service
            await service.start()
            
            # Update health status
            self._service_health[service_name] = True
            
            # Emit restart event
            await self._emit_event('service_restarted', {
                'service_name': service_name
            })
            
            logger.info("Service restarted successfully", service=service_name)
            
        except Exception as e:
            self._service_health[service_name] = False
            logger.error(
                "Failed to restart service",
                service=service_name,
                error=str(e)
            )
            raise ServiceError(f"Failed to restart {service_name}: {e}")
    
    async def update_config(self, config: AudioConfig) -> None:
        """
        Update system configuration and propagate to services.
        
        Args:
            config: New audio configuration
        """
        old_config = self._config
        self._config = config
        
        logger.info("Updating system configuration")
        
        # Update each service's configuration
        for name, service in self._services.items():
            try:
                if hasattr(service, 'update_config'):
                    await service.update_config(config)
                    logger.debug("Service config updated", service=name)
            except Exception as e:
                logger.error(
                    "Failed to update service config",
                    service=name,
                    error=str(e)
                )
        
        # Emit config change event
        await self._emit_event('config_updated', {
            'old_config': old_config.model_dump(),
            'new_config': config.model_dump()
        })
    

    
    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Handle system events (implements IEventHandler)."""
        logger.debug("Handling event", event_type=event_type)
        
        # Handle service manager specific events
        if event_type == 'service_error':
            await self._handle_service_error(event_data)
        elif event_type == 'service_health_check':
            await self._handle_health_check(event_data)
    
    def get_supported_events(self) -> List[str]:
        """Get supported event types."""
        return [
            'service_error',
            'service_health_check',
            'service_manager_started',
            'service_manager_stopping',
            'service_restarted',
            'config_updated'
        ]
    
    async def _collect_service_references(self) -> None:
        """Collect references to all instantiated services."""
        container_info = self._container.get_service_info()
        
        # Get singleton instances
        for service_name in container_info['instances']:
            try:
                instance = await self._container.get_by_name(service_name)
                if isinstance(instance, IAudioService):
                    self._services[service_name] = instance
                    self._service_health[service_name] = instance.is_running
            except Exception as e:
                logger.error(
                    "Failed to collect service reference",
                    service=service_name,
                    error=str(e)
                )
    
    async def _health_check_loop(self) -> None:
        """Background task for monitoring service health."""
        while self._is_running:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(5.0)  # Check every 5 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health check failed", error=str(e))
                await asyncio.sleep(1.0)
    
    async def _perform_health_checks(self) -> None:
        """Perform health checks on all services."""
        for name, service in self._services.items():
            try:
                is_healthy = service.is_running
                
                # Additional health checks can be added here
                # e.g., check metrics, response times, etc.
                
                old_health = self._service_health.get(name, True)
                self._service_health[name] = is_healthy
                
                # Emit health change event
                if old_health != is_healthy:
                    await self._emit_event('service_health_changed', {
                        'service_name': name,
                        'healthy': is_healthy,
                        'previous_health': old_health
                    })
                
            except Exception as e:
                self._service_health[name] = False
                logger.error(
                    "Health check failed for service",
                    service=name,
                    error=str(e)
                )
    
    async def _emit_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Emit event to all registered handlers."""
        handlers = self._event_handlers.get(event_type, [])
        
        for handler in handlers:
            try:
                await handler.handle_event(event_type, event_data)
            except Exception as e:
                logger.error(
                    "Event handler failed",
                    event_type=event_type,
                    handler=handler.__class__.__name__,
                    error=str(e)
                )
    
    async def _handle_service_error(self, event_data: Dict[str, Any]) -> None:
        """Handle service error events."""
        service_name = event_data.get('service_name')
        error = event_data.get('error')
        
        logger.error("Service error reported", service=service_name, error=error)
        
        # Mark service as unhealthy
        if service_name:
            self._service_health[service_name] = False
        
        # Could implement automatic restart logic here
    
    async def _handle_health_check(self, event_data: Dict[str, Any]) -> None:
        """Handle health check events."""
        # This could trigger immediate health checks
        await self._perform_health_checks()
    
    async def _on_service_created(self, service_name: str, instance: Any) -> None:
        """Lifecycle hook called when service is created."""
        if isinstance(instance, IAudioService):
            logger.debug("Audio service created", service=service_name)
    
    async def _on_service_destroyed(self, service_name: str, instance: Any) -> None:
        """Lifecycle hook called before service is destroyed."""
        if isinstance(instance, IAudioService):
            logger.debug("Audio service being destroyed", service=service_name)
    
    async def _cleanup(self) -> None:
        """Cleanup resources on shutdown or error."""
        if self._health_check_task:
            self._health_check_task.cancel()
        
        self._services.clear()
        self._service_health.clear()
        self._is_running = False