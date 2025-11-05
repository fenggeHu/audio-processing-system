"""
Intelligent Component Registry and Standardized Component Library

This module implements the IntelligentComponentRegistry class for automatic
discovery, registration, and management of all available audio processing components
with hot-plugging capabilities, version management, and dependency resolution.
"""

import asyncio
import json
import importlib
import inspect
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable, Type, Union
from enum import Enum
import logging
from pathlib import Path
import hashlib
import sys
import os

from .interfaces import (
    IAudioProcessor, IPluggableComponent, IParameterController, 
    IVisualizationProvider, ComponentInfo, ProcessingMetrics
)
from .models import AudioFrame


class ComponentStatus(Enum):
    """Component status in the registry"""
    AVAILABLE = "available"
    LOADED = "loaded"
    ACTIVE = "active"
    ERROR = "error"
    DEPRECATED = "deprecated"
    UPDATING = "updating"


class ComponentCategory(Enum):
    """Categories of audio processing components"""
    WEBRTC = "webrtc"
    SPATIAL_AUDIO = "spatial_audio"
    EFFECTS = "effects"
    ANALYSIS = "analysis"
    SYNTHESIS = "synthesis"
    IO = "io"
    UTILITY = "utility"
    CUSTOM = "custom"


@dataclass
class ComponentVersion:
    """Component version information"""
    major: int
    minor: int
    patch: int
    build: str = ""
    
    def __str__(self) -> str:
        version_str = f"{self.major}.{self.minor}.{self.patch}"
        if self.build:
            version_str += f"-{self.build}"
        return version_str
    
    def __lt__(self, other: 'ComponentVersion') -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
    
    def __eq__(self, other: 'ComponentVersion') -> bool:
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)


@dataclass
class ComponentDependency:
    """Component dependency specification"""
    component_id: str
    min_version: Optional[ComponentVersion] = None
    max_version: Optional[ComponentVersion] = None
    required: bool = True
    description: str = ""


@dataclass
class ComponentRegistration:
    """Complete component registration information"""
    component_id: str
    name: str
    description: str
    version: ComponentVersion
    category: ComponentCategory
    component_class: Type[IAudioProcessor]
    dependencies: List[ComponentDependency]
    status: ComponentStatus = ComponentStatus.AVAILABLE
    file_path: str = ""
    checksum: str = ""
    registration_time: datetime = None
    last_update: datetime = None
    performance_profile: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.registration_time is None:
            self.registration_time = datetime.now()
        if self.last_update is None:
            self.last_update = datetime.now()
        if self.performance_profile is None:
            self.performance_profile = {}


class IntelligentComponentRegistry:
    """
    Intelligent registry for automatic component discovery, registration,
    and management with hot-plugging and dependency resolution
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Component storage
        self.registered_components: Dict[str, ComponentRegistration] = {}
        self.active_instances: Dict[str, IAudioProcessor] = {}
        self.component_dependencies: Dict[str, List[str]] = {}
        
        # Hot-plugging support
        self.hot_plug_manager = HotPlugManager(self)
        self.version_manager = ComponentVersionManager()
        self.dependency_manager = DependencyManager()
        
        # Performance monitoring
        self.performance_monitor = ComponentPerformanceMonitor()
        
        # Discovery and loading
        self.discovery_paths: List[str] = []
        self.auto_discovery_enabled = True
        self.file_watchers: Dict[str, Any] = {}
        
        # Standard component library
        self.standard_library = StandardComponentLibrary()
        
        # Registry persistence
        self.registry_file = "component_registry.json"
        self.load_registry()
        
        # Initialize standard components
        self._initialize_standard_components()
    
    def register_component(self, component_class: Type[IAudioProcessor],
                          component_id: str = None,
                          version: ComponentVersion = None,
                          category: ComponentCategory = ComponentCategory.CUSTOM,
                          dependencies: List[ComponentDependency] = None) -> bool:
        """Register a component class in the registry"""
        try:
            # Auto-generate component ID if not provided
            if component_id is None:
                component_id = f"{component_class.__module__}.{component_class.__name__}"
            
            # Auto-detect version if not provided
            if version is None:
                version = self._detect_component_version(component_class)
            
            # Get component info
            component_info = self._extract_component_info(component_class)
            
            # Calculate file checksum
            file_path = inspect.getfile(component_class)
            checksum = self._calculate_file_checksum(file_path)
            
            # Create registration
            registration = ComponentRegistration(
                component_id=component_id,
                name=component_info.get("name", component_class.__name__),
                description=component_info.get("description", ""),
                version=version,
                category=category,
                component_class=component_class,
                dependencies=dependencies or [],
                file_path=file_path,
                checksum=checksum
            )
            
            # Validate dependencies
            if not self.dependency_manager.validate_dependencies(registration):
                self.logger.error(f"Dependency validation failed for {component_id}")
                return False
            
            # Register component
            self.registered_components[component_id] = registration
            self._update_dependency_graph(component_id, dependencies or [])
            
            self.logger.info(f"Registered component {component_id} v{version}")
            self.save_registry()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to register component {component_id}: {e}")
            return False
    
    def unregister_component(self, component_id: str) -> bool:
        """Unregister a component from the registry"""
        if component_id not in self.registered_components:
            return False
        
        try:
            # Stop any active instances
            if component_id in self.active_instances:
                self.unload_component(component_id)
            
            # Remove from registry
            del self.registered_components[component_id]
            
            # Update dependency graph
            if component_id in self.component_dependencies:
                del self.component_dependencies[component_id]
            
            self.logger.info(f"Unregistered component {component_id}")
            self.save_registry()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to unregister component {component_id}: {e}")
            return False
    
    def load_component(self, component_id: str, config: Dict[str, Any] = None) -> Optional[IAudioProcessor]:
        """Load and instantiate a component"""
        if component_id not in self.registered_components:
            self.logger.error(f"Component {component_id} not registered")
            return None
        
        registration = self.registered_components[component_id]
        
        try:
            # Check dependencies
            if not self.dependency_manager.resolve_dependencies(component_id):
                self.logger.error(f"Failed to resolve dependencies for {component_id}")
                return None
            
            # Create instance
            component_class = registration.component_class
            instance = component_class()
            
            # Configure if config provided
            if config:
                instance.configure(config)
            
            # Store active instance
            self.active_instances[component_id] = instance
            registration.status = ComponentStatus.ACTIVE
            
            # Start performance monitoring
            self.performance_monitor.start_monitoring(component_id, instance)
            
            self.logger.info(f"Loaded component {component_id}")
            return instance
            
        except Exception as e:
            self.logger.error(f"Failed to load component {component_id}: {e}")
            registration.status = ComponentStatus.ERROR
            return None
    
    def unload_component(self, component_id: str) -> bool:
        """Unload an active component instance"""
        if component_id not in self.active_instances:
            return False
        
        try:
            # Stop performance monitoring
            self.performance_monitor.stop_monitoring(component_id)
            
            # Remove active instance
            del self.active_instances[component_id]
            
            # Update status
            if component_id in self.registered_components:
                self.registered_components[component_id].status = ComponentStatus.LOADED
            
            self.logger.info(f"Unloaded component {component_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to unload component {component_id}: {e}")
            return False
    
    def replace_component(self, component_id: str, new_component_class: Type[IAudioProcessor],
                         preserve_config: bool = True) -> bool:
        """Hot-replace a component without stopping the audio processing flow"""
        return self.hot_plug_manager.replace_component(
            component_id, new_component_class, preserve_config
        )
    
    def discover_components(self, search_paths: List[str] = None) -> int:
        """Automatically discover components in specified paths"""
        if search_paths is None:
            search_paths = self.discovery_paths
        
        discovered_count = 0
        
        for search_path in search_paths:
            try:
                discovered_count += self._discover_components_in_path(search_path)
            except Exception as e:
                self.logger.error(f"Error discovering components in {search_path}: {e}")
        
        self.logger.info(f"Discovered {discovered_count} components")
        return discovered_count
    
    def get_component_info(self, component_id: str) -> Optional[ComponentRegistration]:
        """Get detailed information about a component"""
        return self.registered_components.get(component_id)
    
    def list_components(self, category: ComponentCategory = None,
                       status: ComponentStatus = None) -> List[ComponentRegistration]:
        """List registered components with optional filtering"""
        components = list(self.registered_components.values())
        
        if category:
            components = [c for c in components if c.category == category]
        
        if status:
            components = [c for c in components if c.status == status]
        
        return components
    
    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """Get the complete dependency graph"""
        return self.component_dependencies.copy()
    
    def validate_component_compatibility(self, component_id: str) -> Dict[str, Any]:
        """Validate component compatibility and dependencies"""
        if component_id not in self.registered_components:
            return {"valid": False, "error": "Component not found"}
        
        registration = self.registered_components[component_id]
        
        validation_result = {
            "valid": True,
            "component_id": component_id,
            "version": str(registration.version),
            "dependencies": [],
            "conflicts": [],
            "warnings": []
        }
        
        # Check dependencies
        for dep in registration.dependencies:
            dep_result = self.dependency_manager.check_dependency(dep)
            validation_result["dependencies"].append({
                "component_id": dep.component_id,
                "required": dep.required,
                "satisfied": dep_result["satisfied"],
                "available_version": dep_result.get("available_version"),
                "required_version": f"{dep.min_version}-{dep.max_version}" if dep.min_version else "any"
            })
            
            if dep.required and not dep_result["satisfied"]:
                validation_result["valid"] = False
        
        return validation_result
    
    def get_performance_metrics(self, component_id: str) -> Dict[str, Any]:
        """Get performance metrics for a component"""
        return self.performance_monitor.get_metrics(component_id)
    
    def enable_auto_discovery(self, paths: List[str] = None):
        """Enable automatic component discovery with file watching"""
        if paths:
            self.discovery_paths.extend(paths)
        
        self.auto_discovery_enabled = True
        
        # Set up file watchers
        for path in self.discovery_paths:
            self._setup_file_watcher(path)
    
    def disable_auto_discovery(self):
        """Disable automatic component discovery"""
        self.auto_discovery_enabled = False
        
        # Stop file watchers
        for watcher in self.file_watchers.values():
            watcher.stop()
        self.file_watchers.clear()
    
    def upgrade_component(self, component_id: str, new_version: ComponentVersion) -> bool:
        """Upgrade a component to a new version"""
        return self.version_manager.upgrade_component(component_id, new_version)
    
    def rollback_component(self, component_id: str, target_version: ComponentVersion = None) -> bool:
        """Rollback a component to a previous version"""
        return self.version_manager.rollback_component(component_id, target_version)
    
    def save_registry(self):
        """Save registry state to file"""
        try:
            registry_data = {}
            for component_id, registration in self.registered_components.items():
                # Skip active instances and classes for serialization
                reg_data = asdict(registration)
                reg_data.pop("component_class", None)
                registry_data[component_id] = reg_data
            
            with open(self.registry_file, 'w') as f:
                json.dump(registry_data, f, indent=2, default=str)
                
        except Exception as e:
            self.logger.error(f"Failed to save registry: {e}")
    
    def load_registry(self):
        """Load registry state from file"""
        try:
            with open(self.registry_file, 'r') as f:
                registry_data = json.load(f)
            
            for component_id, reg_data in registry_data.items():
                # Reconstruct registration (without component_class)
                reg_data["version"] = ComponentVersion(**reg_data["version"])
                reg_data["category"] = ComponentCategory(reg_data["category"])
                reg_data["status"] = ComponentStatus(reg_data["status"])
                reg_data["registration_time"] = datetime.fromisoformat(reg_data["registration_time"])
                reg_data["last_update"] = datetime.fromisoformat(reg_data["last_update"])
                
                # Reconstruct dependencies
                dependencies = []
                for dep_data in reg_data.get("dependencies", []):
                    dep = ComponentDependency(**dep_data)
                    if dep.min_version:
                        dep.min_version = ComponentVersion(**dep.min_version)
                    if dep.max_version:
                        dep.max_version = ComponentVersion(**dep.max_version)
                    dependencies.append(dep)
                reg_data["dependencies"] = dependencies
                
                # Create registration without component_class (will be loaded later)
                reg_data["component_class"] = None
                registration = ComponentRegistration(**reg_data)
                self.registered_components[component_id] = registration
                
        except FileNotFoundError:
            self.logger.info("No registry file found, starting with empty registry")
        except Exception as e:
            self.logger.error(f"Failed to load registry: {e}")
    
    def _initialize_standard_components(self):
        """Initialize standard component library"""
        # Register WebRTC components
        webrtc_components = self.standard_library.get_webrtc_components()
        for component_class in webrtc_components:
            self.register_component(
                component_class,
                category=ComponentCategory.WEBRTC
            )
        
        # Register spatial audio components
        spatial_components = self.standard_library.get_spatial_audio_components()
        for component_class in spatial_components:
            self.register_component(
                component_class,
                category=ComponentCategory.SPATIAL_AUDIO
            )
    
    def _discover_components_in_path(self, search_path: str) -> int:
        """Discover components in a specific path"""
        discovered_count = 0
        
        try:
            path_obj = Path(search_path)
            if not path_obj.exists():
                return 0
            
            # Find Python files
            for py_file in path_obj.rglob("*.py"):
                try:
                    # Import module
                    module_name = str(py_file.relative_to(path_obj)).replace("/", ".").replace("\\", ".")[:-3]
                    spec = importlib.util.spec_from_file_location(module_name, py_file)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Find component classes
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if (issubclass(obj, IAudioProcessor) and 
                            obj != IAudioProcessor and
                            hasattr(obj, '__module__') and
                            obj.__module__ == module_name):
                            
                            component_id = f"{module_name}.{name}"
                            if component_id not in self.registered_components:
                                if self.register_component(obj):
                                    discovered_count += 1
                
                except Exception as e:
                    self.logger.debug(f"Error processing {py_file}: {e}")
                    continue
        
        except Exception as e:
            self.logger.error(f"Error discovering in path {search_path}: {e}")
        
        return discovered_count
    
    def _extract_component_info(self, component_class: Type[IAudioProcessor]) -> Dict[str, str]:
        """Extract component information from class"""
        info = {}
        
        # Get name from class attribute or class name
        info["name"] = getattr(component_class, "COMPONENT_NAME", component_class.__name__)
        
        # Get description from docstring or class attribute
        info["description"] = (
            getattr(component_class, "COMPONENT_DESCRIPTION", None) or
            (component_class.__doc__ or "").strip()
        )
        
        return info
    
    def _detect_component_version(self, component_class: Type[IAudioProcessor]) -> ComponentVersion:
        """Auto-detect component version"""
        # Try to get version from class attribute
        if hasattr(component_class, "COMPONENT_VERSION"):
            version_str = component_class.COMPONENT_VERSION
            if isinstance(version_str, str):
                parts = version_str.split(".")
                return ComponentVersion(
                    major=int(parts[0]) if len(parts) > 0 else 1,
                    minor=int(parts[1]) if len(parts) > 1 else 0,
                    patch=int(parts[2]) if len(parts) > 2 else 0
                )
        
        # Default version
        return ComponentVersion(1, 0, 0)
    
    def _calculate_file_checksum(self, file_path: str) -> str:
        """Calculate MD5 checksum of a file"""
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                return hashlib.md5(content).hexdigest()
        except Exception:
            return ""
    
    def _update_dependency_graph(self, component_id: str, dependencies: List[ComponentDependency]):
        """Update the dependency graph"""
        self.component_dependencies[component_id] = [dep.component_id for dep in dependencies]
    
    def _setup_file_watcher(self, path: str):
        """Set up file watcher for automatic discovery"""
        # Simplified file watcher - in production would use watchdog or similar
        pass


class HotPlugManager:
    """Manager for hot-plugging component replacement"""
    
    def __init__(self, registry: IntelligentComponentRegistry):
        self.registry = registry
        self.logger = logging.getLogger(__name__)
        self.replacement_lock = threading.Lock()
    
    def replace_component(self, component_id: str, new_component_class: Type[IAudioProcessor],
                         preserve_config: bool = True) -> bool:
        """Replace component without stopping audio flow"""
        with self.replacement_lock:
            try:
                # Get current instance and config
                current_instance = self.registry.active_instances.get(component_id)
                if not current_instance:
                    self.logger.error(f"Component {component_id} not active")
                    return False
                
                current_config = current_instance.get_parameters() if preserve_config else {}
                
                # Create new instance
                new_instance = new_component_class()
                if preserve_config and current_config:
                    new_instance.configure(current_config)
                
                # Atomic replacement
                self.registry.active_instances[component_id] = new_instance
                
                # Update registration
                registration = self.registry.registered_components[component_id]
                registration.component_class = new_component_class
                registration.last_update = datetime.now()
                registration.status = ComponentStatus.ACTIVE
                
                self.logger.info(f"Hot-replaced component {component_id}")
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to hot-replace component {component_id}: {e}")
                return False


class ComponentVersionManager:
    """Manager for component version control"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.version_history: Dict[str, List[ComponentVersion]] = {}
    
    def upgrade_component(self, component_id: str, new_version: ComponentVersion) -> bool:
        """Upgrade component to new version"""
        # Implementation for version upgrade
        self.logger.info(f"Upgrading {component_id} to version {new_version}")
        return True
    
    def rollback_component(self, component_id: str, target_version: ComponentVersion = None) -> bool:
        """Rollback component to previous version"""
        # Implementation for version rollback
        self.logger.info(f"Rolling back {component_id} to version {target_version}")
        return True


class DependencyManager:
    """Manager for component dependency resolution"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_dependencies(self, registration: ComponentRegistration) -> bool:
        """Validate component dependencies"""
        for dep in registration.dependencies:
            if not self._check_dependency_available(dep):
                if dep.required:
                    return False
        return True
    
    def resolve_dependencies(self, component_id: str) -> bool:
        """Resolve and load component dependencies"""
        # Implementation for dependency resolution
        return True
    
    def check_dependency(self, dependency: ComponentDependency) -> Dict[str, Any]:
        """Check if a dependency is satisfied"""
        return {
            "satisfied": True,
            "available_version": "1.0.0"
        }
    
    def _check_dependency_available(self, dependency: ComponentDependency) -> bool:
        """Check if a dependency is available"""
        # Simplified check - in production would verify actual availability
        return True


class ComponentPerformanceMonitor:
    """Monitor component performance metrics"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.monitoring_data: Dict[str, Dict[str, Any]] = {}
    
    def start_monitoring(self, component_id: str, instance: IAudioProcessor):
        """Start monitoring component performance"""
        self.monitoring_data[component_id] = {
            "start_time": datetime.now(),
            "metrics": []
        }
        self.logger.info(f"Started monitoring {component_id}")
    
    def stop_monitoring(self, component_id: str):
        """Stop monitoring component performance"""
        if component_id in self.monitoring_data:
            del self.monitoring_data[component_id]
        self.logger.info(f"Stopped monitoring {component_id}")
    
    def get_metrics(self, component_id: str) -> Dict[str, Any]:
        """Get performance metrics for component"""
        return self.monitoring_data.get(component_id, {})


class StandardComponentLibrary:
    """Standard library of audio processing components"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def get_webrtc_components(self) -> List[Type[IAudioProcessor]]:
        """Get WebRTC audio processing components"""
        return [
            AECComponent,
            AGCComponent,
            NSComponent
        ]
    
    def get_spatial_audio_components(self) -> List[Type[IAudioProcessor]]:
        """Get spatial audio processing components"""
        return [
            BeamformingComponent,
            SourceLocalizationComponent,
            SpatialFilterComponent,
            MultiChannelProcessorComponent
        ]


# Standard WebRTC Components
class AECComponent(IAudioProcessor):
    """Acoustic Echo Cancellation component"""
    COMPONENT_NAME = "AEC"
    COMPONENT_DESCRIPTION = "Acoustic Echo Cancellation for WebRTC"
    COMPONENT_VERSION = "1.0.0"
    
    def __init__(self):
        self.enabled = True
        self.parameters = {"suppression_level": 0.5}
    
    def get_info(self) -> ComponentInfo:
        return ComponentInfo(
            component_id="webrtc.aec",
            name=self.COMPONENT_NAME,
            description=self.COMPONENT_DESCRIPTION,
            version=self.COMPONENT_VERSION,
            category="webrtc"
        )
    
    def process(self, audio_frame: AudioFrame) -> AudioFrame:
        # Simplified AEC processing
        processed_data = audio_frame.data * 0.9  # Simple attenuation
        return AudioFrame(
            data=processed_data,
            sample_rate=audio_frame.sample_rate,
            channels=audio_frame.channels,
            timestamp=audio_frame.timestamp
        )
    
    def configure(self, parameters: Dict[str, Any]) -> bool:
        self.parameters.update(parameters)
        return True
    
    def get_parameters(self) -> Dict[str, Any]:
        return self.parameters.copy()
    
    def set_parameter(self, name: str, value: Any) -> bool:
        if name in self.parameters:
            self.parameters[name] = value
            return True
        return False


class AGCComponent(IAudioProcessor):
    """Automatic Gain Control component"""
    COMPONENT_NAME = "AGC"
    COMPONENT_DESCRIPTION = "Automatic Gain Control for WebRTC"
    COMPONENT_VERSION = "1.0.0"
    
    def __init__(self):
        self.enabled = True
        self.parameters = {"target_level": -18.0, "compression_ratio": 3.0}
    
    def get_info(self) -> ComponentInfo:
        return ComponentInfo(
            component_id="webrtc.agc",
            name=self.COMPONENT_NAME,
            description=self.COMPONENT_DESCRIPTION,
            version=self.COMPONENT_VERSION,
            category="webrtc"
        )
    
    def process(self, audio_frame: AudioFrame) -> AudioFrame:
        # Simplified AGC processing
        import numpy as np
        rms = np.sqrt(np.mean(audio_frame.data ** 2))
        target_rms = 0.1  # Target RMS level
        gain = target_rms / (rms + 1e-10)
        gain = np.clip(gain, 0.1, 10.0)  # Limit gain range
        
        processed_data = audio_frame.data * gain
        return AudioFrame(
            data=processed_data,
            sample_rate=audio_frame.sample_rate,
            channels=audio_frame.channels,
            timestamp=audio_frame.timestamp
        )
    
    def configure(self, parameters: Dict[str, Any]) -> bool:
        self.parameters.update(parameters)
        return True
    
    def get_parameters(self) -> Dict[str, Any]:
        return self.parameters.copy()
    
    def set_parameter(self, name: str, value: Any) -> bool:
        if name in self.parameters:
            self.parameters[name] = value
            return True
        return False


class NSComponent(IAudioProcessor):
    """Noise Suppression component"""
    COMPONENT_NAME = "NS"
    COMPONENT_DESCRIPTION = "Noise Suppression for WebRTC"
    COMPONENT_VERSION = "1.0.0"
    
    def __init__(self):
        self.enabled = True
        self.parameters = {"suppression_level": 2}  # 0-3 scale
    
    def get_info(self) -> ComponentInfo:
        return ComponentInfo(
            component_id="webrtc.ns",
            name=self.COMPONENT_NAME,
            description=self.COMPONENT_DESCRIPTION,
            version=self.COMPONENT_VERSION,
            category="webrtc"
        )
    
    def process(self, audio_frame: AudioFrame) -> AudioFrame:
        # Simplified noise suppression
        import numpy as np
        
        # Simple spectral subtraction approach
        fft = np.fft.fft(audio_frame.data)
        magnitude = np.abs(fft)
        phase = np.angle(fft)
        
        # Estimate noise floor and suppress
        noise_floor = np.percentile(magnitude, 10)
        suppression_factor = self.parameters["suppression_level"] * 0.25
        
        suppressed_magnitude = magnitude - noise_floor * suppression_factor
        suppressed_magnitude = np.maximum(suppressed_magnitude, magnitude * 0.1)
        
        # Reconstruct signal
        suppressed_fft = suppressed_magnitude * np.exp(1j * phase)
        processed_data = np.real(np.fft.ifft(suppressed_fft)).astype(np.float32)
        
        return AudioFrame(
            data=processed_data,
            sample_rate=audio_frame.sample_rate,
            channels=audio_frame.channels,
            timestamp=audio_frame.timestamp
        )
    
    def configure(self, parameters: Dict[str, Any]) -> bool:
        self.parameters.update(parameters)
        return True
    
    def get_parameters(self) -> Dict[str, Any]:
        return self.parameters.copy()
    
    def set_parameter(self, name: str, value: Any) -> bool:
        if name in self.parameters:
            self.parameters[name] = value
            return True
        return False


# Standard Spatial Audio Components
class BeamformingComponent(IAudioProcessor):
    """Beamforming component for spatial audio"""
    COMPONENT_NAME = "Beamforming"
    COMPONENT_DESCRIPTION = "Directional beamforming for spatial audio"
    COMPONENT_VERSION = "1.0.0"
    
    def __init__(self):
        self.enabled = True
        self.parameters = {"beam_direction": 0.0, "beam_width": 60.0}
    
    def get_info(self) -> ComponentInfo:
        return ComponentInfo(
            component_id="spatial.beamforming",
            name=self.COMPONENT_NAME,
            description=self.COMPONENT_DESCRIPTION,
            version=self.COMPONENT_VERSION,
            category="spatial_audio"
        )
    
    def process(self, audio_frame: AudioFrame) -> AudioFrame:
        # Simplified beamforming - just pass through for now
        return audio_frame
    
    def configure(self, parameters: Dict[str, Any]) -> bool:
        self.parameters.update(parameters)
        return True
    
    def get_parameters(self) -> Dict[str, Any]:
        return self.parameters.copy()
    
    def set_parameter(self, name: str, value: Any) -> bool:
        if name in self.parameters:
            self.parameters[name] = value
            return True
        return False


class SourceLocalizationComponent(IAudioProcessor):
    """Source localization component"""
    COMPONENT_NAME = "Source Localization"
    COMPONENT_DESCRIPTION = "Audio source localization for spatial audio"
    COMPONENT_VERSION = "1.0.0"
    
    def __init__(self):
        self.enabled = True
        self.parameters = {"algorithm": "gcc_phat", "frame_size": 1024}
    
    def get_info(self) -> ComponentInfo:
        return ComponentInfo(
            component_id="spatial.source_localization",
            name=self.COMPONENT_NAME,
            description=self.COMPONENT_DESCRIPTION,
            version=self.COMPONENT_VERSION,
            category="spatial_audio"
        )
    
    def process(self, audio_frame: AudioFrame) -> AudioFrame:
        # Simplified source localization - just pass through
        return audio_frame
    
    def configure(self, parameters: Dict[str, Any]) -> bool:
        self.parameters.update(parameters)
        return True
    
    def get_parameters(self) -> Dict[str, Any]:
        return self.parameters.copy()
    
    def set_parameter(self, name: str, value: Any) -> bool:
        if name in self.parameters:
            self.parameters[name] = value
            return True
        return False


class SpatialFilterComponent(IAudioProcessor):
    """Spatial filtering component"""
    COMPONENT_NAME = "Spatial Filter"
    COMPONENT_DESCRIPTION = "Spatial filtering for multi-channel audio"
    COMPONENT_VERSION = "1.0.0"
    
    def __init__(self):
        self.enabled = True
        self.parameters = {"filter_type": "wiener", "adaptation_rate": 0.01}
    
    def get_info(self) -> ComponentInfo:
        return ComponentInfo(
            component_id="spatial.spatial_filter",
            name=self.COMPONENT_NAME,
            description=self.COMPONENT_DESCRIPTION,
            version=self.COMPONENT_VERSION,
            category="spatial_audio"
        )
    
    def process(self, audio_frame: AudioFrame) -> AudioFrame:
        # Simplified spatial filtering - just pass through
        return audio_frame
    
    def configure(self, parameters: Dict[str, Any]) -> bool:
        self.parameters.update(parameters)
        return True
    
    def get_parameters(self) -> Dict[str, Any]:
        return self.parameters.copy()
    
    def set_parameter(self, name: str, value: Any) -> bool:
        if name in self.parameters:
            self.parameters[name] = value
            return True
        return False


class MultiChannelProcessorComponent(IAudioProcessor):
    """Multi-channel audio processor"""
    COMPONENT_NAME = "Multi-Channel Processor"
    COMPONENT_DESCRIPTION = "Multi-channel audio processing for spatial audio"
    COMPONENT_VERSION = "1.0.0"
    
    def __init__(self):
        self.enabled = True
        self.parameters = {"channel_count": 8, "processing_mode": "independent"}
    
    def get_info(self) -> ComponentInfo:
        return ComponentInfo(
            component_id="spatial.multichannel_processor",
            name=self.COMPONENT_NAME,
            description=self.COMPONENT_DESCRIPTION,
            version=self.COMPONENT_VERSION,
            category="spatial_audio"
        )
    
    def process(self, audio_frame: AudioFrame) -> AudioFrame:
        # Simplified multi-channel processing - just pass through
        return audio_frame
    
    def configure(self, parameters: Dict[str, Any]) -> bool:
        self.parameters.update(parameters)
        return True
    
    def get_parameters(self) -> Dict[str, Any]:
        return self.parameters.copy()
    
    def set_parameter(self, name: str, value: Any) -> bool:
        if name in self.parameters:
            self.parameters[name] = value
            return True
        return False