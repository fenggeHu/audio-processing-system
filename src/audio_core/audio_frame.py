"""
Audio Frame Data Structure

Defines the audio frame data structure and related utilities.
"""

import numpy as np
from typing import Optional, Dict, Any
from dataclasses import dataclass
import time


@dataclass
class AudioFrameMetadata:
    """Metadata for audio frames."""
    timestamp: float
    sequence_number: int
    sample_rate: int
    channels: int
    bit_depth: int
    device_id: str
    quality_metrics: Optional[Dict[str, float]] = None


class AudioFrame:
    """Audio frame with data and metadata."""
    
    def __init__(
        self,
        data: np.ndarray,
        sample_rate: int,
        channels: int = None,
        timestamp: float = None,
        device_id: str = "unknown"
    ):
        self.data = data
        self.sample_rate = sample_rate
        self.channels = channels or (data.shape[1] if len(data.shape) > 1 else 1)
        self.timestamp = timestamp or time.time()
        self.device_id = device_id
        
        # Frame properties
        self.frame_size = len(data)
        self.duration_ms = (self.frame_size / sample_rate) * 1000
        
        # Quality metrics (to be populated by processing components)
        self.quality_metrics: Dict[str, float] = {}
    
    def get_duration_ms(self) -> float:
        """Get frame duration in milliseconds."""
        return self.duration_ms
    
    def get_rms_level(self) -> float:
        """Get RMS level of the audio frame."""
        if len(self.data) == 0:
            return 0.0
        return float(np.sqrt(np.mean(self.data ** 2)))
    
    def get_peak_level(self) -> float:
        """Get peak level of the audio frame."""
        if len(self.data) == 0:
            return 0.0
        return float(np.max(np.abs(self.data)))
    
    def is_silent(self, threshold: float = 0.001) -> bool:
        """Check if frame is silent below threshold."""
        return self.get_rms_level() < threshold
    
    def copy(self) -> 'AudioFrame':
        """Create a copy of the audio frame."""
        return AudioFrame(
            data=self.data.copy(),
            sample_rate=self.sample_rate,
            channels=self.channels,
            timestamp=self.timestamp,
            device_id=self.device_id
        )