"""
Integrated Multi-Input Audio Access System

This module provides an integrated system that combines all multi-input audio access
components into a cohesive, easy-to-use interface.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime

from .models import AudioDevice, AudioFrame, AudioProcessingConfig
from .interfaces import IMultiInputCapture
from .multi_input_access import (
    DynamicAudioInputDetector,
    SelectiveAudioAccessManager,
    MultiInputAudioCapture,
    InputDeviceManager,
    MultiInputSynchronizationCoordinator,
    InputQualityMonitor,
    HotPlugSupport,
    InputConfigurationVisualizationUI,
    InputConfiguration,
    InputDeviceStatus
)


class MultiInputAudioSystem(IMultiInputCapture):
    """
    Integrated multi-input audio access system that provides a unified interface
    for all multi-input audio functionality
    """
    
    def __init__(self, config: InputConfiguration):
        self.config = config
        self.logger = logging.getLogger(__name__ + ".MultiInputAudioSystem")
        
        # Initialize components
        self._detector = DynamicAudioInputDetector(config)
        self._access_manager = SelectiveAudioAccessManager(config)
        self._capture = MultiInputAudioCapture(config)
        self._device_manager = InputDeviceManager(config)
        self._sync_coordinator = MultiInputSynchronizationCoordinator(config)
        self._quality_monitor = InputQualityMonitor(config)
        self._hotplug_support = HotPlugSupport(config)
        self._visualization_ui = InputConfigurationVisualizationUI(config)
        
        # System state
        self._is_initialized = False
        self._is_running = False
        self._current_devices: List[AudioDevice] = []
        
        # Callbacks
        self._frame_callbacks: List[Callable[[str, AudioFrame], None]] = []
        self._sync_callbacks: List[Callable[[Dict[str, AudioFrame]], None]] = []
        self._status_callbacks: List[Callable[[str, InputDeviceStatus], None]] = []
        
        # Setup component interconnections
        self._setup_component_connections()
    
    def _setup_component_connections(self):
        """Setup connections between components"""
        # Connect detector to access manager
        self._detector.register_detection_callback(self._handle_device_detection)
        
        # Connect access manager to device manager
        self._access_manager.register_access_callback(self._handle_access_change)
        
        # Connect capture to quality monitor and sync coordinator
        self._capture.register_frame_callback(self._handle_captured_frame)
        
        # Connect quality monitor to device manager
        self._quality_monitor.set_device_manager(self._device_manager)
        
        # Connect hotplug support
        self._hotplug_support.set_components(
            self._detector, self._access_manager, self._device_manager, self._capture
        )
        
        # Connect visualization UI
        self._visualization_ui.set_components(self._device_manager, self._quality_monitor)
        
        # Connect sync coordinator callbacks
        self._sync_coordinator.register_sync_callback(self._handle_synchronized_frames)
        
        # Connect device manager callbacks
        self._device_manager.register_status_callback(self._handle_status_change)
    
    async def initialize(self) -> bool:
        """Initialize the multi-input audio system"""
        try:
            if self._is_initialized:
                self.logger.warning("System already initialized")
                return True
            
            self.logger.info("Initializing multi-input audio system")
            
            # Start device detection
            if not self._detector.start_detection():
                self.logger.error("Failed to start device detection")
                return False
            
            # Start quality monitoring if enabled
            if self.config.enable_quality_monitoring:
                if not self._quality_monitor.start_monitoring():
                    self.logger.error("Failed to start quality monitoring")
                    return False
            
            # Perform initial device scan
            initial_devices = self._detector.scan_devices_once()
            if initial_devices:
                self._handle_device_detection(initial_devices)
            
            self._is_initialized = True
            self.logger.info(f"Multi-input audio system initialized with {len(initial_devices)} devices")
            return True
            
        except Exception as e:
            self.logger.error(f"Error initializing system: {e}")
            return False
    
    async def shutdown(self):
        """Shutdown the multi-input audio system"""
        try:
            self.logger.info("Shutting down multi-input audio system")
            
            # Stop capture if running
            if self._is_running:
                await self.stop_capture()
            
            # Stop components
            self._detector.stop_detection()
            self._quality_monitor.stop_monitoring()
            
            self._is_initialized = False
            self.logger.info("Multi-input audio system shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
    
    # IMultiInputCapture interface implementation
    
    def scan_input_devices(self) -> List[Dict[str, Any]]:
        """Scan and return available input devices"""
        devices = self._detector.scan_devices_once()
        return [device.to_dict() for device in devices]
    
    def get_device_capabilities(self, device_id: str) -> Dict[str, Any]:
        """Get detailed capabilities of a specific device"""
        capabilities = self._detector.get_device_capabilities(device_id)
        return capabilities or {}
    
    def select_inputs(self, device_ids: List[str]) -> bool:
        """Select specific input devices for capture"""
        return self._access_manager.select_devices(device_ids)
    
    def enable_all_inputs(self) -> bool:
        """Enable all available input devices"""
        return self._access_manager.enable_all_devices()
    
    def start_capture(self, config: AudioProcessingConfig) -> bool:
        """Start multi-input audio capture"""
        try:
            if self._is_running:
                self.logger.warning("Capture already running")
                return True
            
            if not self._is_initialized:
                self.logger.error("System not initialized")
                return False
            
            # Get selected devices
            selected_devices = self._access_manager.get_selected_devices()
            if not selected_devices:
                self.logger.error("No devices selected for capture")
                return False
            
            # Setup synchronization for selected devices
            for device in selected_devices:
                self._sync_coordinator.add_input_device(device.device_id)
            
            # Start capture
            audio_config = {
                'sample_rate': config.sample_rate,
                'channels': config.channels,
                'bit_depth': config.bit_depth,
                'buffer_size': config.buffer_size
            }
            
            if not self._capture.start_capture(selected_devices, audio_config):
                self.logger.error("Failed to start capture")
                return False
            
            self._is_running = True
            self.logger.info(f"Started capture for {len(selected_devices)} devices")
            return True
            
        except Exception as e:
            self.logger.error(f"Error starting capture: {e}")
            return False
    
    def stop_capture(self) -> bool:
        """Stop audio capture"""
        try:
            if not self._is_running:
                return True
            
            # Stop capture
            if not self._capture.stop_capture():
                self.logger.error("Failed to stop capture")
                return False
            
            # Clear synchronization
            for device in self._current_devices:
                self._sync_coordinator.remove_input_device(device.device_id)
            
            self._is_running = False
            self.logger.info("Stopped audio capture")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping capture: {e}")
            return False
    
    def get_input_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all input devices"""
        status = {}
        
        # Get device manager status
        device_status = self._device_manager.get_all_device_status()
        
        # Get quality metrics
        quality_metrics = self._quality_monitor.get_all_quality_metrics()
        
        # Get capture status
        capture_status = self._capture.get_capture_status() if self._is_running else {}
        
        # Combine all status information
        for device_id in device_status:
            status[device_id] = {
                'device_status': {
                    'state': device_status[device_id].state.value,
                    'is_enabled': device_status[device_id].is_enabled,
                    'priority': device_status[device_id].priority,
                    'gain_db': device_status[device_id].gain_db,
                    'is_muted': device_status[device_id].is_muted,
                    'frames_captured': device_status[device_id].frames_captured,
                    'frames_dropped': device_status[device_id].frames_dropped,
                    'error_count': device_status[device_id].error_count
                },
                'quality_metrics': quality_metrics.get(device_id, {}),
                'capture_status': capture_status.get(device_id, {})
            }
        
        return status
    
    def set_input_gain(self, device_id: str, gain_db: float) -> bool:
        """Set input gain for specific device"""
        return self._device_manager.set_device_gain(device_id, gain_db)
    
    def mute_input(self, device_id: str, muted: bool) -> bool:
        """Mute/unmute specific input device"""
        return self._device_manager.mute_device(device_id, muted)
    
    def register_input_callback(self, callback: Callable[[str, AudioFrame], None]) -> bool:
        """Register callback for input audio data"""
        self._frame_callbacks.append(callback)
        return True
    
    # Additional system-specific methods
    
    def enable_device(self, device_id: str) -> bool:
        """Enable specific device"""
        return (self._access_manager.enable_device(device_id) and 
                self._device_manager.enable_device(device_id))
    
    def disable_device(self, device_id: str) -> bool:
        """Disable specific device"""
        return (self._access_manager.disable_device(device_id) and 
                self._device_manager.disable_device(device_id))
    
    def set_device_priority(self, device_id: str, priority: int) -> bool:
        """Set device priority"""
        return (self._access_manager.set_device_priority(device_id, priority) and 
                self._device_manager.set_device_priority(device_id, priority))
    
    def get_selected_devices(self) -> List[AudioDevice]:
        """Get currently selected devices"""
        return self._access_manager.get_selected_devices()
    
    def get_devices_by_priority(self) -> List[AudioDevice]:
        """Get devices sorted by priority"""
        return self._access_manager.get_devices_by_priority()
    
    def get_synchronization_status(self) -> Dict[str, Any]:
        """Get synchronization status"""
        return self._sync_coordinator.get_synchronization_status()
    
    def get_ui_data(self) -> Dict[str, Any]:
        """Get UI visualization data"""
        return self._visualization_ui.get_ui_data()
    
    def get_device_visualization_data(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Get visualization data for specific device"""
        return self._visualization_ui.get_device_visualization_data(device_id)
    
    def register_sync_callback(self, callback: Callable[[Dict[str, AudioFrame]], None]) -> bool:
        """Register callback for synchronized frames"""
        self._sync_callbacks.append(callback)
        return True
    
    def register_status_callback(self, callback: Callable[[str, InputDeviceStatus], None]) -> bool:
        """Register callback for device status changes"""
        self._status_callbacks.append(callback)
        return True
    
    def register_hotplug_callback(self, callback: Callable[[str, Optional[AudioDevice], bool], None]) -> bool:
        """Register callback for hot-plug events"""
        self._hotplug_support.register_hotplug_callback(callback)
        return True
    
    # Internal event handlers
    
    def _handle_device_detection(self, devices: List[AudioDevice]):
        """Handle device detection events"""
        self._current_devices = devices
        
        # Update access manager
        self._access_manager.set_available_devices(devices)
        
        # Add devices to device manager
        for device in devices:
            self._device_manager.add_device(device)
        
        self.logger.debug(f"Updated device list: {len(devices)} devices")
    
    def _handle_access_change(self, device_id: str, enabled: bool):
        """Handle access change events"""
        if enabled:
            self._device_manager.enable_device(device_id)
        else:
            self._device_manager.disable_device(device_id)
        
        self.logger.debug(f"Device {device_id} access changed: {enabled}")
    
    def _handle_captured_frame(self, device_id: str, frame: AudioFrame):
        """Handle captured audio frames"""
        # Update quality monitor
        self._quality_monitor.update_frame_quality(device_id, frame)
        
        # Record frame in device manager
        self._device_manager.record_device_frame(device_id, frame.timestamp)
        
        # Add to synchronization coordinator
        self._sync_coordinator.add_frame(device_id, frame)
        
        # Notify frame callbacks
        for callback in self._frame_callbacks:
            try:
                callback(device_id, frame)
            except Exception as e:
                self.logger.error(f"Error in frame callback: {e}")
    
    def _handle_synchronized_frames(self, frames: Dict[str, AudioFrame]):
        """Handle synchronized frames"""
        # Notify sync callbacks
        for callback in self._sync_callbacks:
            try:
                callback(frames)
            except Exception as e:
                self.logger.error(f"Error in sync callback: {e}")
    
    def _handle_status_change(self, device_id: str, status: InputDeviceStatus):
        """Handle device status changes"""
        # Notify status callbacks
        for callback in self._status_callbacks:
            try:
                callback(device_id, status)
            except Exception as e:
                self.logger.error(f"Error in status callback: {e}")
    
    # Properties
    
    @property
    def is_initialized(self) -> bool:
        """Check if system is initialized"""
        return self._is_initialized
    
    @property
    def is_running(self) -> bool:
        """Check if capture is running"""
        return self._is_running
    
    @property
    def device_count(self) -> int:
        """Get number of available devices"""
        return len(self._current_devices)
    
    @property
    def selected_device_count(self) -> int:
        """Get number of selected devices"""
        return len(self._access_manager.get_selected_devices())
    
    @property
    def hotplug_enabled(self) -> bool:
        """Check if hot-plug support is enabled"""
        return self._hotplug_support.is_enabled()


# Factory function for easy system creation
def create_multi_input_system(
    auto_detect: bool = True,
    enable_all_by_default: bool = True,
    enable_quality_monitoring: bool = True,
    enable_hot_plug: bool = True,
    sync_mode: str = "software_sync",
    **kwargs
) -> MultiInputAudioSystem:
    """
    Factory function to create a multi-input audio system with common configurations
    
    Args:
        auto_detect: Enable automatic device detection
        enable_all_by_default: Enable all detected devices by default
        enable_quality_monitoring: Enable quality monitoring
        enable_hot_plug: Enable hot-plug support
        sync_mode: Synchronization mode ("none", "timestamp", "software_sync")
        **kwargs: Additional configuration parameters
    
    Returns:
        Configured MultiInputAudioSystem instance
    """
    from .multi_input_access import SynchronizationMode
    
    # Map sync mode string to enum
    sync_mode_map = {
        "none": SynchronizationMode.NONE,
        "timestamp": SynchronizationMode.TIMESTAMP,
        "software_sync": SynchronizationMode.SOFTWARE_SYNC,
        "hardware_sync": SynchronizationMode.HARDWARE_SYNC
    }
    
    config = InputConfiguration(
        auto_detect_devices=auto_detect,
        enable_all_by_default=enable_all_by_default,
        enable_quality_monitoring=enable_quality_monitoring,
        enable_hot_plug=enable_hot_plug,
        sync_mode=sync_mode_map.get(sync_mode, SynchronizationMode.SOFTWARE_SYNC),
        **kwargs
    )
    
    return MultiInputAudioSystem(config)


# Example usage and testing
async def example_usage():
    """Example usage of the multi-input audio system"""
    # Create system with default configuration
    system = create_multi_input_system()
    
    # Register callbacks
    def on_frame(device_id: str, frame: AudioFrame):
        print(f"Frame from {device_id}: {frame.frame_size} samples")
    
    def on_sync_frames(frames: Dict[str, AudioFrame]):
        print(f"Synchronized frames from {len(frames)} devices")
    
    def on_status_change(device_id: str, status: InputDeviceStatus):
        print(f"Device {device_id} status: {status.state.value}")
    
    system.register_input_callback(on_frame)
    system.register_sync_callback(on_sync_frames)
    system.register_status_callback(on_status_change)
    
    try:
        # Initialize system
        if await system.initialize():
            print("System initialized successfully")
            
            # Get available devices
            devices = system.scan_input_devices()
            print(f"Found {len(devices)} input devices")
            
            # Create dummy audio config
            from .models import AudioProcessingConfig
            config = AudioProcessingConfig(
                config_id="test",
                name="Test Configuration"
            )
            
            # Start capture
            if system.start_capture(config):
                print("Capture started")
                
                # Run for a short time
                await asyncio.sleep(5.0)
                
                # Get status
                status = system.get_input_status()
                print(f"Input status: {len(status)} devices")
                
                # Stop capture
                system.stop_capture()
                print("Capture stopped")
        
        # Shutdown system
        await system.shutdown()
        print("System shutdown complete")
        
    except Exception as e:
        print(f"Error in example: {e}")
        await system.shutdown()


if __name__ == "__main__":
    # Run example
    asyncio.run(example_usage())