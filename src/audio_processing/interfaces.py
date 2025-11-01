"""
Core interfaces for the audio processing system.

This module defines the fundamental interfaces that all audio processing
services and components must implement, ensuring consistent behavior
and enabling dependency injection.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, AsyncGenerator, Optional, List
from .models import AudioFrame, ProcessingResult, AudioConfig, AudioMetrics


class IAudioService(ABC):
    """
    Base interface for all audio processing services.
    
    Defines the lifecycle management methods and core processing
    interface that all audio services must implement.
    """
    
    @abstractmethod
    async def start(self) -> None:
        """
        Start the audio service.
        
        Initialize resources, establish connections, and prepare
        the service for processing audio frames.
        
        Raises:
            ServiceError: If service fails to start
        """
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the audio service.
        
        Clean up resources, close connections, and gracefully
        shut down the service.
        """
        pass
    
    @abstractmethod
    async def process(self, frame: AudioFrame) -> ProcessingResult:
        """
        Process a single audio frame.
        
        Args:
            frame: Input audio frame to process
            
        Returns:
            ProcessingResult containing the processed frame and metrics
        """
        pass
    
    @abstractmethod
    def get_metrics(self) -> AudioMetrics:
        """
        Get current performance metrics for the service.
        
        Returns:
            AudioMetrics object with current performance data
        """
        pass
    
    @abstractmethod
    def get_config(self) -> AudioConfig:
        """
        Get current service configuration.
        
        Returns:
            AudioConfig object with current settings
        """
        pass
    
    @abstractmethod
    async def update_config(self, config: AudioConfig) -> None:
        """
        Update service configuration at runtime.
        
        Args:
            config: New configuration to apply
            
        Raises:
            ConfigError: If configuration is invalid or cannot be applied
        """
        pass
    
    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Check if the service is currently running."""
        pass
    
    @property
    @abstractmethod
    def service_name(self) -> str:
        """Get the unique name of this service."""
        pass


class IMetricsCollector(ABC):
    """
    Interface for collecting and aggregating performance metrics.
    
    Provides methods for recording various types of metrics
    and retrieving aggregated statistics.
    """
    
    @abstractmethod
    def record_latency(self, service_name: str, latency_ms: float) -> None:
        """
        Record processing latency for a service.
        
        Args:
            service_name: Name of the service
            latency_ms: Processing latency in milliseconds
        """
        pass
    
    @abstractmethod
    def record_cpu_usage(self, service_name: str, cpu_percent: float) -> None:
        """
        Record CPU usage for a service.
        
        Args:
            service_name: Name of the service
            cpu_percent: CPU usage percentage
        """
        pass
    
    @abstractmethod
    def record_memory_usage(self, service_name: str, memory_mb: float) -> None:
        """
        Record memory usage for a service.
        
        Args:
            service_name: Name of the service
            memory_mb: Memory usage in megabytes
        """
        pass
    
    @abstractmethod
    def record_audio_level(self, service_name: str, level_dbfs: float, 
                          is_input: bool = True) -> None:
        """
        Record audio level measurement.
        
        Args:
            service_name: Name of the service
            level_dbfs: Audio level in dBFS
            is_input: True for input level, False for output level
        """
        pass
    
    @abstractmethod
    def record_frame_drop(self, service_name: str) -> None:
        """
        Record a dropped frame event.
        
        Args:
            service_name: Name of the service that dropped the frame
        """
        pass
    
    @abstractmethod
    def get_service_metrics(self, service_name: str) -> AudioMetrics:
        """
        Get aggregated metrics for a specific service.
        
        Args:
            service_name: Name of the service
            
        Returns:
            AudioMetrics object with aggregated data
        """
        pass
    
    @abstractmethod
    def get_system_metrics(self) -> Dict[str, AudioMetrics]:
        """
        Get metrics for all services in the system.
        
        Returns:
            Dictionary mapping service names to their metrics
        """
        pass
    
    @abstractmethod
    def reset_metrics(self, service_name: Optional[str] = None) -> None:
        """
        Reset metrics for a service or all services.
        
        Args:
            service_name: Service to reset, or None for all services
        """
        pass


class IConfigurable(ABC):
    """
    Interface for components that can be configured at runtime.
    
    Provides methods for configuration management and validation.
    """
    
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate a configuration dictionary.
        
        Args:
            config: Configuration to validate
            
        Returns:
            True if configuration is valid, False otherwise
        """
        pass
    
    @abstractmethod
    async def apply_config(self, config: Dict[str, Any]) -> None:
        """
        Apply a new configuration.
        
        Args:
            config: Configuration to apply
            
        Raises:
            ConfigError: If configuration cannot be applied
        """
        pass
    
    @abstractmethod
    def get_config_schema(self) -> Dict[str, Any]:
        """
        Get the configuration schema for this component.
        
        Returns:
            JSON schema describing valid configuration
        """
        pass


class IEventHandler(ABC):
    """
    Interface for handling system events.
    
    Components can implement this interface to receive
    notifications about system events.
    """
    
    @abstractmethod
    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """
        Handle a system event.
        
        Args:
            event_type: Type of event (e.g., 'service_started', 'error_occurred')
            event_data: Event-specific data
        """
        pass
    
    @abstractmethod
    def get_supported_events(self) -> List[str]:
        """
        Get list of event types this handler supports.
        
        Returns:
            List of supported event type strings
        """
        pass


class IStreamProcessor(ABC):
    """
    Interface for components that process continuous audio streams.
    
    Extends IAudioService with stream-specific functionality.
    """
    
    @abstractmethod
    async def process_stream(self, 
                           input_stream: AsyncGenerator[AudioFrame, None]
                           ) -> AsyncGenerator[ProcessingResult, None]:
        """
        Process a continuous stream of audio frames.
        
        Args:
            input_stream: Async generator yielding input audio frames
            
        Yields:
            ProcessingResult objects for each processed frame
        """
        pass
    
    @abstractmethod
    def get_stream_info(self) -> Dict[str, Any]:
        """
        Get information about the current stream.
        
        Returns:
            Dictionary with stream metadata (sample rate, channels, etc.)
        """
        pass


class IPluginInterface(ABC):
    """
    Interface for audio processing plugins.
    
    Defines the contract that all plugins must implement
    to be loaded by the plugin manager.
    """
    
    @abstractmethod
    def get_plugin_info(self) -> Dict[str, Any]:
        """
        Get plugin metadata.
        
        Returns:
            Dictionary with plugin name, version, description, etc.
        """
        pass
    
    @abstractmethod
    def get_required_dependencies(self) -> List[str]:
        """
        Get list of required dependencies.
        
        Returns:
            List of dependency names/versions
        """
        pass
    
    @abstractmethod
    async def initialize(self, config: AudioConfig) -> None:
        """
        Initialize the plugin with given configuration.
        
        Args:
            config: Audio system configuration
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up plugin resources."""
        pass