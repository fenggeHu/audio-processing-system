"""
Production Audio Service Interface

This module defines the core interface for production audio services,
providing a unified API for real-time audio capture and processing.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from enum import Enum

from .models import AudioFrame, AudioProcessingConfig, ProcessingMetrics
from .interfaces import IPluggableComponent


class CaptureMode(Enum):
    """Audio capture modes"""
    SINGLE_DEVICE = "single_device"
    MULTI_DEVICE = "multi_device"
    SYNCHRONIZED = "synchronized"
    SELECTIVE = "selective"


class AudioQuality(Enum):
    """Audio quality levels"""
    BASIC = "basic"
    STANDARD = "standard"
    HIGH = "high"
    PROFESSIONAL = "professional"


class IProductionAudioService(IPluggableComponent):
    """
    Core interface for production audio services providing unified
    audio capture, processing, and monitoring capabilities.
    
    Implements requirements: 2.1, 2.2, 2.3, 6.1, 6.2, 6.3
    """
    
    @abstractmethod
    def configure_capture(self, config: AudioProcessingConfig) -> bool:
        """Configure audio capture parameters"""
        pass
    
    @abstractmethod
    def start_capture(self) -> bool:
        """Start audio capture"""
        pass
    
    @abstractmethod
    def stop_capture(self) -> bool:
        """Stop audio capture"""
        pass
    
    @abstractmethod
    def pause_capture(self) -> bool:
        """Pause audio capture"""
        pass
    
    @abstractmethod
    def resume_capture(self) -> bool:
        """Resume audio capture"""
        pass
    
    @abstractmethod
    def get_audio_frame(self, timeout_ms: int = 100) -> Optional[AudioFrame]:
        """Get next available audio frame"""
        pass
    
    @abstractmethod
    def register_frame_callback(self, callback: Callable[[AudioFrame], None]) -> bool:
        """Register callback for audio frame events"""
        pass
    
    @abstractmethod
    def unregister_frame_callback(self, callback: Callable[[AudioFrame], None]) -> bool:
        """Unregister frame callback"""
        pass
    
    @abstractmethod
    def get_capture_metrics(self) -> ProcessingMetrics:
        """Get current capture performance metrics"""
        pass
    
    @abstractmethod
    def get_device_status(self) -> Dict[str, Any]:
        """Get status of all capture devices"""
        pass
    
    @abstractmethod
    def set_device_gain(self, device_id: str, gain_db: float) -> bool:
        """Set input gain for specific device"""
        pass
    
    @abstractmethod
    def mute_device(self, device_id: str, muted: bool) -> bool:
        """Mute/unmute specific device"""
        pass
    
    @abstractmethod
    def select_audio_sources(self, source_ids: List[str]) -> bool:
        """Select specific audio sources for capture"""
        pass
    
    @abstractmethod
    def enable_all_sources(self) -> bool:
        """Enable all available audio sources"""
        pass
    
    @abstractmethod
    def get_quality_metrics(self) -> Dict[str, Any]:
        """Get real-time audio quality metrics"""
        pass
    
    @abstractmethod
    def calibrate_timing(self) -> bool:
        """Calibrate timing and synchronization"""
        pass