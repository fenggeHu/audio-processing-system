"""
Dependency injection container for the audio processing system.

This module provides a simple but effective dependency injection
container that manages service instances, their dependencies,
and lifecycle.
"""

import asyncio
from typing import Dict, Any, Type, TypeVar, Callable, List, Set
import inspect
import structlog

from .interfaces import IAudioService
from .exceptions import DependencyError, ServiceError

logger = structlog.get_logger(__name__)

T = TypeVar('T')


class DIContainer:
    """
    Dependency injection container.
    
    Manages service registration, dependency resolution, and lifecycle.
    Supports singleton and transient service lifetimes.
    """
    
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._singletons: Dict[str, Any] = {}
        self._service_configs: Dict[str, Dict[str, Any]] = {}
        self._dependency_graph: Dict[str, Set[str]] = {}
        self._lifecycle_hooks: Dict[str, List[Callable]] = {
            'before_create': [],
            'after_create': [],
            'before_destroy': [],
            'after_destroy': []
        }
    
    def register_singleton(self, service_type: Type[T], 
                          implementation: Type[T] = None,
                          name: str = None,
                          config: Dict[str, Any] = None) -> 'DIContainer':
        """
        Register a service as singleton (single instance).
        
        Args:
            service_type: Interface or base class type
            implementation: Concrete implementation class
            name: Optional service name (defaults to class name)
            config: Optional configuration for the service
            
        Returns:
            Self for method chaining
        """
        impl_class = implementation or service_type
        service_name = name or impl_class.__name__
        
        self._factories[service_name] = impl_class
        self._service_configs[service_name] = config or {}
        
        # Analyze dependencies
        self._analyze_dependencies(service_name, impl_class)
        
        logger.debug(
            "Registered singleton service",
            service=service_name,
            implementation=impl_class.__name__
        )
        
        return self
    
    def register_transient(self, service_type: Type[T],
                          implementation: Type[T] = None,
                          name: str = None,
                          config: Dict[str, Any] = None) -> 'DIContainer':
        """
        Register a service as transient (new instance each time).
        
        Args:
            service_type: Interface or base class type
            implementation: Concrete implementation class
            name: Optional service name
            config: Optional configuration for the service
            
        Returns:
            Self for method chaining
        """
        impl_class = implementation or service_type
        service_name = name or impl_class.__name__
        
        # For transient services, we store the factory directly
        self._services[service_name] = impl_class
        self._service_configs[service_name] = config or {}
        
        self._analyze_dependencies(service_name, impl_class)
        
        logger.debug(
            "Registered transient service",
            service=service_name,
            implementation=impl_class.__name__
        )
        
        return self
    
    def register_instance(self, instance: T, name: str = None) -> 'DIContainer':
        """
        Register an existing instance.
        
        Args:
            instance: Service instance to register
            name: Optional service name
            
        Returns:
            Self for method chaining
        """
        service_name = name or instance.__class__.__name__
        self._singletons[service_name] = instance
        
        logger.debug(
            "Registered service instance",
            service=service_name,
            type=instance.__class__.__name__
        )
        
        return self
    
    async def get(self, service_type: Type[T], name: str = None) -> T:
        """
        Get service instance by type or name.
        
        Args:
            service_type: Service type to retrieve
            name: Optional service name
            
        Returns:
            Service instance
            
        Raises:
            DependencyError: If service cannot be resolved
        """
        service_name = name or service_type.__name__
        
        # Check if already instantiated as singleton
        if service_name in self._singletons:
            return self._singletons[service_name]
        
        # Check if registered as transient
        if service_name in self._services:
            return await self._create_instance(service_name, self._services[service_name])
        
        # Check if registered as singleton factory
        if service_name in self._factories:
            instance = await self._create_instance(service_name, self._factories[service_name])
            self._singletons[service_name] = instance
            return instance
        
        raise DependencyError(f"Service not registered: {service_name}")
    
    async def get_by_name(self, name: str) -> Any:
        """
        Get service instance by name only.
        
        Args:
            name: Service name
            
        Returns:
            Service instance
        """
        if name in self._singletons:
            return self._singletons[name]
        
        if name in self._services:
            return await self._create_instance(name, self._services[name])
        
        if name in self._factories:
            instance = await self._create_instance(name, self._factories[name])
            self._singletons[name] = instance
            return instance
        
        raise DependencyError(f"Service not found: {name}")
    
    def is_registered(self, service_type: Type[T] = None, name: str = None) -> bool:
        """
        Check if a service is registered.
        
        Args:
            service_type: Service type to check
            name: Service name to check
            
        Returns:
            True if service is registered
        """
        service_name = name or (service_type.__name__ if service_type else None)
        if not service_name:
            return False
        
        return (service_name in self._services or 
                service_name in self._factories or 
                service_name in self._singletons)
    
    async def start_all_services(self) -> None:
        """
        Start all registered services that implement IAudioService.
        
        Services are started in dependency order.
        """
        # Get all service names
        all_services = set(self._services.keys()) | set(self._factories.keys())
        
        # Resolve dependency order
        start_order = self._resolve_dependency_order(all_services)
        
        logger.info("Starting services", order=start_order)
        
        for service_name in start_order:
            try:
                instance = await self.get_by_name(service_name)
                
                if isinstance(instance, IAudioService):
                    await instance.start()
                    logger.info("Service started", service=service_name)
                
            except Exception as e:
                logger.error(
                    "Failed to start service",
                    service=service_name,
                    error=str(e)
                )
                raise ServiceError(f"Failed to start {service_name}: {e}")
    
    async def stop_all_services(self) -> None:
        """
        Stop all running services in reverse dependency order.
        """
        # Get all instantiated services
        running_services = []
        
        for service_name, instance in self._singletons.items():
            if isinstance(instance, IAudioService) and instance.is_running:
                running_services.append((service_name, instance))
        
        # Stop in reverse order
        running_services.reverse()
        
        logger.info("Stopping services", count=len(running_services))
        
        for service_name, instance in running_services:
            try:
                await instance.stop()
                logger.info("Service stopped", service=service_name)
            except Exception as e:
                logger.error(
                    "Error stopping service",
                    service=service_name,
                    error=str(e)
                )
    
    def add_lifecycle_hook(self, event: str, callback: Callable) -> None:
        """
        Add lifecycle hook callback.
        
        Args:
            event: Event name ('before_create', 'after_create', etc.)
            callback: Callback function
        """
        if event in self._lifecycle_hooks:
            self._lifecycle_hooks[event].append(callback)
    
    def get_service_info(self) -> Dict[str, Any]:
        """
        Get information about registered services.
        
        Returns:
            Dictionary with service registration info
        """
        return {
            'singletons': list(self._factories.keys()),
            'transients': list(self._services.keys()),
            'instances': list(self._singletons.keys()),
            'dependency_graph': dict(self._dependency_graph)
        }
    
    async def _create_instance(self, service_name: str, service_class: Type) -> Any:
        """Create service instance with dependency injection."""
        # Call before_create hooks
        for hook in self._lifecycle_hooks['before_create']:
            await self._call_hook(hook, service_name, service_class)
        
        # Get constructor parameters
        sig = inspect.signature(service_class.__init__)
        kwargs = {}
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            
            # Check if parameter has type annotation
            if param.annotation != inspect.Parameter.empty:
                try:
                    # Try to resolve dependency
                    dependency = await self.get(param.annotation)
                    kwargs[param_name] = dependency
                except DependencyError:
                    # Check if parameter has default value
                    if param.default == inspect.Parameter.empty:
                        logger.warning(
                            "Cannot resolve dependency",
                            service=service_name,
                            parameter=param_name,
                            type=param.annotation
                        )
        
        # Add service configuration and service name
        config = self._service_configs.get(service_name, {})
        
        # Handle service_name parameter
        if 'service_name' in sig.parameters:
            kwargs['service_name'] = service_name
        
        # Handle config parameter
        if 'config' in sig.parameters:
            if config and 'config' in config:
                kwargs['config'] = config['config']
            elif 'config' in config:
                kwargs['config'] = config['config']
        
        # Create instance
        try:
            if asyncio.iscoroutinefunction(service_class.__init__):
                instance = await service_class(**kwargs)
            else:
                instance = service_class(**kwargs)
            
            # Call after_create hooks
            for hook in self._lifecycle_hooks['after_create']:
                await self._call_hook(hook, service_name, instance)
            
            logger.debug("Service instance created", service=service_name)
            return instance
            
        except Exception as e:
            logger.error(
                "Failed to create service instance",
                service=service_name,
                error=str(e)
            )
            raise DependencyError(f"Failed to create {service_name}: {e}")
    
    def _analyze_dependencies(self, service_name: str, service_class: Type) -> None:
        """Analyze service dependencies from constructor parameters."""
        sig = inspect.signature(service_class.__init__)
        dependencies = set()
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            
            if param.annotation != inspect.Parameter.empty:
                # Try to find registered service for this type
                dep_name = param.annotation.__name__
                if self.is_registered(param.annotation) or self.is_registered(name=dep_name):
                    dependencies.add(dep_name)
        
        self._dependency_graph[service_name] = dependencies
    
    def _resolve_dependency_order(self, service_names: Set[str]) -> List[str]:
        """Resolve service startup order based on dependencies."""
        ordered = []
        visited = set()
        visiting = set()
        
        def visit(name: str) -> None:
            if name in visiting:
                raise DependencyError(f"Circular dependency detected involving {name}")
            
            if name in visited:
                return
            
            visiting.add(name)
            
            # Visit dependencies first
            for dep in self._dependency_graph.get(name, set()):
                if dep in service_names:
                    visit(dep)
            
            visiting.remove(name)
            visited.add(name)
            ordered.append(name)
        
        for service_name in service_names:
            visit(service_name)
        
        return ordered
    
    async def _call_hook(self, hook: Callable, *args) -> None:
        """Call lifecycle hook with error handling."""
        try:
            if asyncio.iscoroutinefunction(hook):
                await hook(*args)
            else:
                hook(*args)
        except Exception as e:
            logger.error("Lifecycle hook failed", error=str(e))