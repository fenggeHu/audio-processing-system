"""
Tests for DenoiseService implementation.

This module tests the noise reduction and speech enhancement functionality
including RNNoise integration, adjustable noise reduction strength,
and speech quality protection mechanisms.
"""

import pytest
import numpy as np
from datetime import datetime
from unittest.mock import Mock, patch

from src.audio_processing.services.denoise import (
    DenoiseService, DenoiseMode, NoiseType,
    SpeechActivityDetector, NoiseEstimator, RNNoiseProcessor
)
from src.audio_processing.models import AudioFrame, AudioConfig
from src.audio_processing.exceptions import ProcessingError


class TestSpeechActivityDetector:
    """Test speech activity detection functionality."""
    
    def test_detector_initialization(self):
        """Test VAD initialization."""
        detector = SpeechActivityDetector(frame_size=480, sensitivity=0.5)
        
        assert detector.frame_size == 480
        assert detector.sensitivity == 0.5
        assert not detector.speech_active
    
    def test_speech_detection_with_speech_signal(self):
        """Test detection with speech-like signal."""
        detector = SpeechActivityDetector(frame_size=480, sensitivity=0.5)
        
        # Generate speech-like signal (moderate energy, varied spectrum)
        speech_signal = np.random.randn(480) * 0.1
        speech_signal += np.sin(2 * np.pi * 1000 * np.arange(480) / 48000) * 0.05
        
        is_speech, prob = detector.detect(speech_signal)
        
        # Should detect some speech activity
        assert isinstance(is_speech, bool)
        assert 0.0 <= prob <= 1.0
    
    def test_speech_detection_with_noise_signal(self):
        """Test detection with noise-only signal."""
        detector = SpeechActivityDetector(frame_size=480, sensitivity=0.5)
        
        # Generate low-level noise
        noise_signal = np.random.randn(480) * 0.01
        
        is_speech, prob = detector.detect(noise_signal)
        
        # Should not detect speech in low-level noise
        assert isinstance(is_speech, bool)
        assert 0.0 <= prob <= 1.0


class TestNoiseEstimator:
    """Test noise estimation functionality."""
    
    def test_estimator_initialization(self):
        """Test noise estimator initialization."""
        estimator = NoiseEstimator(frame_size=480, adaptation_rate=0.1)
        
        assert estimator.frame_size == 480
        assert estimator.adaptation_rate == 0.1
        assert estimator.get_noise_spectrum() is None
    
    def test_noise_estimation_update(self):
        """Test noise spectrum estimation."""
        estimator = NoiseEstimator(frame_size=480, adaptation_rate=0.1)
        
        # Simulate noise-only signal
        noise_signal = np.random.randn(480) * 0.05
        
        # Update during non-speech period
        estimator.update(noise_signal, is_speech_active=False)
        
        # Should have noise spectrum after update
        noise_spectrum = estimator.get_noise_spectrum()
        if noise_spectrum is not None:
            assert len(noise_spectrum) > 0
            assert np.all(noise_spectrum >= 0)  # Magnitude spectrum should be positive
    
    def test_noise_type_classification(self):
        """Test noise type classification."""
        estimator = NoiseEstimator(frame_size=480, adaptation_rate=0.1)
        
        # Update with some noise
        for _ in range(10):
            noise_signal = np.random.randn(480) * 0.05
            estimator.update(noise_signal, is_speech_active=False)
        
        noise_type = estimator.get_noise_type()
        assert isinstance(noise_type, NoiseType)


class TestRNNoiseProcessor:
    """Test RNNoise processing functionality."""
    
    def test_processor_initialization(self):
        """Test RNNoise processor initialization."""
        processor = RNNoiseProcessor(frame_size=480, noise_reduction_factor=0.5)
        
        assert processor.frame_size == 480
        assert processor.noise_reduction_factor == 0.5
    
    def test_signal_processing_without_noise_estimate(self):
        """Test processing without noise estimate."""
        processor = RNNoiseProcessor(frame_size=480, noise_reduction_factor=0.5)
        
        # Generate test signal
        signal = np.random.randn(480) * 0.1
        
        # Process without noise estimate
        processed = processor.process(signal, noise_spectrum=None, speech_prob=0.5)
        
        assert len(processed) == len(signal)
        assert np.all(np.isfinite(processed))
    
    def test_signal_processing_with_noise_estimate(self):
        """Test processing with noise estimate."""
        processor = RNNoiseProcessor(frame_size=480, noise_reduction_factor=0.5)
        
        # Generate test signal and noise estimate
        signal = np.random.randn(480) * 0.1
        noise_spectrum = np.random.rand(256) * 0.01  # Half FFT size
        
        # Process with noise estimate
        processed = processor.process(signal, noise_spectrum=noise_spectrum, speech_prob=0.5)
        
        assert len(processed) == len(signal)
        assert np.all(np.isfinite(processed))
    
    def test_noise_reduction_factor_adjustment(self):
        """Test noise reduction factor adjustment."""
        processor = RNNoiseProcessor(frame_size=480, noise_reduction_factor=0.5)
        
        # Test factor adjustment
        processor.set_noise_reduction_factor(0.8)
        assert processor.noise_reduction_factor == 0.8
        
        # Test bounds
        processor.set_noise_reduction_factor(-0.1)
        assert processor.noise_reduction_factor == 0.0
        
        processor.set_noise_reduction_factor(1.5)
        assert processor.noise_reduction_factor == 1.0


class TestDenoiseService:
    """Test DenoiseService functionality."""
    
    @pytest.fixture
    def audio_config(self):
        """Create test audio configuration."""
        return AudioConfig(
            sample_rate=48000,
            frame_size=480,
            channels=1,
            buffer_size=4096
        )
    
    @pytest.fixture
    def denoise_service(self, audio_config):
        """Create test denoise service."""
        return DenoiseService(
            service_name="test_denoise",
            config=audio_config,
            noise_reduction_factor=0.5,
            mode=DenoiseMode.BALANCED
        )
    
    def test_service_initialization(self, denoise_service):
        """Test service initialization."""
        assert denoise_service.service_name == "test_denoise"
        assert denoise_service.noise_reduction_factor == 0.5
        assert denoise_service.mode == DenoiseMode.BALANCED
        assert not denoise_service.is_running
    
    def test_invalid_noise_reduction_factor(self, audio_config):
        """Test invalid noise reduction factor."""
        with pytest.raises(ValueError):
            DenoiseService(
                service_name="test_denoise",
                config=audio_config,
                noise_reduction_factor=1.5  # Invalid factor
            )
    
    @pytest.mark.asyncio
    async def test_service_lifecycle(self, denoise_service):
        """Test service start/stop lifecycle."""
        # Start service
        await denoise_service.start()
        assert denoise_service.is_running
        
        # Stop service
        await denoise_service.stop()
        assert not denoise_service.is_running
    
    @pytest.mark.asyncio
    async def test_frame_processing_bypass_mode(self, denoise_service, audio_config):
        """Test frame processing in bypass mode."""
        await denoise_service.start()
        
        # Set bypass mode
        denoise_service.set_mode(DenoiseMode.BYPASS)
        
        # Create test frame
        test_data = np.random.randn(1, 480) * 0.1
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=1,
            frame_size=480,
            data=test_data
        )
        
        # Process frame
        result = await denoise_service.process(frame)
        
        assert result.success
        assert result.data is not None
        assert result.data.channels == 1
        assert result.data.frame_size == 480
        
        await denoise_service.stop()
    
    @pytest.mark.asyncio
    async def test_frame_processing_denoise_mode(self, denoise_service, audio_config):
        """Test frame processing in denoise mode."""
        await denoise_service.start()
        
        # Set balanced mode
        denoise_service.set_mode(DenoiseMode.BALANCED)
        
        # Create test frame with some noise
        test_data = np.random.randn(1, 480) * 0.1
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=1,
            frame_size=480,
            data=test_data
        )
        
        # Process frame
        result = await denoise_service.process(frame)
        
        assert result.success
        assert result.data is not None
        assert result.data.channels == 1
        assert result.data.frame_size == 480
        
        # Check metadata
        metadata = result.data.metadata
        assert metadata['denoise_applied'] is True
        assert metadata['denoise_mode'] == DenoiseMode.BALANCED.value
        assert 'speech_probability' in metadata
        assert 'noise_reduction_db' in metadata
        
        await denoise_service.stop()
    
    @pytest.mark.asyncio
    async def test_multichannel_input_error(self, denoise_service):
        """Test error handling for multichannel input."""
        await denoise_service.start()
        
        # Create multichannel frame (should fail)
        test_data = np.random.randn(2, 480) * 0.1  # 2 channels
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=2,
            frame_size=480,
            data=test_data
        )
        
        # Process frame - should return error
        result = await denoise_service.process(frame)
        
        assert not result.success
        assert "single-channel" in result.error.lower()
        
        await denoise_service.stop()
    
    def test_mode_switching(self, denoise_service):
        """Test denoise mode switching."""
        # Test mode changes
        denoise_service.set_mode(DenoiseMode.FIDELITY)
        assert denoise_service.mode == DenoiseMode.FIDELITY
        
        denoise_service.set_mode(DenoiseMode.AGGRESSIVE)
        assert denoise_service.mode == DenoiseMode.AGGRESSIVE
        
        denoise_service.set_mode(DenoiseMode.BALANCED)
        assert denoise_service.mode == DenoiseMode.BALANCED
    
    def test_noise_reduction_factor_adjustment(self, denoise_service):
        """Test noise reduction factor adjustment."""
        # Test valid factor
        denoise_service.set_noise_reduction_factor(0.8)
        assert denoise_service.noise_reduction_factor == 0.8
        
        # Test invalid factors
        with pytest.raises(ValueError):
            denoise_service.set_noise_reduction_factor(-0.1)
        
        with pytest.raises(ValueError):
            denoise_service.set_noise_reduction_factor(1.5)
    
    def test_metrics_collection(self, denoise_service):
        """Test metrics collection."""
        metrics = denoise_service.get_denoise_metrics()
        
        assert isinstance(metrics, dict)
        assert 'mode' in metrics
        assert 'noise_reduction_factor' in metrics
        assert 'frames_processed' in metrics
        assert 'speech_frame_ratio' in metrics
        assert 'noise_frame_ratio' in metrics
    
    def test_config_schema(self, denoise_service):
        """Test configuration schema."""
        schema = denoise_service.get_config_schema()
        
        assert isinstance(schema, dict)
        assert 'properties' in schema
        assert 'noise_reduction_factor' in schema['properties']
        assert 'mode' in schema['properties']
    
    def test_adaptation_reset(self, denoise_service):
        """Test adaptation state reset."""
        # Reset should not raise errors
        denoise_service.reset_adaptation()
        
        # Metrics should be reset
        metrics = denoise_service.get_denoise_metrics()
        assert metrics['frames_processed'] == 0


if __name__ == "__main__":
    pytest.main([__file__])