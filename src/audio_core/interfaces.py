"""
Pluggable Component Architecture Interfaces

This module defines the core interfaces for the pluggable audio processing component system,
enabling dynamic loading, configuration, and management of audio processing components.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple, Union, Callable
from enum import Enum
import numpy as np
from datetime import datetime
from dataclasses import dataclass

from .models import AudioFrame, ProcessingMetrics, AudioProcessingConfig, AudioDevice


class ComponentState(Enum):
    """Component lifecycle states"""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPING = "stopping"
    STOPPED = "stopped"


class ProcessingMode(Enum):
    """Audio processing modes"""
    REALTIME = "realtime"
    BATCH = "batch"
    OFFLINE = "offline"


@dataclass
class ComponentInfo:
    """Component information and metadata"""
    component_id: str
    name: str
    version: str
    description: str
    author: str
    category: str
    
    # Capabilities
    supports_realtime: bool = True
    supports_batch: bool = True
    supports_multi_channel: bool = True
    max_channels: int = 32
    
    # Requirements
    min_sample_rate: int = 8000
    max_sample_rate: int = 192000
    supported_bit_depths: List[int] = None
    
    # Dependencies
    dependencies: List[str] = None
    conflicts: List[str] = None
    
    def __post_init__(self):
        if self.supported_bit_depths is None:
            self.supported_bit_depths = [16, 24, 32]
        if self.dependencies is None:
            self.dependencies = []
        if self.conflicts is None:
            self.conflicts = []


class IAudioProcessor(ABC):
    """
    Base interface for all audio processing components
    """
    
    @abstractmethod
    def get_info(self) -> ComponentInfo:
        """Get component information and metadata"""
        pass
    
    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize the processor with configuration"""
        pass
    
    @abstractmethod
    def configure(self, parameters: Dict[str, Any]) -> bool:
        """Configure processor parameters"""
        pass
    
    @abstractmethod
    def process(self, audio_frame: AudioFrame) -> AudioFrame:
        """Process a single audio frame"""
        pass
    
    @abstractmethod
    def process_batch(self, audio_frames: List[AudioFrame]) -> List[AudioFrame]:
        """Process a batch of audio frames"""
        pass
    
    @abstractmethod
    def get_metrics(self) -> ProcessingMetrics:
        """Get current processing metrics"""
        pass
    
    @abstractmethod
    def get_parameters(self) -> Dict[str, Any]:
        """Get current parameter values"""
        pass
    
    @abstractmethod
    def set_parameter(self, name: str, value: Any) -> bool:
        """Set a specific parameter value"""
        pass
    
    @abstractmethod
    def reset(self) -> bool:
        """Reset processor to initial state"""
        pass
    
    @abstractmethod
    def cleanup(self) -> bool:
        """Clean up resources"""
        pass


class IMultiInputCapture(ABC):
    """
    Interface for multi-input audio capture with dynamic device detection
    """
    
    @abstractmethod
    def scan_input_devices(self) -> List[Dict[str, Any]]:
        """Scan and return available input devices"""
        pass
    
    @abstractmethod
    def get_device_capabilities(self, device_id: str) -> Dict[str, Any]:
        """Get detailed capabilities of a specific device"""
        pass
    
    @abstractmethod
    def select_inputs(self, device_ids: List[str]) -> bool:
        """Select specific input devices for capture"""
        pass
    
    @abstractmethod
    def enable_all_inputs(self) -> bool:
        """Enable all available input devices"""
        pass
    
    @abstractmethod
    def start_capture(self, config: AudioProcessingConfig) -> bool:
        """Start multi-input audio capture"""
        pass
    
    @abstractmethod
    def stop_capture(self) -> bool:
        """Stop audio capture"""
        pass
    
    @abstractmethod
    def get_input_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all input devices"""
        pass
    
    @abstractmethod
    def set_input_gain(self, device_id: str, gain_db: float) -> bool:
        """Set input gain for specific device"""
        pass
    
    @abstractmethod
    def mute_input(self, device_id: str, muted: bool) -> bool:
        """Mute/unmute specific input device"""
        pass
    
    @abstractmethod
    def register_input_callback(self, callback: Callable[[str, AudioFrame], None]) -> bool:
        """Register callback for input audio data"""
        pass


class IPluggableComponent(ABC):
    """
    Interface for pluggable components with lifecycle management
    """
    
    @abstractmethod
    def get_component_info(self) -> ComponentInfo:
        """Get component information"""
        pass
    
    @abstractmethod
    def get_state(self) -> ComponentState:
        """Get current component state"""
        pass
    
    @abstractmethod
    def init(self, config: Dict[str, Any]) -> bool:
        """Initialize component"""
        pass
    
    @abstractmethod
    def start(self) -> bool:
        """Start component operation"""
        pass
    
    @abstractmethod
    def pause(self) -> bool:
        """Pause component operation"""
        pass
    
    @abstractmethod
    def resume(self) -> bool:
        """Resume component operation"""
        pass
    
    @abstractmethod
    def stop(self) -> bool:
        """Stop component operation"""
        pass
    
    @abstractmethod
    def cleanup(self) -> bool:
        """Clean up component resources"""
        pass
    
    @abstractmethod
    def get_health_status(self) -> Dict[str, Any]:
        """Get component health and diagnostic information"""
        pass
    
    @abstractmethod
    def handle_error(self, error: Exception) -> bool:
        """Handle component errors"""
        pass


class IProcessingPipeline(ABC):
    """
    Interface for audio processing pipeline with component chaining
    """
    
    @abstractmethod
    def add_component(self, component: IAudioProcessor, position: Optional[int] = None) -> bool:
        """Add component to pipeline"""
        pass
    
    @abstractmethod
    def remove_component(self, component_id: str) -> bool:
        """Remove component from pipeline"""
        pass
    
    @abstractmethod
    def insert_component(self, component: IAudioProcessor, after_component: str) -> bool:
        """Insert component after specified component"""
        pass
    
    @abstractmethod
    def create_parallel_branch(self, components: List[IAudioProcessor], merge_strategy: str) -> bool:
        """Create parallel processing branch"""
        pass
    
    @abstractmethod
    def create_conditional_branch(self, condition: Callable, true_branch: List[IAudioProcessor], 
                                false_branch: List[IAudioProcessor]) -> bool:
        """Create conditional processing branch"""
        pass
    
    @abstractmethod
    def process_pipeline(self, audio_frame: AudioFrame) -> AudioFrame:
        """Process audio frame through entire pipeline"""
        pass
    
    @abstractmethod
    def get_pipeline_metrics(self) -> Dict[str, ProcessingMetrics]:
        """Get metrics for all components in pipeline"""
        pass
    
    @abstractmethod
    def get_pipeline_topology(self) -> Dict[str, Any]:
        """Get pipeline structure and connections"""
        pass
    
    @abstractmethod
    def validate_pipeline(self) -> Tuple[bool, List[str]]:
        """Validate pipeline configuration and dependencies"""
        pass
    
    @abstractmethod
    def optimize_pipeline(self) -> bool:
        """Optimize pipeline for performance"""
        pass


class IComponentRegistry(ABC):
    """
    Interface for component registry and discovery
    """
    
    @abstractmethod
    def register_component(self, component_class: type, component_info: ComponentInfo) -> bool:
        """Register a component class"""
        pass
    
    @abstractmethod
    def unregister_component(self, component_id: str) -> bool:
        """Unregister a component"""
        pass
    
    @abstractmethod
    def discover_components(self, search_paths: List[str]) -> List[ComponentInfo]:
        """Discover components in specified paths"""
        pass
    
    @abstractmethod
    def get_component_info(self, component_id: str) -> Optional[ComponentInfo]:
        """Get information about a specific component"""
        pass
    
    @abstractmethod
    def list_components(self, category: Optional[str] = None) -> List[ComponentInfo]:
        """List all registered components, optionally filtered by category"""
        pass
    
    @abstractmethod
    def create_component(self, component_id: str, config: Dict[str, Any]) -> Optional[IAudioProcessor]:
        """Create instance of a component"""
        pass
    
    @abstractmethod
    def check_dependencies(self, component_id: str) -> Tuple[bool, List[str]]:
        """Check if component dependencies are satisfied"""
        pass
    
    @abstractmethod
    def check_conflicts(self, component_ids: List[str]) -> Tuple[bool, List[str]]:
        """Check for conflicts between components"""
        pass
    
    @abstractmethod
    def get_compatible_components(self, requirements: Dict[str, Any]) -> List[ComponentInfo]:
        """Get components compatible with specified requirements"""
        pass


class IParameterController(ABC):
    """
    Interface for real-time parameter control and monitoring
    """
    
    @abstractmethod
    def get_parameter_schema(self, component_id: str) -> Dict[str, Any]:
        """Get parameter schema for a component"""
        pass
    
    @abstractmethod
    def get_parameter_value(self, component_id: str, parameter_name: str) -> Any:
        """Get current parameter value"""
        pass
    
    @abstractmethod
    def set_parameter_value(self, component_id: str, parameter_name: str, value: Any) -> bool:
        """Set parameter value with validation"""
        pass
    
    @abstractmethod
    def batch_set_parameters(self, component_id: str, parameters: Dict[str, Any]) -> Dict[str, bool]:
        """Set multiple parameters in batch"""
        pass
    
    @abstractmethod
    def get_parameter_limits(self, component_id: str, parameter_name: str) -> Dict[str, Any]:
        """Get parameter limits and constraints"""
        pass
    
    @abstractmethod
    def register_parameter_callback(self, component_id: str, parameter_name: str, 
                                  callback: Callable[[str, str, Any], None]) -> bool:
        """Register callback for parameter changes"""
        pass
    
    @abstractmethod
    def create_parameter_preset(self, preset_name: str, parameters: Dict[str, Dict[str, Any]]) -> bool:
        """Create parameter preset"""
        pass
    
    @abstractmethod
    def load_parameter_preset(self, preset_name: str) -> bool:
        """Load parameter preset"""
        pass
    
    @abstractmethod
    def get_parameter_history(self, component_id: str, parameter_name: str, 
                            duration_seconds: int) -> List[Tuple[datetime, Any]]:
        """Get parameter change history"""
        pass
    
    @abstractmethod
    def enable_auto_tuning(self, component_id: str, parameters: List[str], 
                          optimization_target: str) -> bool:
        """Enable automatic parameter tuning"""
        pass


class IVisualizationProvider(ABC):
    """
    Interface for component visualization and monitoring
    """
    
    @abstractmethod
    def get_visualization_types(self) -> List[str]:
        """Get available visualization types"""
        pass
    
    @abstractmethod
    def get_visualization_data(self, viz_type: str, time_range: Optional[Tuple[datetime, datetime]] = None) -> Dict[str, Any]:
        """Get data for specific visualization type"""
        pass
    
    @abstractmethod
    def get_real_time_data(self, data_types: List[str]) -> Dict[str, Any]:
        """Get real-time data for monitoring"""
        pass
    
    @abstractmethod
    def get_spectrum_data(self, fft_size: int = 1024) -> np.ndarray:
        """Get frequency spectrum data"""
        pass
    
    @abstractmethod
    def get_waveform_data(self, duration_ms: int = 1000) -> np.ndarray:
        """Get waveform data"""
        pass
    
    @abstractmethod
    def get_level_meters(self) -> Dict[str, float]:
        """Get audio level meter data"""
        pass
    
    @abstractmethod
    def get_processing_graph(self) -> Dict[str, Any]:
        """Get processing flow graph data"""
        pass
    
    @abstractmethod
    def export_visualization(self, viz_type: str, format: str, file_path: str) -> bool:
        """Export visualization to file"""
        pass
    
    @abstractmethod
    def register_visualization_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> bool:
        """Register callback for visualization updates"""
        pass


class IComponentLifecycle(ABC):
    """
    Interface for component lifecycle management
    """
    
    @abstractmethod
    def initialize_component(self, component: IPluggableComponent, config: Dict[str, Any]) -> bool:
        """Initialize component with configuration"""
        pass
    
    @abstractmethod
    def start_component(self, component_id: str) -> bool:
        """Start component operation"""
        pass
    
    @abstractmethod
    def stop_component(self, component_id: str, graceful: bool = True) -> bool:
        """Stop component operation"""
        pass
    
    @abstractmethod
    def restart_component(self, component_id: str) -> bool:
        """Restart component"""
        pass
    
    @abstractmethod
    def pause_component(self, component_id: str) -> bool:
        """Pause component operation"""
        pass
    
    @abstractmethod
    def resume_component(self, component_id: str) -> bool:
        """Resume component operation"""
        pass
    
    @abstractmethod
    def get_component_state(self, component_id: str) -> ComponentState:
        """Get current component state"""
        pass
    
    @abstractmethod
    def monitor_component_health(self, component_id: str) -> Dict[str, Any]:
        """Monitor component health status"""
        pass
    
    @abstractmethod
    def handle_component_failure(self, component_id: str, error: Exception) -> bool:
        """Handle component failure"""
        pass
    
    @abstractmethod
    def cleanup_component(self, component_id: str) -> bool:
        """Clean up component resources"""
        pass
    
    @abstractmethod
    def register_lifecycle_callback(self, event: str, callback: Callable[[str, ComponentState], None]) -> bool:
        """Register callback for lifecycle events"""
        pass


# Base implementations for common functionality

class BaseAudioProcessor(IAudioProcessor):
    """
    Base implementation of IAudioProcessor with common functionality
    """
    
    def __init__(self, component_info: ComponentInfo):
        self._info = component_info
        self._state = ComponentState.UNINITIALIZED
        self._config = {}
        self._parameters = {}
        self._metrics = ProcessingMetrics(component_name=component_info.name)
        self._callbacks = {}
    
    def get_info(self) -> ComponentInfo:
        return self._info
    
    def get_state(self) -> ComponentState:
        return self._state
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        try:
            self._state = ComponentState.INITIALIZING
            self._config = config.copy()
            self._initialize_parameters()
            self._state = ComponentState.READY
            return True
        except Exception as e:
            self._state = ComponentState.ERROR
            return False
    
    def configure(self, parameters: Dict[str, Any]) -> bool:
        try:
            for name, value in parameters.items():
                if not self.set_parameter(name, value):
                    return False
            return True
        except Exception:
            return False
    
    def get_parameters(self) -> Dict[str, Any]:
        return self._parameters.copy()
    
    def set_parameter(self, name: str, value: Any) -> bool:
        if self._validate_parameter(name, value):
            old_value = self._parameters.get(name)
            self._parameters[name] = value
            self._on_parameter_changed(name, old_value, value)
            return True
        return False
    
    def get_metrics(self) -> ProcessingMetrics:
        return self._metrics
    
    def reset(self) -> bool:
        try:
            self._initialize_parameters()
            self._metrics = ProcessingMetrics(component_name=self._info.name)
            return True
        except Exception:
            return False
    
    def cleanup(self) -> bool:
        try:
            self._state = ComponentState.STOPPED
            self._callbacks.clear()
            return True
        except Exception:
            return False
    
    # Abstract methods that must be implemented by subclasses
    @abstractmethod
    def process(self, audio_frame: AudioFrame) -> AudioFrame:
        pass
    
    @abstractmethod
    def process_batch(self, audio_frames: List[AudioFrame]) -> List[AudioFrame]:
        pass
    
    # Protected methods for subclass implementation
    def _initialize_parameters(self):
        """Initialize default parameters - override in subclasses"""
        pass
    
    def _validate_parameter(self, name: str, value: Any) -> bool:
        """Validate parameter value - override in subclasses"""
        return True
    
    def _on_parameter_changed(self, name: str, old_value: Any, new_value: Any):
        """Handle parameter change - override in subclasses"""
        pass


class BasePluggableComponent(IPluggableComponent, BaseAudioProcessor):
    """
    Base implementation combining pluggable component and audio processor interfaces
    """
    
    def __init__(self, component_info: ComponentInfo):
        super().__init__(component_info)
        self._health_status = {"status": "healthy", "last_check": datetime.now()}
    
    def get_component_info(self) -> ComponentInfo:
        return self.get_info()
    
    def init(self, config: Dict[str, Any]) -> bool:
        return self.initialize(config)
    
    def start(self) -> bool:
        if self._state == ComponentState.READY:
            self._state = ComponentState.RUNNING
            return True
        return False
    
    def pause(self) -> bool:
        if self._state == ComponentState.RUNNING:
            self._state = ComponentState.PAUSED
            return True
        return False
    
    def resume(self) -> bool:
        if self._state == ComponentState.PAUSED:
            self._state = ComponentState.RUNNING
            return True
        return False
    
    def stop(self) -> bool:
        if self._state in [ComponentState.RUNNING, ComponentState.PAUSED]:
            self._state = ComponentState.STOPPED
            return True
        return False
    
    def get_health_status(self) -> Dict[str, Any]:
        self._health_status["last_check"] = datetime.now()
        return self._health_status.copy()
    
    def handle_error(self, error: Exception) -> bool:
        self._state = ComponentState.ERROR
        self._health_status["status"] = "error"
        self._health_status["error"] = str(error)
        return False


# Utility functions for component management

def validate_component_compatibility(component_info: ComponentInfo, requirements: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate if component meets requirements"""
    issues = []
    
    # Check sample rate compatibility
    if "sample_rate" in requirements:
        sample_rate = requirements["sample_rate"]
        if sample_rate < component_info.min_sample_rate or sample_rate > component_info.max_sample_rate:
            issues.append(f"Sample rate {sample_rate} not supported (range: {component_info.min_sample_rate}-{component_info.max_sample_rate})")
    
    # Check bit depth compatibility
    if "bit_depth" in requirements:
        bit_depth = requirements["bit_depth"]
        if bit_depth not in component_info.supported_bit_depths:
            issues.append(f"Bit depth {bit_depth} not supported (supported: {component_info.supported_bit_depths})")
    
    # Check channel count
    if "channels" in requirements:
        channels = requirements["channels"]
        if channels > component_info.max_channels:
            issues.append(f"Channel count {channels} exceeds maximum {component_info.max_channels}")
    
    # Check processing mode
    if "processing_mode" in requirements:
        mode = requirements["processing_mode"]
        if mode == ProcessingMode.REALTIME and not component_info.supports_realtime:
            issues.append("Real-time processing not supported")
        elif mode == ProcessingMode.BATCH and not component_info.supports_batch:
            issues.append("Batch processing not supported")
    
    return len(issues) == 0, issues


def check_component_dependencies(component_info: ComponentInfo, available_components: List[str]) -> Tuple[bool, List[str]]:
    """Check if component dependencies are satisfied"""
    missing_deps = []
    
    for dep in component_info.dependencies:
        if dep not in available_components:
            missing_deps.append(dep)
    
    return len(missing_deps) == 0, missing_deps


def check_component_conflicts(component_infos: List[ComponentInfo]) -> Tuple[bool, List[str]]:
    """Check for conflicts between components"""
    conflicts = []
    
    for i, comp1 in enumerate(component_infos):
        for j, comp2 in enumerate(component_infos[i+1:], i+1):
            if comp2.component_id in comp1.conflicts:
                conflicts.append(f"{comp1.component_id} conflicts with {comp2.component_id}")
            if comp1.component_id in comp2.conflicts:
                conflicts.append(f"{comp2.component_id} conflicts with {comp1.component_id}")
    
    return len(conflicts) == 0, conflicts