"""
Audio Processing Components Registry

Registry for managing pluggable audio processing components.
This will be implemented in subsequent tasks.
"""

from typing import Dict, List, Type, Any
from abc import ABC, abstractmethod


class IAudioProcessor(ABC):
    """Interface for audio processors."""
    
    @abstractmethod
    def process(self, audio_data: Any) -> Any:
        """Process audio data."""
        pass
    
    @abstractmethod
    def configure(self, config: Dict[str, Any]) -> None:
        """Configure the processor."""
        pass
    
    @abstractmethod
    def get_metrics(self) -> Dict[str, float]:
        """Get processing metrics."""
        pass


class ComponentRegistry:
    """Registry for audio processing components - placeholder for task 5.1."""
    
    def __init__(self):
        self.components: Dict[str, Type[IAudioProcessor]] = {}
        self.instances: Dict[str, IAudioProcessor] = {}
    
    def register_component(self, name: str, component_class: Type[IAudioProcessor]) -> None:
        """Register a processing component."""
        # TODO: Implement in task 5.1
        pass
    
    def create_component(self, name: str, config: Dict[str, Any] = None) -> IAudioProcessor:
        """Create an instance of a registered component."""
        # TODO: Implement in task 5.1
        pass
    
    def list_components(self) -> List[str]:
        """List all registered components."""
        # TODO: Implement in task 5.1
        return list(self.components.keys())