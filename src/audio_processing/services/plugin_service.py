"""
Plugin service for integrating plugins into the audio processing pipeline.

This service manages plugin execution within the audio processing chain,
providing seamless integration with the existing service architecture.
"""

import asyncio
from typing import Dict, List, Optional, Any
import structlog

from ..interfaces import IAudioService, IPluginInterface
from ..models import AudioFrame, ProcessingResult, AudioConfig, AudioMetrics
from ..base import BaseAudioProcessor
from ..plugin_manager import PluginManager
from ..plugin_sandbox import PluginSandbox, PluginSecurityManager
from ..exceptions import PluginError, ProcessingError

logger = structlog.get_logger(__name__)


class PluginService(BaseAudioProcessor):
    """
    Service for executing plugins in the audio processing pipeline.
    
    Manages plugin lifecycle, execution, and integration with the
    audio processing system.
    """
    
    def __init__(self, config: AudioConfig, plugin_manager: PluginManager):
        super().__init__("PluginService", config)
        self._plugin_manager = plugin_manager
        self._security_manager = PluginSecurityManager()
        self._active_plugins: Dict[str, IPluginInterface] = {}
        self._plugin_order: List[str] = []
        self._plugin_sandboxes: Dict[str, PluginSandbox] = {}
        self._plugin_metrics: Dict[str, AudioMetrics] = {}
        self._bypass_mode = False
    
    async def _initialize(self) -> None:
        """Initialize the plugin service."""
        logger.info("Initializing plugin service")
        
        # Ensure plugin manager is running
        if not self._plugin_manager.is_running:
            await self._plugin_manager.start()
        
        # Load default plugins if configured
        default_plugins = self._config.get('default_plugins', [])
        for plugin_name in default_plugins:
            try:
                await self.load_plugin(plugin_name)
            except Exception as e:
                logger.warning(
                    "Failed to load default plugin",
                    plugin=plugin_name,
                    error=str(e)
                )
    
    async def _cleanup(self) -> None:
        """Cleanup plugin service resources."""
        logger.info("Cleaning up plugin service")
        
        # Unload all plugins
        await self.unload_all_plugins()
        
        # Cleanup sandboxes
        for sandbox in self._plugin_sandboxes.values():
            try:
                await sandbox.__aexit__(None, None, None)
            except Exception as e:
                logger.error("Error cleaning up sandbox", error=str(e))
        
        self._plugin_sandboxes.clear()
    
    async def load_plugin(self, plugin_name: str, position: Optional[int] = None) -> bool:
        """
        Load and activate a plugin in the processing chain.
        
        Args:
            plugin_name: Name of plugin to load
            position: Position in processing chain (None for end)
            
        Returns:
            True if plugin loaded successfully
        """
        if plugin_name in self._active_plugins:
            logger.warning("Plugin already loaded", plugin=plugin_name)
            return True
        
        logger.info("Loading plugin into service", plugin=plugin_name)
        
        try:
            # Load plugin through manager
            success = await self._plugin_manager.load_plugin(plugin_name)
            if not success:
                return False
            
            # Get plugin instance
            plugin_instance = self._plugin_manager.get_plugin(plugin_name)
            if not plugin_instance:
                raise PluginError(f"Plugin instance not available: {plugin_name}")
            
            # Create sandbox for plugin
            sandbox = self._security_manager.create_sandbox(plugin_name)
            self._plugin_sandboxes[plugin_name] = sandbox
            
            # Add to active plugins
            self._active_plugins[plugin_name] = plugin_instance
            
            # Add to processing order
            if position is not None:
                self._plugin_order.insert(position, plugin_name)
            else:
                self._plugin_order.append(plugin_name)
            
            # Initialize metrics
            self._plugin_metrics[plugin_name] = AudioMetrics()
            
            logger.info(
                "Plugin loaded into service",
                plugin=plugin_name,
                position=len(self._plugin_order) - 1
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Failed to load plugin into service",
                plugin=plugin_name,
                error=str(e)
            )
            
            # Cleanup on failure
            if plugin_name in self._active_plugins:
                del self._active_plugins[plugin_name]
            if plugin_name in self._plugin_order:
                self._plugin_order.remove(plugin_name)
            if plugin_name in self._plugin_sandboxes:
                del self._plugin_sandboxes[plugin_name]
            
            return False
    
    async def unload_plugin(self, plugin_name: str) -> bool:
        """
        Unload and deactivate a plugin from the processing chain.
        
        Args:
            plugin_name: Name of plugin to unload
            
        Returns:
            True if plugin unloaded successfully
        """
        if plugin_name not in self._active_plugins:
            logger.warning("Plugin not loaded in service", plugin=plugin_name)
            return True
        
        logger.info("Unloading plugin from service", plugin=plugin_name)
        
        try:
            # Remove from processing order
            if plugin_name in self._plugin_order:
                self._plugin_order.remove(plugin_name)
            
            # Cleanup sandbox
            if plugin_name in self._plugin_sandboxes:
                sandbox = self._plugin_sandboxes[plugin_name]
                await sandbox.__aexit__(None, None, None)
                del self._plugin_sandboxes[plugin_name]
            
            # Remove from active plugins
            del self._active_plugins[plugin_name]
            
            # Remove metrics
            if plugin_name in self._plugin_metrics:
                del self._plugin_metrics[plugin_name]
            
            # Unload from manager
            await self._plugin_manager.unload_plugin(plugin_name)
            
            logger.info("Plugin unloaded from service", plugin=plugin_name)
            return True
            
        except Exception as e:
            logger.error(
                "Failed to unload plugin from service",
                plugin=plugin_name,
                error=str(e)
            )
            return False
    
    async def unload_all_plugins(self) -> Dict[str, bool]:
        """
        Unload all active plugins.
        
        Returns:
            Dictionary mapping plugin names to unload success status
        """
        results = {}
        
        # Unload in reverse order
        for plugin_name in reversed(self._plugin_order.copy()):
            results[plugin_name] = await self.unload_plugin(plugin_name)
        
        return results
    
    async def reorder_plugins(self, new_order: List[str]) -> bool:
        """
        Reorder plugins in the processing chain.
        
        Args:
            new_order: New plugin processing order
            
        Returns:
            True if reordering successful
        """
        # Validate that all plugins in new order are loaded
        for plugin_name in new_order:
            if plugin_name not in self._active_plugins:
                logger.error("Cannot reorder: plugin not loaded", plugin=plugin_name)
                return False
        
        # Validate that no plugins are missing
        if set(new_order) != set(self._plugin_order):
            logger.error("Cannot reorder: plugin list mismatch")
            return False
        
        self._plugin_order = new_order.copy()
        logger.info("Plugin order updated", order=self._plugin_order)
        return True
    
    def set_bypass_mode(self, bypass: bool) -> None:
        """
        Set bypass mode for all plugins.
        
        Args:
            bypass: True to bypass all plugins
        """
        self._bypass_mode = bypass
        logger.info("Plugin bypass mode set", bypass=bypass)
    
    def get_active_plugins(self) -> List[str]:
        """Get list of active plugin names in processing order."""
        return self._plugin_order.copy()
    
    def get_plugin_metrics(self) -> Dict[str, AudioMetrics]:
        """Get metrics for all active plugins."""
        return self._plugin_metrics.copy()
    
    async def _process_frame(self, frame: AudioFrame) -> AudioFrame:
        """
        Process audio frame through plugin chain.
        
        Args:
            frame: Input audio frame
            
        Returns:
            Processed audio frame
        """
        if self._bypass_mode or not self._plugin_order:
            return frame
        
        current_frame = frame
        
        # Process through each plugin in order
        for plugin_name in self._plugin_order:
            try:
                plugin = self._active_plugins[plugin_name]
                sandbox = self._plugin_sandboxes[plugin_name]
                
                # Process frame in sandbox
                async with sandbox:
                    if hasattr(plugin, 'process_frame'):
                        # Synchronous processing
                        processed_frame = sandbox.execute_sync_safe(
                            plugin.process_frame, 
                            current_frame
                        )
                    elif hasattr(plugin, 'process_frame_async'):
                        # Asynchronous processing
                        processed_frame = await sandbox.execute_safe(
                            plugin.process_frame_async(current_frame)
                        )
                    else:
                        logger.warning(
                            "Plugin has no process method",
                            plugin=plugin_name
                        )
                        continue
                
                # Update current frame for next plugin
                current_frame = processed_frame
                
                # Update plugin metrics
                self._update_plugin_metrics(plugin_name, True)
                
            except Exception as e:
                logger.error(
                    "Plugin processing failed",
                    plugin=plugin_name,
                    error=str(e)
                )
                
                # Update metrics with error
                self._update_plugin_metrics(plugin_name, False)
                
                # Continue with original frame (skip failed plugin)
                # In production, you might want different error handling strategies
                continue
        
        return current_frame
    
    def _update_plugin_metrics(self, plugin_name: str, success: bool) -> None:
        """Update metrics for a plugin."""
        if plugin_name not in self._plugin_metrics:
            self._plugin_metrics[plugin_name] = AudioMetrics()
        
        metrics = self._plugin_metrics[plugin_name]
        
        if success:
            metrics.frames_processed += 1
        else:
            metrics.frames_dropped += 1
    
    async def configure_plugin(self, plugin_name: str, 
                             parameters: Dict[str, Any]) -> bool:
        """
        Configure plugin parameters.
        
        Args:
            plugin_name: Name of plugin to configure
            parameters: Plugin parameters
            
        Returns:
            True if configuration successful
        """
        if plugin_name not in self._active_plugins:
            logger.error("Cannot configure: plugin not loaded", plugin=plugin_name)
            return False
        
        try:
            plugin = self._active_plugins[plugin_name]
            sandbox = self._plugin_sandboxes[plugin_name]
            
            async with sandbox:
                if hasattr(plugin, 'set_parameters'):
                    sandbox.execute_sync_safe(plugin.set_parameters, parameters)
                    logger.info("Plugin configured", plugin=plugin_name, parameters=parameters)
                    return True
                else:
                    logger.warning("Plugin does not support configuration", plugin=plugin_name)
                    return False
                    
        except Exception as e:
            logger.error(
                "Failed to configure plugin",
                plugin=plugin_name,
                error=str(e)
            )
            return False
    
    def get_plugin_parameters(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """
        Get current plugin parameters.
        
        Args:
            plugin_name: Name of plugin
            
        Returns:
            Plugin parameters if available
        """
        if plugin_name not in self._active_plugins:
            return None
        
        try:
            plugin = self._active_plugins[plugin_name]
            
            if hasattr(plugin, 'get_parameters'):
                return plugin.get_parameters()
            else:
                return None
                
        except Exception as e:
            logger.error(
                "Failed to get plugin parameters",
                plugin=plugin_name,
                error=str(e)
            )
            return None
    
    def get_service_status(self) -> Dict[str, Any]:
        """
        Get comprehensive service status.
        
        Returns:
            Dictionary with service status information
        """
        return {
            'active_plugins': len(self._active_plugins),
            'plugin_order': self._plugin_order.copy(),
            'bypass_mode': self._bypass_mode,
            'plugin_metrics': {
                name: metrics.model_dump() 
                for name, metrics in self._plugin_metrics.items()
            },
            'available_plugins': self._plugin_manager.list_available_plugins()
        }