"""
Audio Device Manager

Comprehensive audio device management system with discovery, validation, monitoring,
hot-plug detection, and configuration persistence capabilities.
"""

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable, Set
from dataclasses import dataclass, asdict
from enum import Enum
import logging

from .models import AudioDevice, DeviceType
from .interfaces import IPluggableComponent, ComponentState


class DeviceStatus(Enum):
    """Device status enumeration"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
    DISCONNECTED = "disconnected"
    INITIALIZING = "initializing"
    UNKNOWN = "unknown"


class HealthStatus(Enum):
    """Device health status"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class DeviceHealthInfo:
    """Device health information"""
    status: HealthStatus
    last_check: datetime
    error_count: int = 0
    warning_count: int = 0
    latency_ms: float = 0.0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    temperature: Optional[float] = None
    issues: List[str] = None
    
    def __post_init__(self):
        if self.issues is None:
            self.issues = []


@dataclass
class DeviceConfiguration:
    """Device configuration settings"""
    device_id: str
    enabled: bool = True
    sample_rate: int = 48000
    bit_depth: int = 24
    channels: int = 2
    buffer_size: int = 256
    gain_db: float = 0.0
    muted: bool = False
    priority: int = 0
    custom_settings: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.custom_settings is None:
            self.custom_settings = {}


class AudioDeviceDiscovery:
    """Audio device discovery and validation functionality"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._discovery_callbacks: List[Callable[[List[AudioDevice]], None]] = []
    
    def discover_devices(self) -> List[AudioDevice]:
        """Discover all available audio devices"""
        devices = []
        
        try:
            # Simulate device discovery - in real implementation would use platform-specific APIs
            # like WASAPI on Windows, CoreAudio on macOS, ALSA/PulseAudio on Linux
            
            # Mock input devices
            input_devices = [
                AudioDevice(
                    device_id="input_0",
                    name="Built-in Microphone",
                    device_type=DeviceType.MICROPHONE,
                    is_input=True,
                    is_output=False,
                    max_input_channels=2,
                    supported_sample_rates=[44100, 48000, 96000],
                    supported_bit_depths=[16, 24, 32],
                    manufacturer="Apple",
                    model="Built-in"
                ),
                AudioDevice(
                    device_id="input_1",
                    name="USB Audio Interface",
                    device_type=DeviceType.USB_AUDIO,
                    is_input=True,
                    is_output=True,
                    max_input_channels=8,
                    max_output_channels=8,
                    supported_sample_rates=[44100, 48000, 88200, 96000, 192000],
                    supported_bit_depths=[16, 24, 32],
                    manufacturer="Focusrite",
                    model="Scarlett 18i20"
                )
            ]
            
            # Mock output devices
            output_devices = [
                AudioDevice(
                    device_id="output_0",
                    name="Built-in Speakers",
                    device_type=DeviceType.SPEAKER,
                    is_input=False,
                    is_output=True,
                    max_output_channels=2,
                    supported_sample_rates=[44100, 48000, 96000],
                    supported_bit_depths=[16, 24, 32],
                    manufacturer="Apple",
                    model="Built-in"
                ),
                AudioDevice(
                    device_id="output_1",
                    name="Studio Monitors",
                    device_type=DeviceType.SPEAKER,
                    is_input=False,
                    is_output=True,
                    max_output_channels=2,
                    supported_sample_rates=[44100, 48000, 96000, 192000],
                    supported_bit_depths=[16, 24, 32],
                    manufacturer="KRK",
                    model="Rokit 5"
                )
            ]
            
            devices.extend(input_devices)
            devices.extend(output_devices)
            
            # Validate discovered devices
            validated_devices = []
            for device in devices:
                if self._validate_device(device):
                    validated_devices.append(device)
                    self.logger.info(f"Discovered and validated device: {device.name}")
                else:
                    self.logger.warning(f"Device validation failed: {device.name}")
            
            # Notify discovery callbacks
            for callback in self._discovery_callbacks:
                try:
                    callback(validated_devices)
                except Exception as e:
                    self.logger.error(f"Error in discovery callback: {e}")
            
            return validated_devices
            
        except Exception as e:
            self.logger.error(f"Device discovery failed: {e}")
            return []
    
    def _validate_device(self, device: AudioDevice) -> bool:
        """Validate device capabilities and availability"""
        try:
            # Check basic device properties
            if not device.device_id or not device.name:
                return False
            
            # Validate sample rates
            if not device.supported_sample_rates or len(device.supported_sample_rates) == 0:
                return False
            
            # Validate bit depths
            if not device.supported_bit_depths or len(device.supported_bit_depths) == 0:
                return False
            
            # Check channel configuration
            if device.is_input and device.max_input_channels <= 0:
                return False
            if device.is_output and device.max_output_channels <= 0:
                return False
            
            # Simulate device availability check
            device.is_available = True
            device.is_connected = True
            device.last_seen = datetime.now()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Device validation error for {device.name}: {e}")
            return False
    
    def register_discovery_callback(self, callback: Callable[[List[AudioDevice]], None]):
        """Register callback for device discovery events"""
        self._discovery_callbacks.append(callback)
    
    def unregister_discovery_callback(self, callback: Callable[[List[AudioDevice]], None]):
        """Unregister discovery callback"""
        if callback in self._discovery_callbacks:
            self._discovery_callbacks.remove(callback)


class DeviceHealthMonitor:
    """Device health monitoring and status tracking"""
    
    def __init__(self, check_interval: float = 5.0):
        self.check_interval = check_interval
        self.logger = logging.getLogger(__name__)
        self._health_info: Dict[str, DeviceHealthInfo] = {}
        self._monitoring_active = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._health_callbacks: List[Callable[[str, DeviceHealthInfo], None]] = []
    
    def start_monitoring(self, devices: List[AudioDevice]):
        """Start health monitoring for devices"""
        if self._monitoring_active:
            return
        
        self._monitoring_active = True
        
        # Initialize health info for all devices
        for device in devices:
            self._health_info[device.device_id] = DeviceHealthInfo(
                status=HealthStatus.UNKNOWN,
                last_check=datetime.now()
            )
        
        # Start monitoring thread
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        self.logger.info(f"Started health monitoring for {len(devices)} devices")
    
    def stop_monitoring(self):
        """Stop health monitoring"""
        self._monitoring_active = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
        self.logger.info("Stopped health monitoring")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self._monitoring_active:
            try:
                for device_id in list(self._health_info.keys()):
                    self._check_device_health(device_id)
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(1.0)
    
    def _check_device_health(self, device_id: str):
        """Check health of a specific device"""
        try:
            health_info = self._health_info.get(device_id)
            if not health_info:
                return
            
            # Simulate health checks - in real implementation would check:
            # - Device connectivity
            # - Latency measurements
            # - Error rates
            # - Resource usage
            
            old_status = health_info.status
            
            # Mock health check logic
            import random
            health_score = random.uniform(0.7, 1.0)  # Simulate health score
            
            if health_score > 0.9:
                health_info.status = HealthStatus.HEALTHY
                health_info.issues.clear()
            elif health_score > 0.7:
                health_info.status = HealthStatus.WARNING
                health_info.issues = ["Minor performance degradation detected"]
                health_info.warning_count += 1
            else:
                health_info.status = HealthStatus.CRITICAL
                health_info.issues = ["Significant performance issues detected"]
                health_info.error_count += 1
            
            # Update metrics
            health_info.last_check = datetime.now()
            health_info.latency_ms = random.uniform(1.0, 10.0)
            health_info.cpu_usage = random.uniform(5.0, 25.0)
            health_info.memory_usage = random.uniform(10.0, 50.0)
            
            # Notify callbacks if status changed
            if old_status != health_info.status:
                for callback in self._health_callbacks:
                    try:
                        callback(device_id, health_info)
                    except Exception as e:
                        self.logger.error(f"Error in health callback: {e}")
            
        except Exception as e:
            self.logger.error(f"Health check failed for device {device_id}: {e}")
    
    def get_device_health(self, device_id: str) -> Optional[DeviceHealthInfo]:
        """Get health information for a device"""
        return self._health_info.get(device_id)
    
    def get_all_health_info(self) -> Dict[str, DeviceHealthInfo]:
        """Get health information for all monitored devices"""
        return self._health_info.copy()
    
    def register_health_callback(self, callback: Callable[[str, DeviceHealthInfo], None]):
        """Register callback for health status changes"""
        self._health_callbacks.append(callback)
    
    def unregister_health_callback(self, callback: Callable[[str, DeviceHealthInfo], None]):
        """Unregister health callback"""
        if callback in self._health_callbacks:
            self._health_callbacks.remove(callback)


class HotPlugDetector:
    """Hot-plug detection for device connection/disconnection events"""
    
    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        self.logger = logging.getLogger(__name__)
        self._known_devices: Set[str] = set()
        self._detection_active = False
        self._detector_thread: Optional[threading.Thread] = None
        self._hotplug_callbacks: List[Callable[[str, str, AudioDevice], None]] = []  # event_type, device_id, device
        self._discovery = AudioDeviceDiscovery()
    
    def start_detection(self):
        """Start hot-plug detection"""
        if self._detection_active:
            return
        
        self._detection_active = True
        
        # Initialize known devices
        current_devices = self._discovery.discover_devices()
        self._known_devices = {device.device_id for device in current_devices}
        
        # Start detection thread
        self._detector_thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._detector_thread.start()
        
        self.logger.info("Started hot-plug detection")
    
    def stop_detection(self):
        """Stop hot-plug detection"""
        self._detection_active = False
        if self._detector_thread and self._detector_thread.is_alive():
            self._detector_thread.join(timeout=1.0)
        self.logger.info("Stopped hot-plug detection")
    
    def _detection_loop(self):
        """Main detection loop"""
        while self._detection_active:
            try:
                current_devices = self._discovery.discover_devices()
                current_device_ids = {device.device_id for device in current_devices}
                
                # Check for newly connected devices
                new_devices = current_device_ids - self._known_devices
                for device_id in new_devices:
                    device = next((d for d in current_devices if d.device_id == device_id), None)
                    if device:
                        self._notify_hotplug_event("connected", device_id, device)
                        self.logger.info(f"Device connected: {device.name}")
                
                # Check for disconnected devices
                disconnected_devices = self._known_devices - current_device_ids
                for device_id in disconnected_devices:
                    # Create a placeholder device for disconnection event
                    placeholder_device = AudioDevice(
                        device_id=device_id,
                        name="Disconnected Device",
                        device_type=DeviceType.UNKNOWN,
                        is_input=False,
                        is_output=False,
                        is_available=False,
                        is_connected=False
                    )
                    self._notify_hotplug_event("disconnected", device_id, placeholder_device)
                    self.logger.info(f"Device disconnected: {device_id}")
                
                # Update known devices
                self._known_devices = current_device_ids
                
                time.sleep(self.poll_interval)
                
            except Exception as e:
                self.logger.error(f"Error in hot-plug detection loop: {e}")
                time.sleep(1.0)
    
    def _notify_hotplug_event(self, event_type: str, device_id: str, device: AudioDevice):
        """Notify callbacks about hot-plug events"""
        for callback in self._hotplug_callbacks:
            try:
                callback(event_type, device_id, device)
            except Exception as e:
                self.logger.error(f"Error in hot-plug callback: {e}")
    
    def register_hotplug_callback(self, callback: Callable[[str, str, AudioDevice], None]):
        """Register callback for hot-plug events"""
        self._hotplug_callbacks.append(callback)
    
    def unregister_hotplug_callback(self, callback: Callable[[str, str, AudioDevice], None]):
        """Unregister hot-plug callback"""
        if callback in self._hotplug_callbacks:
            self._hotplug_callbacks.remove(callback)


class DeviceConfigurationManager:
    """Device configuration management and persistence"""
    
    def __init__(self, config_dir: str = "device_configs"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        self.logger = logging.getLogger(__name__)
        self._configurations: Dict[str, DeviceConfiguration] = {}
        self._config_callbacks: List[Callable[[str, DeviceConfiguration], None]] = []
    
    def load_configurations(self) -> Dict[str, DeviceConfiguration]:
        """Load all device configurations from disk"""
        try:
            config_file = self.config_dir / "device_configs.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
                
                for device_id, config_dict in config_data.items():
                    config = DeviceConfiguration(**config_dict)
                    self._configurations[device_id] = config
                
                self.logger.info(f"Loaded {len(self._configurations)} device configurations")
            
            return self._configurations.copy()
            
        except Exception as e:
            self.logger.error(f"Failed to load device configurations: {e}")
            return {}
    
    def save_configurations(self) -> bool:
        """Save all device configurations to disk"""
        try:
            config_file = self.config_dir / "device_configs.json"
            config_data = {}
            
            for device_id, config in self._configurations.items():
                config_data[device_id] = asdict(config)
            
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            self.logger.info(f"Saved {len(self._configurations)} device configurations")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save device configurations: {e}")
            return False
    
    def get_device_configuration(self, device_id: str) -> Optional[DeviceConfiguration]:
        """Get configuration for a specific device"""
        return self._configurations.get(device_id)
    
    def set_device_configuration(self, device_id: str, config: DeviceConfiguration) -> bool:
        """Set configuration for a specific device"""
        try:
            old_config = self._configurations.get(device_id)
            self._configurations[device_id] = config
            
            # Notify callbacks
            for callback in self._config_callbacks:
                try:
                    callback(device_id, config)
                except Exception as e:
                    self.logger.error(f"Error in configuration callback: {e}")
            
            # Auto-save configurations
            self.save_configurations()
            
            self.logger.info(f"Updated configuration for device: {device_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set device configuration: {e}")
            return False
    
    def create_default_configuration(self, device: AudioDevice) -> DeviceConfiguration:
        """Create default configuration for a device"""
        return DeviceConfiguration(
            device_id=device.device_id,
            enabled=True,
            sample_rate=48000 if 48000 in device.supported_sample_rates else device.supported_sample_rates[0],
            bit_depth=24 if 24 in device.supported_bit_depths else device.supported_bit_depths[0],
            channels=min(device.max_input_channels or device.max_output_channels or 2, 2),
            buffer_size=256,
            gain_db=0.0,
            muted=False,
            priority=0
        )
    
    def register_config_callback(self, callback: Callable[[str, DeviceConfiguration], None]):
        """Register callback for configuration changes"""
        self._config_callbacks.append(callback)
    
    def unregister_config_callback(self, callback: Callable[[str, DeviceConfiguration], None]):
        """Unregister configuration callback"""
        if callback in self._config_callbacks:
            self._config_callbacks.remove(callback)


class DeviceManager(IPluggableComponent):
    """
    Comprehensive audio device manager with discovery, validation, monitoring,
    hot-plug detection, and configuration management capabilities.
    
    Implements requirements: 1.1, 1.2, 4.1, 6.1, 6.2
    """
    
    def __init__(self, config_dir: str = "device_configs"):
        self.logger = logging.getLogger(__name__)
        self._state = ComponentState.UNINITIALIZED
        
        # Core components
        self._discovery = AudioDeviceDiscovery()
        self._health_monitor = DeviceHealthMonitor()
        self._hotplug_detector = HotPlugDetector()
        self._config_manager = DeviceConfigurationManager(config_dir)
        
        # Device storage
        self._devices: Dict[str, AudioDevice] = {}
        self._device_status: Dict[str, DeviceStatus] = {}
        
        # Default devices
        self._default_input_device: Optional[str] = None
        self._default_output_device: Optional[str] = None
        
        # Callbacks
        self._device_callbacks: List[Callable[[str, str, AudioDevice], None]] = []  # event_type, device_id, device
        
        # Setup internal callbacks
        self._setup_callbacks()
    
    def _setup_callbacks(self):
        """Setup internal callbacks between components"""
        # Discovery callbacks
        self._discovery.register_discovery_callback(self._on_devices_discovered)
        
        # Hot-plug callbacks
        self._hotplug_detector.register_hotplug_callback(self._on_hotplug_event)
        
        # Health monitoring callbacks
        self._health_monitor.register_health_callback(self._on_health_changed)
        
        # Configuration callbacks
        self._config_manager.register_config_callback(self._on_config_changed)
    
    # IPluggableComponent interface implementation
    
    def get_component_info(self):
        """Get component information"""
        from .interfaces import ComponentInfo
        return ComponentInfo(
            component_id="device_manager",
            name="Audio Device Manager",
            version="1.0.0",
            description="Comprehensive audio device management system",
            author="Production Audio System",
            category="device_management"
        )
    
    def get_state(self) -> ComponentState:
        """Get current component state"""
        return self._state
    
    def init(self, config: Dict[str, Any]) -> bool:
        """Initialize device manager"""
        try:
            self._state = ComponentState.INITIALIZING
            
            # Load existing configurations
            self._config_manager.load_configurations()
            
            # Perform initial device discovery
            self.scan_devices()
            
            self._state = ComponentState.READY
            self.logger.info("Device manager initialized successfully")
            return True
            
        except Exception as e:
            self._state = ComponentState.ERROR
            self.logger.error(f"Device manager initialization failed: {e}")
            return False
    
    def start(self) -> bool:
        """Start device manager operation"""
        if self._state != ComponentState.READY:
            return False
        
        try:
            # Start health monitoring
            devices = list(self._devices.values())
            self._health_monitor.start_monitoring(devices)
            
            # Start hot-plug detection
            self._hotplug_detector.start_detection()
            
            self._state = ComponentState.RUNNING
            self.logger.info("Device manager started")
            return True
            
        except Exception as e:
            self._state = ComponentState.ERROR
            self.logger.error(f"Failed to start device manager: {e}")
            return False
    
    def pause(self) -> bool:
        """Pause device manager operation"""
        if self._state == ComponentState.RUNNING:
            self._state = ComponentState.PAUSED
            return True
        return False
    
    def resume(self) -> bool:
        """Resume device manager operation"""
        if self._state == ComponentState.PAUSED:
            self._state = ComponentState.RUNNING
            return True
        return False
    
    def stop(self) -> bool:
        """Stop device manager operation"""
        try:
            # Stop monitoring and detection
            self._health_monitor.stop_monitoring()
            self._hotplug_detector.stop_detection()
            
            # Save configurations
            self._config_manager.save_configurations()
            
            self._state = ComponentState.STOPPED
            self.logger.info("Device manager stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping device manager: {e}")
            return False
    
    def cleanup(self) -> bool:
        """Clean up device manager resources"""
        try:
            self.stop()
            self._devices.clear()
            self._device_status.clear()
            return True
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            return False
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get device manager health status"""
        return {
            "status": "healthy" if self._state == ComponentState.RUNNING else "degraded",
            "state": self._state.value,
            "device_count": len(self._devices),
            "healthy_devices": len([d for d in self._devices.values() if d.is_available]),
            "last_check": datetime.now().isoformat()
        }
    
    def handle_error(self, error: Exception) -> bool:
        """Handle component errors"""
        self.logger.error(f"Device manager error: {error}")
        self._state = ComponentState.ERROR
        return False
    
    # Device management methods
    
    def scan_devices(self) -> List[AudioDevice]:
        """Scan for available audio devices"""
        try:
            devices = self._discovery.discover_devices()
            
            # Update device storage
            for device in devices:
                self._devices[device.device_id] = device
                self._device_status[device.device_id] = DeviceStatus.AVAILABLE
                
                # Create default configuration if not exists
                if not self._config_manager.get_device_configuration(device.device_id):
                    default_config = self._config_manager.create_default_configuration(device)
                    self._config_manager.set_device_configuration(device.device_id, default_config)
            
            # Set default devices if not set
            self._update_default_devices()
            
            self.logger.info(f"Scanned and found {len(devices)} devices")
            return devices
            
        except Exception as e:
            self.logger.error(f"Device scan failed: {e}")
            return []
    
    def get_all_devices(self) -> List[AudioDevice]:
        """Get all known devices"""
        return list(self._devices.values())
    
    def get_input_devices(self) -> List[AudioDevice]:
        """Get all input devices"""
        return [device for device in self._devices.values() if device.is_input]
    
    def get_output_devices(self) -> List[AudioDevice]:
        """Get all output devices"""
        return [device for device in self._devices.values() if device.is_output]
    
    def get_device(self, device_id: str) -> Optional[AudioDevice]:
        """Get specific device by ID"""
        return self._devices.get(device_id)
    
    def get_device_status(self, device_id: str) -> Optional[DeviceStatus]:
        """Get device status"""
        return self._device_status.get(device_id)
    
    def get_default_input_device(self) -> Optional[AudioDevice]:
        """Get default input device"""
        if self._default_input_device:
            return self._devices.get(self._default_input_device)
        return None
    
    def get_default_output_device(self) -> Optional[AudioDevice]:
        """Get default output device"""
        if self._default_output_device:
            return self._devices.get(self._default_output_device)
        return None
    
    def set_default_input_device(self, device_id: str) -> bool:
        """Set default input device"""
        if device_id in self._devices and self._devices[device_id].is_input:
            self._default_input_device = device_id
            self.logger.info(f"Set default input device: {device_id}")
            return True
        return False
    
    def set_default_output_device(self, device_id: str) -> bool:
        """Set default output device"""
        if device_id in self._devices and self._devices[device_id].is_output:
            self._default_output_device = device_id
            self.logger.info(f"Set default output device: {device_id}")
            return True
        return False
    
    def _update_default_devices(self):
        """Update default devices if not set"""
        if not self._default_input_device:
            input_devices = self.get_input_devices()
            if input_devices:
                self._default_input_device = input_devices[0].device_id
        
        if not self._default_output_device:
            output_devices = self.get_output_devices()
            if output_devices:
                self._default_output_device = output_devices[0].device_id
    
    # Device configuration methods
    
    def get_device_configuration(self, device_id: str) -> Optional[DeviceConfiguration]:
        """Get device configuration"""
        return self._config_manager.get_device_configuration(device_id)
    
    def set_device_configuration(self, device_id: str, config: DeviceConfiguration) -> bool:
        """Set device configuration"""
        return self._config_manager.set_device_configuration(device_id, config)
    
    def enable_device(self, device_id: str) -> bool:
        """Enable a device"""
        config = self.get_device_configuration(device_id)
        if config:
            config.enabled = True
            return self.set_device_configuration(device_id, config)
        return False
    
    def disable_device(self, device_id: str) -> bool:
        """Disable a device"""
        config = self.get_device_configuration(device_id)
        if config:
            config.enabled = False
            return self.set_device_configuration(device_id, config)
        return False
    
    # Health monitoring methods
    
    def get_device_health(self, device_id: str) -> Optional[DeviceHealthInfo]:
        """Get device health information"""
        return self._health_monitor.get_device_health(device_id)
    
    def get_all_device_health(self) -> Dict[str, DeviceHealthInfo]:
        """Get health information for all devices"""
        return self._health_monitor.get_all_health_info()
    
    # Event callback methods
    
    def register_device_callback(self, callback: Callable[[str, str, AudioDevice], None]):
        """Register callback for device events (connected, disconnected, status_changed)"""
        self._device_callbacks.append(callback)
    
    def unregister_device_callback(self, callback: Callable[[str, str, AudioDevice], None]):
        """Unregister device callback"""
        if callback in self._device_callbacks:
            self._device_callbacks.remove(callback)
    
    # Internal callback handlers
    
    def _on_devices_discovered(self, devices: List[AudioDevice]):
        """Handle device discovery events"""
        for device in devices:
            if device.device_id not in self._devices:
                self._notify_device_event("discovered", device.device_id, device)
    
    def _on_hotplug_event(self, event_type: str, device_id: str, device: AudioDevice):
        """Handle hot-plug events"""
        if event_type == "connected":
            self._devices[device_id] = device
            self._device_status[device_id] = DeviceStatus.AVAILABLE
            
            # Create default configuration
            if not self._config_manager.get_device_configuration(device_id):
                default_config = self._config_manager.create_default_configuration(device)
                self._config_manager.set_device_configuration(device_id, default_config)
            
            # Update health monitoring
            if self._state == ComponentState.RUNNING:
                self._health_monitor.start_monitoring([device])
        
        elif event_type == "disconnected":
            if device_id in self._devices:
                self._device_status[device_id] = DeviceStatus.DISCONNECTED
                # Keep device in memory but mark as disconnected
        
        self._notify_device_event(event_type, device_id, device)
    
    def _on_health_changed(self, device_id: str, health_info: DeviceHealthInfo):
        """Handle device health changes"""
        # Update device status based on health
        if health_info.status == HealthStatus.CRITICAL:
            self._device_status[device_id] = DeviceStatus.ERROR
        elif health_info.status == HealthStatus.HEALTHY:
            self._device_status[device_id] = DeviceStatus.AVAILABLE
        
        # Notify callbacks
        device = self._devices.get(device_id)
        if device:
            self._notify_device_event("health_changed", device_id, device)
    
    def _on_config_changed(self, device_id: str, config: DeviceConfiguration):
        """Handle device configuration changes"""
        device = self._devices.get(device_id)
        if device:
            self._notify_device_event("config_changed", device_id, device)
    
    def _notify_device_event(self, event_type: str, device_id: str, device: AudioDevice):
        """Notify all registered callbacks about device events"""
        for callback in self._device_callbacks:
            try:
                callback(event_type, device_id, device)
            except Exception as e:
                self.logger.error(f"Error in device callback: {e}")
    
    # Utility methods
    
    def get_device_summary(self) -> Dict[str, Any]:
        """Get summary of all devices and their status"""
        summary = {
            "total_devices": len(self._devices),
            "input_devices": len(self.get_input_devices()),
            "output_devices": len(self.get_output_devices()),
            "available_devices": len([d for d in self._devices.values() if d.is_available]),
            "default_input": self._default_input_device,
            "default_output": self._default_output_device,
            "devices": []
        }
        
        for device in self._devices.values():
            device_info = {
                "device_id": device.device_id,
                "name": device.name,
                "type": device.device_type.value,
                "is_input": device.is_input,
                "is_output": device.is_output,
                "is_available": device.is_available,
                "is_connected": device.is_connected,
                "status": self._device_status.get(device.device_id, DeviceStatus.UNKNOWN).value
            }
            
            # Add health info if available
            health_info = self.get_device_health(device.device_id)
            if health_info:
                device_info["health"] = {
                    "status": health_info.status.value,
                    "latency_ms": health_info.latency_ms,
                    "cpu_usage": health_info.cpu_usage,
                    "error_count": health_info.error_count
                }
            
            summary["devices"].append(device_info)
        
        return summary


# Factory function for creating device manager instances
def create_device_manager(config_dir: str = "device_configs") -> DeviceManager:
    """Create and initialize a device manager instance"""
    manager = DeviceManager(config_dir)
    return manager