"""
Plugin manager for the audio processing system.

This module provides the PluginManager class that handles dynamic loading,
unloading, and management of audio processing plugins.
"""

import asyncio
import importlib
import importlib.util
import sys
import os
from typing import Dict, List, Optional, Any, Type, Set
from pathlib import Path
import structlog

from .interfaces import IPluginInterface, IAudioService
from .models import AudioConfig, AudioFrame, ProcessingResult
from .exceptions import PluginError, ServiceError
from .base import BaseAsyncService
from .plugin_sandbox import PluginSandbox, PluginSecurityManager
from .plugin_registry import PluginRegistry, PluginMetadata, PluginVersion

logger = structlog.get_logger(__name__)


class PluginInfo:
    """Information about a loaded plugin."""
    
    def __init__(self, name: str, version: str, description: str, 
                 plugin_class: Type[IPluginInterface], module_path: str):
        self.name = name
        self.version = version
        self.description = description
        self.plugin_class = plugin_class
        self.module_path = module_path
        self.instance: Optional[IPluginInterface] = None
        self.is_loaded = False
        self.dependencies: List[str] = []
        self.load_time: Optional[float] = None





class PluginManager(BaseAsyncService):
    """
    Manages audio processing plugins with hot loading/unloading capabilities.
    
    Provides plugin discovery, loading, dependency management, and sandboxing.
    """
    
    def __init__(self, config: AudioConfig, plugin_dirs: List[str] = None):
        super().__init__("PluginManager", config.model_dump())
        self._config = config
        self._plugin_dirs = plugin_dirs or ["plugins", "src/plugins"]
        self._registry = PluginRegistry("plugin_registry.json")
        self._security_manager = PluginSecurityManager()
        self._loaded_plugins: Dict[str, IPluginInterface] = {}
        self._plugin_modules: Dict[str, Any] = {}
        self._hot_reload_enabled = True
        self._file_watchers: Dict[str, Any] = {}
        self._plugin_info_cache: Dict[str, PluginInfo] = {}
        self._watch_task: Optional[asyncio.Task] = None
    
    async def _initialize(self) -> None:
        """Initialize the plugin manager."""
        logger.info("Initializing plugin manager")
        
        # Create plugin directories if they don't exist
        for plugin_dir in self._plugin_dirs:
            Path(plugin_dir).mkdir(parents=True, exist_ok=True)
        
        # Discover and register plugins
        await self._discover_plugins()
        
        # Start file watching for hot reload
        if self._hot_reload_enabled:
            self._watch_task = asyncio.create_task(self._watch_plugin_files())
    
    async def _cleanup(self) -> None:
        """Cleanup plugin manager resources."""
        logger.info("Cleaning up plugin manager")
        
        # Unload all plugins
        await self.unload_all_plugins()
        
        # Stop file watching
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
        
        # Stop file watchers
        for watcher in self._file_watchers.values():
            if hasattr(watcher, 'stop'):
                watcher.stop()
        
        self._file_watchers.clear()
    
    async def discover_plugins(self) -> List[str]:
        """
        Discover available plugins in plugin directories.
        
        Returns:
            List of discovered plugin names
        """
        return await self._discover_plugins()
    
    async def load_plugin(self, plugin_name: str) -> bool:
        """
        Load a specific plugin.
        
        Args:
            plugin_name: Name of plugin to load
            
        Returns:
            True if plugin loaded successfully
        """
        plugin_info = self._registry.get_plugin(plugin_name)
        if not plugin_info:
            raise PluginError(f"Plugin not found: {plugin_name}")
        
        if plugin_info.is_loaded:
            logger.warning("Plugin already loaded", plugin=plugin_name)
            return True
        
        logger.info("Loading plugin", plugin=plugin_name)
        
        try:
            # Check dependencies
            await self._check_dependencies(plugin_info)
            
            # Load plugin in sandbox
            sandbox = self._security_manager.create_sandbox(plugin_name)
            async with sandbox:
                # Create plugin instance
                plugin_instance = plugin_info.plugin_class()
                
                # Initialize plugin
                await plugin_instance.initialize(self._config)
                
                # Store instance
                plugin_info.instance = plugin_instance
                plugin_info.is_loaded = True
                self._loaded_plugins[plugin_name] = plugin_instance
                
                logger.info("Plugin loaded successfully", plugin=plugin_name)
                return True
                
        except Exception as e:
            logger.error(
                "Failed to load plugin",
                plugin=plugin_name,
                error=str(e)
            )
            raise PluginError(f"Failed to load plugin {plugin_name}: {e}")
    
    async def unload_plugin(self, plugin_name: str) -> bool:
        """
        Unload a specific plugin.
        
        Args:
            plugin_name: Name of plugin to unload
            
        Returns:
            True if plugin unloaded successfully
        """
        plugin_info = self._registry.get_plugin(plugin_name)
        if not plugin_info or not plugin_info.is_loaded:
            logger.warning("Plugin not loaded", plugin=plugin_name)
            return True
        
        logger.info("Unloading plugin", plugin=plugin_name)
        
        try:
            # Check if other plugins depend on this one
            dependents = self._get_dependent_plugins(plugin_name)
            if dependents:
                raise PluginError(
                    f"Cannot unload plugin {plugin_name}: "
                    f"required by {', '.join(dependents)}"
                )
            
            # Cleanup plugin
            if plugin_info.instance:
                await plugin_info.instance.cleanup()
            
            # Remove from loaded plugins
            plugin_info.instance = None
            plugin_info.is_loaded = False
            
            if plugin_name in self._loaded_plugins:
                del self._loaded_plugins[plugin_name]
            
            # Remove module from sys.modules for hot reload
            if plugin_name in self._plugin_modules:
                module = self._plugin_modules[plugin_name]
                if hasattr(module, '__file__'):
                    module_name = module.__name__
                    if module_name in sys.modules:
                        del sys.modules[module_name]
                del self._plugin_modules[plugin_name]
            
            logger.info("Plugin unloaded successfully", plugin=plugin_name)
            return True
            
        except Exception as e:
            logger.error(
                "Failed to unload plugin",
                plugin=plugin_name,
                error=str(e)
            )
            raise PluginError(f"Failed to unload plugin {plugin_name}: {e}")
    
    async def reload_plugin(self, plugin_name: str) -> bool:
        """
        Reload a plugin (unload then load).
        
        Args:
            plugin_name: Name of plugin to reload
            
        Returns:
            True if plugin reloaded successfully
        """
        logger.info("Reloading plugin", plugin=plugin_name)
        
        try:
            # Unload if currently loaded
            if plugin_name in self._loaded_plugins:
                await self.unload_plugin(plugin_name)
            
            # Rediscover plugin (in case file changed)
            await self._discover_single_plugin(plugin_name)
            
            # Load plugin
            return await self.load_plugin(plugin_name)
            
        except Exception as e:
            logger.error(
                "Failed to reload plugin",
                plugin=plugin_name,
                error=str(e)
            )
            raise PluginError(f"Failed to reload plugin {plugin_name}: {e}")
    
    async def load_all_plugins(self) -> Dict[str, bool]:
        """
        Load all discovered plugins in dependency order.
        
        Returns:
            Dictionary mapping plugin names to load success status
        """
        logger.info("Loading all plugins")
        
        results = {}
        load_order = self._registry.get_load_order()
        
        for plugin_name in load_order:
            try:
                results[plugin_name] = await self.load_plugin(plugin_name)
            except Exception as e:
                logger.error(
                    "Failed to load plugin in batch",
                    plugin=plugin_name,
                    error=str(e)
                )
                results[plugin_name] = False
        
        loaded_count = sum(1 for success in results.values() if success)
        logger.info(
            "Batch plugin loading completed",
            loaded=loaded_count,
            total=len(results)
        )
        
        return results
    
    async def unload_all_plugins(self) -> Dict[str, bool]:
        """
        Unload all loaded plugins in reverse dependency order.
        
        Returns:
            Dictionary mapping plugin names to unload success status
        """
        logger.info("Unloading all plugins")
        
        results = {}
        load_order = self._registry.get_load_order()
        unload_order = list(reversed(load_order))
        
        for plugin_name in unload_order:
            if plugin_name in self._loaded_plugins:
                try:
                    results[plugin_name] = await self.unload_plugin(plugin_name)
                except Exception as e:
                    logger.error(
                        "Failed to unload plugin in batch",
                        plugin=plugin_name,
                        error=str(e)
                    )
                    results[plugin_name] = False
        
        return results
    
    def get_plugin(self, plugin_name: str) -> Optional[IPluginInterface]:
        """
        Get loaded plugin instance by name.
        
        Args:
            plugin_name: Name of plugin
            
        Returns:
            Plugin instance if loaded, None otherwise
        """
        return self._loaded_plugins.get(plugin_name)
    
    def get_plugin_info(self, plugin_name: str) -> Optional[PluginInfo]:
        """Get plugin info by name."""
        return self._plugin_info_cache.get(plugin_name)
    
    def list_loaded_plugins(self) -> List[str]:
        """Get list of currently loaded plugin names."""
        return list(self._loaded_plugins.keys())
    
    def list_available_plugins(self) -> List[Dict[str, Any]]:
        """
        Get list of all available plugins with metadata.
        
        Returns:
            List of plugin info dictionaries
        """
        plugins = []
        
        # Get from registry
        registry_plugins = self._registry.list_plugins()
        for metadata in registry_plugins:
            plugin_info = self._plugin_info_cache.get(metadata.name)
            plugins.append({
                'name': metadata.name,
                'version': str(metadata.version),
                'description': metadata.description,
                'author': metadata.author,
                'license': metadata.license,
                'categories': metadata.categories,
                'keywords': metadata.keywords,
                'loaded': plugin_info.is_loaded if plugin_info else False,
                'dependencies': [dep.name for dep in metadata.dependencies],
                'module_path': plugin_info.module_path if plugin_info else None
            })
        
        return plugins
    
    def get_plugin_status(self) -> Dict[str, Any]:
        """
        Get comprehensive plugin system status.
        
        Returns:
            Dictionary with plugin system status information
        """
        return {
            'total_plugins': len(self._registry.list_plugins()),
            'loaded_plugins': len(self._loaded_plugins),
            'plugin_directories': self._plugin_dirs,
            'hot_reload_enabled': self._hot_reload_enabled,
            'plugins': self.list_available_plugins()
        }
    
    async def _discover_plugins(self) -> List[str]:
        """Discover plugins in all plugin directories."""
        discovered = []
        
        for plugin_dir in self._plugin_dirs:
            plugin_path = Path(plugin_dir)
            if not plugin_path.exists():
                continue
            
            # Look for Python files
            for py_file in plugin_path.glob("*.py"):
                if py_file.name.startswith("__"):
                    continue
                
                plugin_name = py_file.stem
                try:
                    await self._load_plugin_module(str(py_file), plugin_name)
                    discovered.append(plugin_name)
                except Exception as e:
                    logger.error(
                        "Failed to discover plugin",
                        file=str(py_file),
                        error=str(e)
                    )
        
        logger.info("Plugin discovery completed", discovered=len(discovered))
        return discovered
    
    async def _discover_single_plugin(self, plugin_name: str) -> bool:
        """Discover a single plugin by name."""
        for plugin_dir in self._plugin_dirs:
            plugin_file = Path(plugin_dir) / f"{plugin_name}.py"
            if plugin_file.exists():
                try:
                    await self._load_plugin_module(str(plugin_file), plugin_name)
                    return True
                except Exception as e:
                    logger.error(
                        "Failed to rediscover plugin",
                        plugin=plugin_name,
                        error=str(e)
                    )
        return False
    
    async def _load_plugin_module(self, file_path: str, plugin_name: str) -> None:
        """Load plugin module and register plugin class."""
        spec = importlib.util.spec_from_file_location(plugin_name, file_path)
        if not spec or not spec.loader:
            raise PluginError(f"Cannot load module spec for {file_path}")
        
        module = importlib.util.module_from_spec(spec)
        self._plugin_modules[plugin_name] = module
        
        # Execute module
        spec.loader.exec_module(module)
        
        # Find plugin class
        plugin_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and 
                issubclass(attr, IPluginInterface) and 
                attr != IPluginInterface):
                plugin_class = attr
                break
        
        if not plugin_class:
            raise PluginError(f"No plugin class found in {file_path}")
        
        # Get plugin metadata
        temp_instance = plugin_class()
        plugin_info_dict = temp_instance.get_plugin_info()
        dependencies = temp_instance.get_required_dependencies()
        
        # Create plugin info
        plugin_info = PluginInfo(
            name=plugin_info_dict.get('name', plugin_name),
            version=plugin_info_dict.get('version', '1.0.0'),
            description=plugin_info_dict.get('description', ''),
            plugin_class=plugin_class,
            module_path=file_path
        )
        plugin_info.dependencies = dependencies
        
        # Cache plugin info
        self._plugin_info_cache[plugin_name] = plugin_info
        
        # Create registry metadata
        registry_metadata = PluginMetadata(
            name=plugin_info.name,
            version=PluginVersion.from_string(plugin_info.version),
            description=plugin_info.description,
            author=plugin_info_dict.get('author', 'Unknown'),
            license=plugin_info_dict.get('license', 'Unknown'),
            homepage=plugin_info_dict.get('homepage'),
            repository=plugin_info_dict.get('repository'),
            keywords=plugin_info_dict.get('keywords', []),
            categories=plugin_info_dict.get('categories', []),
            entry_point=plugin_info_dict.get('entry_point', 'main'),
            min_system_version=plugin_info_dict.get('min_system_version')
        )
        
        # Register in registry
        self._registry.register_plugin(registry_metadata, file_path)
    
    async def _check_dependencies(self, plugin_info: PluginInfo) -> None:
        """Check if plugin dependencies are satisfied."""
        for dep in plugin_info.dependencies:
            dep_plugin = self._registry.get_plugin(dep)
            if not dep_plugin:
                raise PluginError(
                    f"Dependency not found: {dep} (required by {plugin_info.name})"
                )
            
            if not dep_plugin.is_loaded:
                # Try to load dependency
                await self.load_plugin(dep)
    
    def _get_dependent_plugins(self, plugin_name: str) -> List[str]:
        """Get list of plugins that depend on the given plugin."""
        dependents = []
        for plugin_info in self._plugin_info_cache.values():
            if plugin_name in plugin_info.dependencies and plugin_info.is_loaded:
                dependents.append(plugin_info.name)
        return dependents
    
    async def _watch_plugin_files(self) -> None:
        """Watch plugin files for changes and trigger hot reload."""
        try:
            import watchdog
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            logger.warning("Watchdog not available, hot reload disabled")
            return
        
        class PluginFileHandler(FileSystemEventHandler):
            def __init__(self, plugin_manager):
                self.plugin_manager = plugin_manager
            
            def on_modified(self, event):
                if event.is_directory:
                    return
                
                if event.src_path.endswith('.py'):
                    plugin_name = Path(event.src_path).stem
                    logger.info("Plugin file changed, triggering reload", 
                              plugin=plugin_name, file=event.src_path)
                    
                    # Schedule reload
                    asyncio.create_task(self._handle_file_change(plugin_name))
            
            async def _handle_file_change(self, plugin_name: str):
                """Handle plugin file change."""
                try:
                    if plugin_name in self.plugin_manager._loaded_plugins:
                        await self.plugin_manager.reload_plugin(plugin_name)
                        logger.info("Plugin hot reloaded", plugin=plugin_name)
                except Exception as e:
                    logger.error("Hot reload failed", plugin=plugin_name, error=str(e))
        
        observer = Observer()
        handler = PluginFileHandler(self)
        
        # Watch all plugin directories
        for plugin_dir in self._plugin_dirs:
            if Path(plugin_dir).exists():
                observer.schedule(handler, plugin_dir, recursive=False)
                logger.debug("Watching plugin directory", directory=plugin_dir)
        
        observer.start()
        
        try:
            while self._is_running:
                await asyncio.sleep(1)
        finally:
            observer.stop()
            observer.join()
    
    def enable_hot_reload(self, enabled: bool = True) -> None:
        """
        Enable or disable hot reload functionality.
        
        Args:
            enabled: Whether to enable hot reload
        """
        self._hot_reload_enabled = enabled
        logger.info("Hot reload enabled" if enabled else "Hot reload disabled")
    
    def get_plugin_registry(self) -> PluginRegistry:
        """Get the plugin registry instance."""
        return self._registry
    
    def get_security_manager(self) -> PluginSecurityManager:
        """Get the security manager instance."""
        return self._security_manager