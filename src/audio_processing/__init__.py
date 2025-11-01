"""
Audio Processing System

A real-time audio processing system for multimedia classrooms.
"""

__version__ = "0.1.0"
__author__ = "Audio Processing Team"

from .models import AudioFrame, AudioConfig, ProcessingResult, AudioMetrics
from .interfaces import IAudioService, IMetricsCollector
from .base import BaseAudioProcessor, BaseConfigurable, BaseAsyncService
from .container import DIContainer
from .service_manager import ServiceManager

__all__ = [
    "AudioFrame",
    "AudioConfig", 
    "ProcessingResult",
    "AudioMetrics",
    "IAudioService",
    "IMetricsCollector",
    "BaseAudioProcessor",
    "BaseConfigurable",
    "BaseAsyncService",
    "DIContainer",
    "ServiceManager",
]