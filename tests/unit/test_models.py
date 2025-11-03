"""
Tests for core data models.
"""

import pytest
import numpy as np
from datetime import datetime
from pydantic import ValidationError

from src.audio_processing.models import AudioFrame, AudioConfig, ProcessingResult, AudioMetrics


class TestAudioFrame:
    """Test AudioFrame data model."""
    
    def test_create_valid_frame(self):
        """Test creating a valid audio frame."""
        timestamp = datetime.now()
        data = np.random.randn(2, 480)  # 2 channels, 480 samples
        
        frame = AudioFrame(
            timestamp=timestamp,
            sample_rate=48000,
            channels=2,
            frame_size=480,
            data=data
        )
        
        assert frame.timestamp == timestamp
        assert frame.sample_rate == 48000
        assert frame.channels == 2
        assert frame.frame_size == 480
        assert np.array_equal(frame.data, data)
    
    def test_invalid_data_shape(self):
        """Test that invalid data shape raises error."""
        timestamp = datetime.now()
        data = np.random.randn(3, 480)  # Wrong number of channels
        
        with pytest.raises(ValueError, match="Data shape"):
            AudioFrame(
                timestamp=timestamp,
                sample_rate=48000,
                channels=2,  # Expecting 2 channels
                frame_size=480,
                data=data
            )
    
    def test_to_mono(self):
        """Test converting stereo to mono."""
        timestamp = datetime.now()
        data = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])  # 2 channels
        
        frame = AudioFrame(
            timestamp=timestamp,
            sample_rate=48000,
            channels=2,
            frame_size=3,
            data=data
        )
        
        mono_frame = frame.to_mono()
        
        assert mono_frame.channels == 1
        assert mono_frame.frame_size == 3
        expected_mono = np.array([[2.5, 3.5, 4.5]])  # Average of channels
        np.testing.assert_array_equal(mono_frame.data, expected_mono)
    
    def test_get_rms_level(self):
        """Test RMS level calculation."""
        timestamp = datetime.now()
        # Create a known signal: 1kHz sine wave
        t = np.linspace(0, 0.01, 480)  # 10ms at 48kHz
        signal = np.sin(2 * np.pi * 1000 * t) * 0.5  # -6dBFS
        data = signal.reshape(1, -1)
        
        frame = AudioFrame(
            timestamp=timestamp,
            sample_rate=48000,
            channels=1,
            frame_size=480,
            data=data
        )
        
        rms_level = frame.get_rms_level()
        # Should be approximately -9dB for 0.5 amplitude sine wave
        assert -10 < rms_level < -8
    
    def test_copy(self):
        """Test frame copying."""
        timestamp = datetime.now()
        data = np.random.randn(2, 480)
        metadata = {"test": "value"}
        
        frame = AudioFrame(
            timestamp=timestamp,
            sample_rate=48000,
            channels=2,
            frame_size=480,
            data=data,
            metadata=metadata
        )
        
        copied_frame = frame.copy()
        
        assert copied_frame.timestamp == frame.timestamp
        assert copied_frame.sample_rate == frame.sample_rate
        assert np.array_equal(copied_frame.data, frame.data)
        assert copied_frame.metadata == frame.metadata
        
        # Ensure it's a deep copy
        copied_frame.data[0, 0] = 999
        assert frame.data[0, 0] != 999


class TestAudioConfig:
    """Test AudioConfig data model."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = AudioConfig()
        
        assert config.sample_rate == 48000
        assert config.frame_size == 480
        assert config.channels == 8
        assert config.enable_ssl is True
        assert config.max_latency_ms == 40.0
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = AudioConfig(
            sample_rate=44100,
            frame_size=1024,
            channels=4,
            enable_aec=False
        )
        
        assert config.sample_rate == 44100
        assert config.frame_size == 1024
        assert config.channels == 4
        assert config.enable_aec is False
    
    def test_validation_errors(self):
        """Test configuration validation."""
        # Invalid sample rate
        with pytest.raises(ValidationError):
            AudioConfig(sample_rate=1000)  # Too low
        
        # Invalid frame size
        with pytest.raises(ValidationError):
            AudioConfig(frame_size=32)  # Too small
        
        # Invalid channels
        with pytest.raises(ValidationError):
            AudioConfig(channels=0)  # Must be positive
    
    def test_frame_duration_calculation(self):
        """Test frame duration calculation."""
        config = AudioConfig(sample_rate=48000, frame_size=480)
        duration = config.get_frame_duration_ms()
        assert abs(duration - 10.0) < 0.1  # Should be 10ms
    
    def test_frames_per_second(self):
        """Test frames per second calculation."""
        config = AudioConfig(sample_rate=48000, frame_size=480)
        fps = config.get_frames_per_second()
        assert abs(fps - 100.0) < 0.1  # Should be 100 fps


class TestProcessingResult:
    """Test ProcessingResult data model."""
    
    def test_success_result(self):
        """Test creating successful result."""
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=1,
            frame_size=480,
            data=np.zeros((1, 480))
        )
        
        result = ProcessingResult.success_result(
            data=frame,
            metrics={"latency": 5.0},
            processing_time_ms=3.2
        )
        
        assert result.success is True
        assert result.data == frame
        assert result.metrics["latency"] == 5.0
        assert result.processing_time_ms == 3.2
        assert result.error is None
    
    def test_error_result(self):
        """Test creating error result."""
        result = ProcessingResult.error_result(
            error="Processing failed",
            processing_time_ms=1.5
        )
        
        assert result.success is False
        assert result.data is None
        assert result.error == "Processing failed"
        assert result.processing_time_ms == 1.5
    
    def test_validation_errors(self):
        """Test result validation."""
        # Success result without data
        with pytest.raises(ValueError, match="Successful result must contain data"):
            ProcessingResult(success=True, data=None)
        
        # Error result without error message
        with pytest.raises(ValueError, match="Failed result must contain error message"):
            ProcessingResult(success=False, error=None)


class TestAudioMetrics:
    """Test AudioMetrics data model."""
    
    def test_default_metrics(self):
        """Test default metrics values."""
        metrics = AudioMetrics()
        
        assert metrics.processing_latency_ms == 0.0
        assert metrics.cpu_usage_percent == 0.0
        assert metrics.frames_processed == 0
        assert metrics.frames_dropped == 0
    
    def test_frame_drop_rate(self):
        """Test frame drop rate calculation."""
        metrics = AudioMetrics(
            frames_processed=95,
            frames_dropped=5
        )
        
        drop_rate = metrics.get_frame_drop_rate()
        assert abs(drop_rate - 5.0) < 0.1  # Should be 5%
    
    def test_performance_check(self):
        """Test performance acceptability check."""
        config = AudioConfig(max_latency_ms=40.0, cpu_limit_percent=80.0)
        
        # Good performance
        good_metrics = AudioMetrics(
            end_to_end_latency_ms=30.0,
            cpu_usage_percent=60.0,
            frames_processed=100,
            frames_dropped=0
        )
        assert good_metrics.is_performance_acceptable(config) is True
        
        # High latency
        bad_latency = AudioMetrics(
            end_to_end_latency_ms=50.0,
            cpu_usage_percent=60.0,
            frames_processed=100,
            frames_dropped=0
        )
        assert bad_latency.is_performance_acceptable(config) is False
        
        # High CPU usage
        bad_cpu = AudioMetrics(
            end_to_end_latency_ms=30.0,
            cpu_usage_percent=90.0,
            frames_processed=100,
            frames_dropped=0
        )
        assert bad_cpu.is_performance_acceptable(config) is False
        
        # High drop rate
        bad_drops = AudioMetrics(
            end_to_end_latency_ms=30.0,
            cpu_usage_percent=60.0,
            frames_processed=90,
            frames_dropped=10  # >1% drop rate
        )
        assert bad_drops.is_performance_acceptable(config) is False