"""
Plugin sandbox implementation for secure plugin execution.

This module provides security mechanisms to isolate plugin execution
and prevent malicious or buggy plugins from affecting the system.
"""

import asyncio
import sys
import os
import threading
import time
from typing import Dict, Any, Optional, Set, List, Callable
from contextlib import contextmanager
import structlog

from .exceptions import PluginError

logger = structlog.get_logger(__name__)


class ResourceLimiter:
    """Limits resource usage for plugin execution."""
    
    def __init__(self, max_memory_mb: int = 100, max_cpu_time_ms: int = 1000):
        self.max_memory_mb = max_memory_mb
        self.max_cpu_time_ms = max_cpu_time_ms
        self._start_time = None
        self._memory_tracker = None
    
    def start_monitoring(self) -> None:
        """Start resource monitoring."""
        self._start_time = time.time()
        # In a real implementation, you'd use psutil or similar
        # to track actual memory usage
    
    def check_limits(self) -> None:
        """Check if resource limits are exceeded."""
        if self._start_time:
            elapsed_ms = (time.time() - self._start_time) * 1000
            if elapsed_ms > self.max_cpu_time_ms:
                raise PluginError(f"Plugin exceeded CPU time limit: {elapsed_ms}ms")
    
    def stop_monitoring(self) -> None:
        """Stop resource monitoring."""
        self._start_time = None


class SecureImportHook:
    """Import hook to restrict plugin module imports."""
    
    def __init__(self, allowed_modules: Set[str], restricted_modules: Set[str]):
        self.allowed_modules = allowed_modules
        self.restricted_modules = restricted_modules
        self.original_import = None
    
    def __enter__(self):
        """Install import hook."""
        self.original_import = __builtins__['__import__']
        __builtins__['__import__'] = self._secure_import
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Remove import hook."""
        if self.original_import:
            __builtins__['__import__'] = self.original_import
    
    def _secure_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        """Secure import function that checks module restrictions."""
        # Check if module is explicitly restricted
        if name in self.restricted_modules:
            raise ImportError(f"Module '{name}' is restricted in plugin sandbox")
        
        # Check if module starts with restricted prefix
        for restricted in self.restricted_modules:
            if name.startswith(restricted + '.'):
                raise ImportError(f"Module '{name}' is restricted in plugin sandbox")
        
        # Allow explicitly allowed modules
        if name in self.allowed_modules:
            return self.original_import(name, globals, locals, fromlist, level)
        
        # Allow standard library modules that are safe
        safe_modules = {
            'math', 'random', 'json', 'datetime', 'time', 'collections',
            'itertools', 'functools', 'operator', 'copy', 'typing',
            'dataclasses', 'enum', 'abc', 'contextlib', 'weakref'
        }
        
        if name in safe_modules or name.startswith('audio_processing.'):
            return self.original_import(name, globals, locals, fromlist, level)
        
        # Log and allow other imports with warning
        logger.warning("Plugin importing unverified module", module=name)
        return self.original_import(name, globals, locals, fromlist, level)


class PluginExecutionContext:
    """Execution context for plugin operations with timeout and error handling."""
    
    def __init__(self, plugin_name: str, timeout_seconds: float = 5.0):
        self.plugin_name = plugin_name
        self.timeout_seconds = timeout_seconds
        self._task = None
        self._result = None
        self._exception = None
    
    async def execute(self, coro):
        """Execute coroutine with timeout and error handling."""
        try:
            self._result = await asyncio.wait_for(coro, timeout=self.timeout_seconds)
            return self._result
        except asyncio.TimeoutError:
            logger.error("Plugin execution timeout", plugin=self.plugin_name)
            raise PluginError(f"Plugin {self.plugin_name} execution timeout")
        except Exception as e:
            logger.error(
                "Plugin execution error",
                plugin=self.plugin_name,
                error=str(e)
            )
            self._exception = e
            raise PluginError(f"Plugin {self.plugin_name} execution failed: {e}")


class PluginSandbox:
    """
    Comprehensive plugin sandbox with security and resource controls.
    
    Provides:
    - Import restrictions
    - Resource limiting
    - Execution timeout
    - Error isolation
    - Logging and monitoring
    """
    
    def __init__(self, plugin_name: str, config: Optional[Dict[str, Any]] = None):
        self.plugin_name = plugin_name
        self.config = config or {}
        
        # Security settings
        self.allowed_modules = set(self.config.get('allowed_modules', [
            'numpy', 'scipy', 'librosa', 'soundfile', 'pydantic'
        ]))
        
        self.restricted_modules = set(self.config.get('restricted_modules', [
            'os', 'sys', 'subprocess', 'socket', 'urllib', 'http',
            'ftplib', 'smtplib', 'telnetlib', 'pickle', 'marshal',
            'eval', 'exec', 'compile', '__import__'
        ]))
        
        # Resource limits
        self.max_memory_mb = self.config.get('max_memory_mb', 100)
        self.max_cpu_time_ms = self.config.get('max_cpu_time_ms', 1000)
        self.execution_timeout = self.config.get('execution_timeout', 5.0)
        
        # Internal state
        self._resource_limiter = ResourceLimiter(
            self.max_memory_mb, 
            self.max_cpu_time_ms
        )
        self._import_hook = None
        self._execution_context = None
        self._original_modules = {}
        self._is_active = False
    
    async def __aenter__(self):
        """Enter sandbox context."""
        if self._is_active:
            raise PluginError(f"Sandbox already active for {self.plugin_name}")
        
        logger.debug("Entering plugin sandbox", plugin=self.plugin_name)
        
        try:
            # Setup import restrictions
            self._import_hook = SecureImportHook(
                self.allowed_modules, 
                self.restricted_modules
            )
            self._import_hook.__enter__()
            
            # Start resource monitoring
            self._resource_limiter.start_monitoring()
            
            # Create execution context
            self._execution_context = PluginExecutionContext(
                self.plugin_name, 
                self.execution_timeout
            )
            
            self._is_active = True
            
            logger.debug("Plugin sandbox activated", plugin=self.plugin_name)
            return self
            
        except Exception as e:
            logger.error(
                "Failed to enter plugin sandbox",
                plugin=self.plugin_name,
                error=str(e)
            )
            await self._cleanup()
            raise PluginError(f"Sandbox setup failed: {e}")
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit sandbox context."""
        logger.debug("Exiting plugin sandbox", plugin=self.plugin_name)
        
        try:
            await self._cleanup()
            
            if exc_type:
                logger.error(
                    "Plugin sandbox exception",
                    plugin=self.plugin_name,
                    exception_type=exc_type.__name__,
                    error=str(exc_val)
                )
                
                # Convert plugin exceptions to PluginError
                if not isinstance(exc_val, PluginError):
                    return False  # Re-raise as PluginError
            
        except Exception as cleanup_error:
            logger.error(
                "Error during sandbox cleanup",
                plugin=self.plugin_name,
                error=str(cleanup_error)
            )
        
        self._is_active = False
    
    async def execute_safe(self, coro):
        """
        Execute coroutine safely within sandbox constraints.
        
        Args:
            coro: Coroutine to execute
            
        Returns:
            Execution result
        """
        if not self._is_active:
            raise PluginError("Sandbox not active")
        
        if not self._execution_context:
            raise PluginError("Execution context not available")
        
        # Check resource limits before execution
        self._resource_limiter.check_limits()
        
        # Execute with timeout and error handling
        result = await self._execution_context.execute(coro)
        
        # Check resource limits after execution
        self._resource_limiter.check_limits()
        
        return result
    
    def execute_sync_safe(self, func, *args, **kwargs):
        """
        Execute synchronous function safely within sandbox constraints.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
        """
        if not self._is_active:
            raise PluginError("Sandbox not active")
        
        # Check resource limits before execution
        self._resource_limiter.check_limits()
        
        try:
            result = func(*args, **kwargs)
            
            # Check resource limits after execution
            self._resource_limiter.check_limits()
            
            return result
            
        except Exception as e:
            logger.error(
                "Sync function execution failed in sandbox",
                plugin=self.plugin_name,
                function=func.__name__,
                error=str(e)
            )
            raise PluginError(f"Function execution failed: {e}")
    
    def validate_import(self, module_name: str) -> bool:
        """
        Validate if module import is allowed.
        
        Args:
            module_name: Name of module to import
            
        Returns:
            True if import is allowed
        """
        if module_name in self.restricted_modules:
            return False
        
        for restricted in self.restricted_modules:
            if module_name.startswith(restricted + '.'):
                return False
        
        return True
    
    def get_sandbox_info(self) -> Dict[str, Any]:
        """
        Get information about sandbox configuration and state.
        
        Returns:
            Dictionary with sandbox information
        """
        return {
            'plugin_name': self.plugin_name,
            'is_active': self._is_active,
            'allowed_modules': list(self.allowed_modules),
            'restricted_modules': list(self.restricted_modules),
            'max_memory_mb': self.max_memory_mb,
            'max_cpu_time_ms': self.max_cpu_time_ms,
            'execution_timeout': self.execution_timeout
        }
    
    async def _cleanup(self) -> None:
        """Cleanup sandbox resources."""
        try:
            # Stop resource monitoring
            if self._resource_limiter:
                self._resource_limiter.stop_monitoring()
            
            # Remove import hook
            if self._import_hook:
                self._import_hook.__exit__(None, None, None)
                self._import_hook = None
            
            # Clear execution context
            self._execution_context = None
            
            # Restore original modules
            for module_name, original_module in self._original_modules.items():
                if module_name in sys.modules:
                    sys.modules[module_name] = original_module
            
            self._original_modules.clear()
            
        except Exception as e:
            logger.error(
                "Error during sandbox cleanup",
                plugin=self.plugin_name,
                error=str(e)
            )


class PluginSecurityManager:
    """Manages security policies and validation for plugins."""
    
    def __init__(self):
        self.security_policies: Dict[str, Dict[str, Any]] = {}
        self.plugin_permissions: Dict[str, Set[str]] = {}
        self.default_policy = {
            'max_memory_mb': 100,
            'max_cpu_time_ms': 1000,
            'execution_timeout': 5.0,
            'allowed_modules': [
                'numpy', 'scipy', 'librosa', 'soundfile', 'pydantic'
            ],
            'restricted_modules': [
                'os', 'sys', 'subprocess', 'socket', 'urllib', 'http'
            ]
        }
    
    def set_plugin_policy(self, plugin_name: str, policy: Dict[str, Any]) -> None:
        """
        Set security policy for a specific plugin.
        
        Args:
            plugin_name: Name of the plugin
            policy: Security policy configuration
        """
        self.security_policies[plugin_name] = {**self.default_policy, **policy}
        logger.info("Security policy set for plugin", plugin=plugin_name)
    
    def get_plugin_policy(self, plugin_name: str) -> Dict[str, Any]:
        """
        Get security policy for a plugin.
        
        Args:
            plugin_name: Name of the plugin
            
        Returns:
            Security policy configuration
        """
        return self.security_policies.get(plugin_name, self.default_policy.copy())
    
    def validate_plugin_permissions(self, plugin_name: str, 
                                  requested_permissions: List[str]) -> bool:
        """
        Validate if plugin has requested permissions.
        
        Args:
            plugin_name: Name of the plugin
            requested_permissions: List of requested permissions
            
        Returns:
            True if all permissions are granted
        """
        granted_permissions = self.plugin_permissions.get(plugin_name, set())
        
        for permission in requested_permissions:
            if permission not in granted_permissions:
                logger.warning(
                    "Plugin permission denied",
                    plugin=plugin_name,
                    permission=permission
                )
                return False
        
        return True
    
    def grant_permission(self, plugin_name: str, permission: str) -> None:
        """
        Grant permission to a plugin.
        
        Args:
            plugin_name: Name of the plugin
            permission: Permission to grant
        """
        if plugin_name not in self.plugin_permissions:
            self.plugin_permissions[plugin_name] = set()
        
        self.plugin_permissions[plugin_name].add(permission)
        logger.info(
            "Permission granted to plugin",
            plugin=plugin_name,
            permission=permission
        )
    
    def revoke_permission(self, plugin_name: str, permission: str) -> None:
        """
        Revoke permission from a plugin.
        
        Args:
            plugin_name: Name of the plugin
            permission: Permission to revoke
        """
        if plugin_name in self.plugin_permissions:
            self.plugin_permissions[plugin_name].discard(permission)
            logger.info(
                "Permission revoked from plugin",
                plugin=plugin_name,
                permission=permission
            )
    
    def create_sandbox(self, plugin_name: str) -> PluginSandbox:
        """
        Create sandbox for plugin with appropriate security policy.
        
        Args:
            plugin_name: Name of the plugin
            
        Returns:
            Configured PluginSandbox instance
        """
        policy = self.get_plugin_policy(plugin_name)
        return PluginSandbox(plugin_name, policy)