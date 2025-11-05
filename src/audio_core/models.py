"""
Audio Processing Core Data Models

This module implements the core data models for the production audio processing system,
including configuration, state management, and processing chain definitions.
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime
import json
import yaml
from pathlib import Path


class SystemState(Enum):
    """System state enumeration for audio processing system"""
    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    DEBUGGING = "debugging"
    ERROR = "error"
    STOPPING = "stopping"
    MAINTENANCE = "maintenance"


class DeviceType(Enum):
    """Audio device type enumeration"""
    MICROPHONE = "microphone"
    LINE_INPUT = "line_input"
    USB_AUDIO = "usb_audio"
    SPEAKER = "speaker"
    HEADPHONE = "headphone"
    UNKNOWN = "unknown"


class ProcessingStatus(Enum):
    """Processing status for audio frames and components"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AudioDevice:
    """
    Audio device model with detailed information and capabilities
    """
    device_id: str
    name: str
    device_type: DeviceType
    is_input: bool
    is_output: bool
    
    # Device capabilities
    max_input_channels: int = 0
    max_output_channels: int = 0
    supported_sample_rates: List[int] = field(default_factory=lambda: [44100, 48000])
    supported_bit_depths: List[int] = field(default_factory=lambda: [16, 24, 32])
    
    # Device status
    is_available: bool = True
    is_connected: bool = True
    driver_name: str = ""
    driver_version: str = ""
    
    # Performance characteristics
    default_low_input_latency: float = 0.0
    default_low_output_latency: float = 0.0
    default_high_input_latency: float = 0.0
    default_high_output_latency: float = 0.0
    
    # Additional metadata
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert device to dictionary representation"""
        return {
            'device_id': self.device_id,
            'name': self.name,
            'device_type': self.device_type.value,
            'is_input': self.is_input,
            'is_output': self.is_output,
            'max_input_channels': self.max_input_channels,
            'max_output_channels': self.max_output_channels,
            'supported_sample_rates': self.supported_sample_rates,
            'supported_bit_depths': self.supported_bit_depths,
            'is_available': self.is_available,
            'is_connected': self.is_connected,
            'driver_name': self.driver_name,
            'driver_version': self.driver_version,
            'latency': {
                'low_input': self.default_low_input_latency,
                'low_output': self.default_low_output_latency,
                'high_input': self.default_high_input_latency,
                'high_output': self.default_high_output_latency
            },
            'manufacturer': self.manufacturer,
            'model': self.model,
            'serial_number': self.serial_number,
            'created_at': self.created_at.isoformat(),
            'last_seen': self.last_seen.isoformat()
        }


@dataclass
class ProcessingMetrics:
    """
    Processing metrics for performance and effect monitoring
    """
    component_name: str
    
    # Performance metrics
    processing_time_ms: float = 0.0
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    frames_processed: int = 0
    frames_dropped: int = 0
    
    # Quality metrics
    input_level_db: float = -60.0
    output_level_db: float = -60.0
    snr_db: float = 0.0
    thd_percent: float = 0.0
    
    # Algorithm-specific metrics
    algorithm_metrics: Dict[str, float] = field(default_factory=dict)
    
    # Timestamps
    start_time: datetime = field(default_factory=datetime.now)
    last_update: datetime = field(default_factory=datetime.now)
    
    def update_performance(self, processing_time: float, cpu_usage: float, memory_usage: float):
        """Update performance metrics"""
        self.processing_time_ms = processing_time
        self.cpu_usage_percent = cpu_usage
        self.memory_usage_mb = memory_usage
        self.last_update = datetime.now()
    
    def update_quality(self, input_level: float, output_level: float, snr: float = None, thd: float = None):
        """Update audio quality metrics"""
        self.input_level_db = input_level
        self.output_level_db = output_level
        if snr is not None:
            self.snr_db = snr
        if thd is not None:
            self.thd_percent = thd
        self.last_update = datetime.now()
    
    def add_algorithm_metric(self, name: str, value: float):
        """Add algorithm-specific metric"""
        self.algorithm_metrics[name] = value
        self.last_update = datetime.now()


@dataclass
class AudioFrame:
    """
    Audio frame with data, timestamp, quality metrics and processing status
    """
    frame_id: int
    timestamp: datetime
    sample_rate: int
    channels: int
    bit_depth: int
    
    # Audio data (placeholder - actual implementation would use numpy arrays)
    data: Any = None  # Will be numpy.ndarray in actual implementation
    frame_size: int = 0
    
    # Quality indicators
    peak_level_db: float = -60.0
    rms_level_db: float = -60.0
    zero_crossing_rate: float = 0.0
    spectral_centroid: float = 0.0
    
    # Processing status
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    processing_chain: List[str] = field(default_factory=list)
    processing_errors: List[str] = field(default_factory=list)
    
    # Timing information
    capture_timestamp: datetime = field(default_factory=datetime.now)
    processing_start: Optional[datetime] = None
    processing_end: Optional[datetime] = None
    
    def start_processing(self, component_name: str):
        """Mark frame as starting processing by a component"""
        self.processing_status = ProcessingStatus.PROCESSING
        self.processing_start = datetime.now()
        if component_name not in self.processing_chain:
            self.processing_chain.append(component_name)
    
    def complete_processing(self):
        """Mark frame processing as completed"""
        self.processing_status = ProcessingStatus.COMPLETED
        self.processing_end = datetime.now()
    
    def add_error(self, error_message: str):
        """Add processing error"""
        self.processing_errors.append(error_message)
        self.processing_status = ProcessingStatus.FAILED
    
    def get_processing_duration(self) -> Optional[float]:
        """Get processing duration in milliseconds"""
        if self.processing_start and self.processing_end:
            return (self.processing_end - self.processing_start).total_seconds() * 1000
        return None


@dataclass
class ProcessingChain:
    """
    Processing chain definition with component connections and routing
    """
    chain_id: str
    name: str
    description: str = ""
    
    # Chain configuration
    components: List[str] = field(default_factory=list)
    connections: Dict[str, List[str]] = field(default_factory=dict)
    parallel_branches: List[List[str]] = field(default_factory=list)
    
    # Chain state
    is_active: bool = False
    current_component: Optional[str] = None
    
    # Performance tracking
    total_frames_processed: int = 0
    average_processing_time_ms: float = 0.0
    
    # Configuration
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: datetime = field(default_factory=datetime.now)
    
    def add_component(self, component_name: str, after: Optional[str] = None):
        """Add component to the processing chain"""
        if component_name not in self.components:
            if after and after in self.components:
                index = self.components.index(after) + 1
                self.components.insert(index, component_name)
            else:
                self.components.append(component_name)
            self.modified_at = datetime.now()
    
    def remove_component(self, component_name: str):
        """Remove component from the processing chain"""
        if component_name in self.components:
            self.components.remove(component_name)
            # Clean up connections
            if component_name in self.connections:
                del self.connections[component_name]
            for source, targets in self.connections.items():
                if component_name in targets:
                    targets.remove(component_name)
            self.modified_at = datetime.now()
    
    def connect_components(self, source: str, target: str):
        """Connect two components in the chain"""
        if source not in self.connections:
            self.connections[source] = []
        if target not in self.connections[source]:
            self.connections[source].append(target)
            self.modified_at = datetime.now()
    
    def get_next_components(self, current: str) -> List[str]:
        """Get next components in the processing chain"""
        return self.connections.get(current, [])


@dataclass
class AudioProcessingConfig:
    """
    Comprehensive audio processing configuration with device and processing parameters
    """
    config_id: str
    name: str
    description: str = ""
    
    # Device configuration
    input_devices: List[str] = field(default_factory=list)
    output_devices: List[str] = field(default_factory=list)
    default_input_device: Optional[str] = None
    default_output_device: Optional[str] = None
    
    # Audio parameters
    sample_rate: int = 48000
    bit_depth: int = 24
    channels: int = 2
    buffer_size: int = 256
    
    # Processing parameters
    enable_aec: bool = True  # Acoustic Echo Cancellation
    enable_agc: bool = True  # Automatic Gain Control
    enable_ns: bool = True   # Noise Suppression
    enable_ssl: bool = False # Sound Source Localization
    enable_beamforming: bool = False
    
    # Processing chain configuration
    processing_chains: Dict[str, ProcessingChain] = field(default_factory=dict)
    active_chain: Optional[str] = None
    
    # Performance settings
    max_processing_threads: int = 4
    realtime_priority: bool = True
    low_latency_mode: bool = True
    
    # Quality settings
    quality_monitoring: bool = True
    auto_level_adjustment: bool = True
    dynamic_range_compression: bool = False
    
    # Advanced parameters
    advanced_params: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0.0"
    
    def add_processing_chain(self, chain: ProcessingChain):
        """Add a processing chain to the configuration"""
        self.processing_chains[chain.chain_id] = chain
        if not self.active_chain:
            self.active_chain = chain.chain_id
        self.modified_at = datetime.now()
    
    def set_active_chain(self, chain_id: str):
        """Set the active processing chain"""
        if chain_id in self.processing_chains:
            self.active_chain = chain_id
            self.modified_at = datetime.now()
    
    def get_active_chain(self) -> Optional[ProcessingChain]:
        """Get the currently active processing chain"""
        if self.active_chain and self.active_chain in self.processing_chains:
            return self.processing_chains[self.active_chain]
        return None
    
    def update_advanced_param(self, key: str, value: Any):
        """Update advanced parameter"""
        self.advanced_params[key] = value
        self.modified_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for serialization"""
        return {
            'config_id': self.config_id,
            'name': self.name,
            'description': self.description,
            'devices': {
                'input_devices': self.input_devices,
                'output_devices': self.output_devices,
                'default_input_device': self.default_input_device,
                'default_output_device': self.default_output_device
            },
            'audio_params': {
                'sample_rate': self.sample_rate,
                'bit_depth': self.bit_depth,
                'channels': self.channels,
                'buffer_size': self.buffer_size
            },
            'processing': {
                'enable_aec': self.enable_aec,
                'enable_agc': self.enable_agc,
                'enable_ns': self.enable_ns,
                'enable_ssl': self.enable_ssl,
                'enable_beamforming': self.enable_beamforming
            },
            'performance': {
                'max_processing_threads': self.max_processing_threads,
                'realtime_priority': self.realtime_priority,
                'low_latency_mode': self.low_latency_mode
            },
            'quality': {
                'quality_monitoring': self.quality_monitoring,
                'auto_level_adjustment': self.auto_level_adjustment,
                'dynamic_range_compression': self.dynamic_range_compression
            },
            'advanced_params': self.advanced_params,
            'active_chain': self.active_chain,
            'version': self.version,
            'created_at': self.created_at.isoformat(),
            'modified_at': self.modified_at.isoformat()
        }
    
    def save_to_file(self, file_path: Union[str, Path], format: str = 'json'):
        """Save configuration to file in JSON or YAML format"""
        file_path = Path(file_path)
        config_dict = self.to_dict()
        
        if format.lower() == 'json':
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
        elif format.lower() == 'yaml':
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)
        else:
            raise ValueError(f"Unsupported format: {format}. Use 'json' or 'yaml'.")
    
    @classmethod
    def load_from_file(cls, file_path: Union[str, Path]) -> 'AudioProcessingConfig':
        """Load configuration from file"""
        file_path = Path(file_path)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            if file_path.suffix.lower() == '.json':
                config_dict = json.load(f)
            elif file_path.suffix.lower() in ['.yaml', '.yml']:
                config_dict = yaml.safe_load(f)
            else:
                # Try to detect format by content
                content = f.read()
                f.seek(0)
                try:
                    config_dict = json.load(f)
                except json.JSONDecodeError:
                    f.seek(0)
                    config_dict = yaml.safe_load(f)
        
        # Create configuration from dictionary
        config = cls(
            config_id=config_dict['config_id'],
            name=config_dict['name'],
            description=config_dict.get('description', '')
        )
        
        # Load device settings
        devices = config_dict.get('devices', {})
        config.input_devices = devices.get('input_devices', [])
        config.output_devices = devices.get('output_devices', [])
        config.default_input_device = devices.get('default_input_device')
        config.default_output_device = devices.get('default_output_device')
        
        # Load audio parameters
        audio_params = config_dict.get('audio_params', {})
        config.sample_rate = audio_params.get('sample_rate', 48000)
        config.bit_depth = audio_params.get('bit_depth', 24)
        config.channels = audio_params.get('channels', 2)
        config.buffer_size = audio_params.get('buffer_size', 256)
        
        # Load processing settings
        processing = config_dict.get('processing', {})
        config.enable_aec = processing.get('enable_aec', True)
        config.enable_agc = processing.get('enable_agc', True)
        config.enable_ns = processing.get('enable_ns', True)
        config.enable_ssl = processing.get('enable_ssl', False)
        config.enable_beamforming = processing.get('enable_beamforming', False)
        
        # Load performance settings
        performance = config_dict.get('performance', {})
        config.max_processing_threads = performance.get('max_processing_threads', 4)
        config.realtime_priority = performance.get('realtime_priority', True)
        config.low_latency_mode = performance.get('low_latency_mode', True)
        
        # Load quality settings
        quality = config_dict.get('quality', {})
        config.quality_monitoring = quality.get('quality_monitoring', True)
        config.auto_level_adjustment = quality.get('auto_level_adjustment', True)
        config.dynamic_range_compression = quality.get('dynamic_range_compression', False)
        
        # Load advanced parameters
        config.advanced_params = config_dict.get('advanced_params', {})
        config.active_chain = config_dict.get('active_chain')
        config.version = config_dict.get('version', '1.0.0')
        
        return config


class RealTimeParameterController:
    """
    Real-time parameter adjustment interface for dynamic configuration changes
    """
    
    def __init__(self, config: AudioProcessingConfig):
        self.config = config
        self.parameter_callbacks: Dict[str, List[callable]] = {}
        self.parameter_history: Dict[str, List[Tuple[datetime, Any]]] = {}
    
    def register_callback(self, parameter_name: str, callback: callable):
        """Register callback for parameter changes"""
        if parameter_name not in self.parameter_callbacks:
            self.parameter_callbacks[parameter_name] = []
        self.parameter_callbacks[parameter_name].append(callback)
    
    def set_parameter(self, parameter_name: str, value: Any, notify: bool = True):
        """Set parameter value with optional notification"""
        # Update configuration
        if hasattr(self.config, parameter_name):
            setattr(self.config, parameter_name, value)
        else:
            self.config.update_advanced_param(parameter_name, value)
        
        # Record history
        if parameter_name not in self.parameter_history:
            self.parameter_history[parameter_name] = []
        self.parameter_history[parameter_name].append((datetime.now(), value))
        
        # Notify callbacks
        if notify and parameter_name in self.parameter_callbacks:
            for callback in self.parameter_callbacks[parameter_name]:
                try:
                    callback(parameter_name, value)
                except Exception as e:
                    print(f"Error in parameter callback: {e}")
    
    def get_parameter(self, parameter_name: str) -> Any:
        """Get current parameter value"""
        if hasattr(self.config, parameter_name):
            return getattr(self.config, parameter_name)
        return self.config.advanced_params.get(parameter_name)
    
    def get_parameter_history(self, parameter_name: str, limit: int = 100) -> List[Tuple[datetime, Any]]:
        """Get parameter change history"""
        history = self.parameter_history.get(parameter_name, [])
        return history[-limit:] if limit > 0 else history
    
    def batch_update(self, parameters: Dict[str, Any]):
        """Update multiple parameters in batch"""
        for param_name, value in parameters.items():
            self.set_parameter(param_name, value, notify=False)
        
        # Notify all affected callbacks
        for param_name in parameters.keys():
            if param_name in self.parameter_callbacks:
                for callback in self.parameter_callbacks[param_name]:
                    try:
                        callback(param_name, parameters[param_name])
                    except Exception as e:
                        print(f"Error in parameter callback: {e}")


# Configuration persistence utilities
class ConfigurationManager:
    """
    Configuration persistence and management utilities
    """
    
    def __init__(self, config_dir: Union[str, Path] = "configs"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
    
    def save_config(self, config: AudioProcessingConfig, filename: Optional[str] = None, format: str = 'json'):
        """Save configuration to file"""
        if filename is None:
            filename = f"{config.config_id}.{format}"
        
        file_path = self.config_dir / filename
        config.save_to_file(file_path, format)
        return file_path
    
    def load_config(self, filename: str) -> AudioProcessingConfig:
        """Load configuration from file"""
        file_path = self.config_dir / filename
        return AudioProcessingConfig.load_from_file(file_path)
    
    def list_configs(self) -> List[str]:
        """List available configuration files"""
        configs = []
        for file_path in self.config_dir.glob("*.json"):
            configs.append(file_path.name)
        for file_path in self.config_dir.glob("*.yaml"):
            configs.append(file_path.name)
        for file_path in self.config_dir.glob("*.yml"):
            configs.append(file_path.name)
        return sorted(configs)
    
    def delete_config(self, filename: str) -> bool:
        """Delete configuration file"""
        file_path = self.config_dir / filename
        if file_path.exists():
            file_path.unlink()
            return True
        return False
    
    def create_default_config(self) -> AudioProcessingConfig:
        """Create a default configuration"""
        config = AudioProcessingConfig(
            config_id="default",
            name="Default Audio Processing Configuration",
            description="Default configuration for production audio processing system"
        )
        
        # Add default processing chain
        default_chain = ProcessingChain(
            chain_id="default_chain",
            name="Default Processing Chain",
            description="Standard audio processing pipeline",
            components=["aec", "ns", "agc"]
        )
        
        # Set up component connections
        default_chain.connect_components("aec", "ns")
        default_chain.connect_components("ns", "agc")
        
        config.add_processing_chain(default_chain)
        
        return config