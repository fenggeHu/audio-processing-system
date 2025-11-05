"""
Production Audio Processing System

A production-grade audio processing system designed for multimedia
classroom environments with real-time audio processing capabilities.
"""

__version__ = "1.0.0"
__author__ = "Production Audio System Team"
__description__ = "Production-grade audio processing system for multimedia classroom environments"

# Import main components
from .audio_core import DeviceManager, HardwareAbstractionLayer, AudioFrame
from .processing import ProcessingChain, ComponentRegistry, AudioPipeline
from .visualization import Dashboard, AudioMonitor, WebInterface
from .config import AudioConfig, SystemConfig, PlatformConfigManager, EmbeddedConfigManager

__all__ = [
    # Core components
    "DeviceManager",
    "HardwareAbstractionLayer", 
    "AudioFrame",
    
    # Processing components
    "ProcessingChain",
    "ComponentRegistry",
    "AudioPipeline",
    
    # Visualization components
    "Dashboard",
    "AudioMonitor",
    "WebInterface",
    
    # Configuration
    "AudioConfig",
    "SystemConfig",
    "PlatformConfigManager",
    "EmbeddedConfigManager",
]