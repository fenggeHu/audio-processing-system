"""
Core data models for the audio processing system.

This module defines the fundamental data structures used throughout
the audio processing pipeline, including AudioFrame, AudioConfig,
ProcessingResult, and AudioMetrics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional
import numpy as np
from pydantic import BaseModel, Field, field_validator, ConfigDict


@dataclass
class AudioFrame:
    """
    Standard audio frame data structure.
    
    Represents a single frame of multi-channel audio data with metadata.
    Used throughout the processing pipeline for consistent data exchange.
    """
    timestamp: datetime
    sample_rate: int
    channels: int
    frame_size: int
    data: np.ndarray  # shape: (channels, frame_size)
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate audio frame data after initialization."""
        if self.data.shape != (self.channels, self.frame_size):
            raise ValueError(
                f"Data shape {self.data.shape} doesn't match "
                f"expected ({self.channels}, {self.frame_size})"
            )
        
        if self.sample_rate <= 0:
            raise ValueError("Sample rate must be positive")
            
        if self.channels <= 0:
            raise ValueError("Channel count must be positive")
            
        if self.frame_size <= 0:
            raise ValueError("Frame size must be positive")
    
    def to_mono(self) -> 'AudioFrame':
        """Convert multi-channel audio to mono by averaging channels."""
        if self.channels == 1:
            return self
            
        mono_data = np.mean(self.data, axis=0, keepdims=True)
        return AudioFrame(
            timestamp=self.timestamp,
            sample_rate=self.sample_rate,
            channels=1,
            frame_size=self.frame_size,
            data=mono_data,
            metadata=self.metadata.copy() if self.metadata else {}
        )
    
    def resample(self, target_rate: int) -> 'AudioFrame':
        """
        Resample audio to target sample rate.
        
        Note: This is a placeholder implementation.
        Production code should use proper resampling algorithms.
        """
        if target_rate == self.sample_rate:
            return self
            
        # Simple linear interpolation for demonstration
        # In production, use scipy.signal.resample or librosa
        ratio = target_rate / self.sample_rate
        new_frame_size = int(self.frame_size * ratio)
        
        # Placeholder resampling - replace with proper implementation
        resampled_data = np.zeros((self.channels, new_frame_size))
        for ch in range(self.channels):
            resampled_data[ch] = np.interp(
                np.linspace(0, self.frame_size - 1, new_frame_size),
                np.arange(self.frame_size),
                self.data[ch]
            )
        
        return AudioFrame(
            timestamp=self.timestamp,
            sample_rate=target_rate,
            channels=self.channels,
            frame_size=new_frame_size,
            data=resampled_data,
            metadata=self.metadata.copy() if self.metadata else {}
        )
    
    def get_rms_level(self) -> float:
        """Calculate RMS level of the audio frame in dB."""
        rms = np.sqrt(np.mean(self.data ** 2))
        if rms == 0:
            return -np.inf
        return 20 * np.log10(rms)
    
    def copy(self) -> 'AudioFrame':
        """Create a deep copy of the audio frame."""
        return AudioFrame(
            timestamp=self.timestamp,
            sample_rate=self.sample_rate,
            channels=self.channels,
            frame_size=self.frame_size,
            data=self.data.copy(),
            metadata=self.metadata.copy() if self.metadata else {}
        )


class AudioConfig(BaseModel):
    """
    Audio configuration data model with validation.
    
    Defines system-wide audio parameters and processing settings.
    Uses Pydantic for automatic validation and serialization.
    """
    sample_rate: int = Field(48000, ge=8000, le=96000, description="Audio sample rate in Hz")
    frame_size: int = Field(480, ge=64, le=2048, description="Frame size in samples (10ms at 48kHz)")
    channels: int = Field(8, ge=1, le=32, description="Number of audio channels")
    buffer_size: int = Field(4096, ge=512, le=16384, description="Buffer size in samples")
    bit_depth: int = Field(16, ge=8, le=32, description="Audio bit depth (8, 16, 24, or 32 bits)")
    
    # Processing parameters
    enable_ssl: bool = Field(True, description="Enable sound source localization")
    enable_beamforming: bool = Field(True, description="Enable beamforming")
    enable_aec: bool = Field(True, description="Enable acoustic echo cancellation")
    enable_denoise: bool = Field(True, description="Enable noise reduction")
    enable_agc: bool = Field(True, description="Enable automatic gain control")
    
    # Performance settings
    max_latency_ms: float = Field(40.0, ge=10.0, le=200.0, description="Maximum allowed latency in ms")
    cpu_limit_percent: float = Field(80.0, ge=10.0, le=100.0, description="CPU usage limit percentage")
    
    model_config = ConfigDict(validate_assignment=True, extra="forbid")
    
    @field_validator('frame_size')
    @classmethod
    def validate_frame_size(cls, v: int, info) -> int:
        """Ensure frame size is reasonable for the sample rate."""
        sample_rate = info.data.get('sample_rate', 48000) if info.data else 48000
        frame_duration_ms = (v / sample_rate) * 1000
        
        if frame_duration_ms < 5.0 or frame_duration_ms > 50.0:
            raise ValueError(
                f"Frame duration {frame_duration_ms:.1f}ms is outside "
                "recommended range (5-50ms)"
            )
        return v
    
    def get_frame_duration_ms(self) -> float:
        """Get frame duration in milliseconds."""
        return (self.frame_size / self.sample_rate) * 1000
    
    def get_frames_per_second(self) -> float:
        """Get number of frames processed per second."""
        return self.sample_rate / self.frame_size


@dataclass
class ProcessingResult:
    """
    Result of audio processing operation.
    
    Contains the processed audio data, success status, performance metrics,
    and any error information.
    """
    success: bool
    data: Optional[AudioFrame] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None
    processing_time_ms: float = 0.0
    
    def __post_init__(self) -> None:
        """Validate processing result after initialization."""
        if self.success and self.data is None:
            raise ValueError("Successful result must contain data")
        
        if not self.success and self.error is None:
            raise ValueError("Failed result must contain error message")
    
    @classmethod
    def success_result(cls, data: AudioFrame, 
                      metrics: Optional[Dict[str, float]] = None,
                      processing_time_ms: float = 0.0) -> 'ProcessingResult':
        """Create a successful processing result."""
        return cls(
            success=True,
            data=data,
            metrics=metrics or {},
            processing_time_ms=processing_time_ms
        )
    
    @classmethod
    def error_result(cls, error: str, 
                    processing_time_ms: float = 0.0) -> 'ProcessingResult':
        """Create a failed processing result."""
        return cls(
            success=False,
            error=error,
            processing_time_ms=processing_time_ms
        )


class AudioMetrics(BaseModel):
    """
    Audio performance metrics data model.
    
    Standardizes performance indicators collected throughout
    the audio processing pipeline.
    """
    # Latency metrics
    processing_latency_ms: float = Field(0.0, ge=0.0, description="Processing latency in milliseconds")
    end_to_end_latency_ms: float = Field(0.0, ge=0.0, description="Total system latency in milliseconds")
    
    # Quality metrics
    snr_db: Optional[float] = Field(None, description="Signal-to-noise ratio in dB")
    thd_percent: Optional[float] = Field(None, ge=0.0, le=100.0, description="Total harmonic distortion percentage")
    erle_db: Optional[float] = Field(None, description="Echo return loss enhancement in dB")
    
    # System metrics
    cpu_usage_percent: float = Field(0.0, ge=0.0, le=100.0, description="CPU usage percentage")
    memory_usage_mb: float = Field(0.0, ge=0.0, description="Memory usage in MB")
    
    # Audio level metrics
    input_level_dbfs: float = Field(-60.0, description="Input audio level in dBFS")
    output_level_dbfs: float = Field(-60.0, description="Output audio level in dBFS")
    
    # Processing statistics
    frames_processed: int = Field(0, ge=0, description="Total frames processed")
    frames_dropped: int = Field(0, ge=0, description="Total frames dropped")
    
    model_config = ConfigDict(validate_assignment=True, extra="allow")  # Allow additional metrics
    
    def get_frame_drop_rate(self) -> float:
        """Calculate frame drop rate as percentage."""
        total_frames = self.frames_processed + self.frames_dropped
        if total_frames == 0:
            return 0.0
        return (self.frames_dropped / total_frames) * 100.0
    
    def is_performance_acceptable(self, config: AudioConfig) -> bool:
        """Check if performance metrics meet acceptable thresholds."""
        if self.end_to_end_latency_ms > config.max_latency_ms:
            return False
        
        if self.cpu_usage_percent > config.cpu_limit_percent:
            return False
        
        if self.get_frame_drop_rate() > 1.0:  # More than 1% drop rate
            return False
        
        return True