"""
Tests for AEC (Acoustic Echo Cancellation) Service.
"""

import pytest
import asyncio
import numpy as np
from datetime import datetime

from audio_processing.models import AudioConfig, AudioFrame
from audio_processing.services.aec import (
    AECService, AECMode, DoubleTalkState, NLMSFilter,
    DoubleTalkDetector, ResidualEchoSuppressor, ComfortNoiseGenerator
)


class TestNLMSFilter:
    """Test NLMS filter functionality."""
    
    def test_nlms_filter_initialization(self):
        """Test NLMS filter initialization."""
        filter_obj = NLMSFilter(filter_length=256, step_size=0.5)
        
        assert filter_obj.filter_length == 256
        assert filter_obj.step_size == 0.5
        assert len(filter_obj.weights) == 256
        assert len(filter_obj.input_buffer) == 256
        assert filter_obj.adaptation_enabled is True
    
    def test_filter_operation(self):
        """Test basic filter operation."""
        filter_obj = NLMSFilter(filter_length=64, step_size=0.1)
        
        # Test filtering
        output = filter_obj.filter(0.5)
        assert isinstance(output, float)
        
        # Test adaptation
        filter_obj.adapt(0.1, 0.5)
        
        # Weights should have changed
        assert not np.allclose(filter_obj.weights, 0.0)
    
    def test_filter_reset(self):
        """Test filter reset functionality."""
        filter_obj = NLMSFilter(filter_length=64, step_size=0.1)
        
        # Add some data
        filter_obj.filter(0.5)
        filter_obj.adapt(0.1, 0.5)
        
        # Reset
        filter_obj.reset_filter()
        
        # Should be back to initial state
        assert np.allclose(filter_obj.weights, 0.0)
        assert np.allclose(filter_obj.input_buffer, 0.0)


class TestDoubleTalkDetector:
    """Test double-talk detector functionality."""
    
    def test_detector_initialization(self):
        """Test detector initialization."""
        detector = DoubleTalkDetector(frame_size=480, sensitivity=0.5)
        
        assert detector.frame_size == 480
        assert detector.sensitivity == 0.5
        assert detector.current_state == DoubleTalkState.SILENCE
    
    def test_silence_detection(self):
        """Test silence detection."""
        detector = DoubleTalkDetector()
        
        # Silent signals
        near_signal = np.zeros(480) + np.random.randn(480) * 1e-6
        far_signal = np.zeros(480) + np.random.randn(480) * 1e-6
        
        state = detector.detect(near_signal, far_signal)
        assert state == DoubleTalkState.SILENCE
    
    def test_single_talk_detection(self):
        """Test single-talk detection."""
        detector = DoubleTalkDetector()
        
        # Far-end active, near-end silent
        near_signal = np.random.randn(480) * 0.001  # Very quiet
        far_signal = np.random.randn(480) * 0.1     # Active
        
        state = detector.detect(near_signal, far_signal)
        # Should detect far-end activity
        assert state in [DoubleTalkState.SINGLE_TALK_FAR, DoubleTalkState.SILENCE]
    
    def test_detector_reset(self):
        """Test detector reset."""
        detector = DoubleTalkDetector()
        
        # Add some history
        detector.detect(np.random.randn(480), np.random.randn(480))
        
        # Reset
        detector.reset()
        
        assert detector.current_state == DoubleTalkState.SILENCE
        assert len(detector.near_energy_history) == 0


class TestResidualEchoSuppressor:
    """Test residual echo suppressor functionality."""
    
    def test_suppressor_initialization(self):
        """Test suppressor initialization."""
        suppressor = ResidualEchoSuppressor(frame_size=480)
        
        assert suppressor.frame_size == 480
        assert suppressor.fft_size >= 480
    
    def test_echo_suppression(self):
        """Test basic echo suppression."""
        suppressor = ResidualEchoSuppressor(frame_size=480)
        
        # Create test signals
        microphone = np.random.randn(480) * 0.1
        echo_estimate = np.random.randn(480) * 0.05
        far_end = np.random.randn(480) * 0.1
        
        # Suppress echo
        suppressed = suppressor.suppress(microphone, echo_estimate, far_end)
        
        assert len(suppressed) == 480
        assert isinstance(suppressed, np.ndarray)
    
    def test_suppressor_reset(self):
        """Test suppressor reset."""
        suppressor = ResidualEchoSuppressor(frame_size=480)
        
        # Process some data
        microphone = np.random.randn(480) * 0.1
        echo_estimate = np.random.randn(480) * 0.05
        far_end = np.random.randn(480) * 0.1
        suppressor.suppress(microphone, echo_estimate, far_end)
        
        # Reset
        suppressor.reset()
        
        assert suppressor.echo_spectrum_estimate is None


class TestComfortNoiseGenerator:
    """Test comfort noise generator functionality."""
    
    def test_generator_initialization(self):
        """Test generator initialization."""
        generator = ComfortNoiseGenerator(noise_level_db=-60.0)
        
        assert generator.noise_level_db == -60.0
    
    def test_noise_generation(self):
        """Test noise generation."""
        generator = ComfortNoiseGenerator(noise_level_db=-40.0)
        
        noise = generator.generate(480)
        
        assert len(noise) == 480
        assert isinstance(noise, np.ndarray)
        
        # Check noise level is reasonable (allow wider range due to filter shaping)
        noise_level = 20 * np.log10(np.sqrt(np.mean(noise ** 2)))
        assert -70 < noise_level < -20  # Should be around -40 dB with some tolerance
    
    def test_adaptive_noise_level(self):
        """Test adaptive noise level."""
        generator = ComfortNoiseGenerator(noise_level_db=-60.0)
        
        # Generate with reference level
        noise_with_ref = generator.generate(480, reference_level=0.1)
        noise_without_ref = generator.generate(480)
        
        # With reference should be different
        assert not np.allclose(noise_with_ref, noise_without_ref)


class TestAECService:
    """Test AEC service functionality."""
    
    async def test_aec_service_initialization(self):
        """Test AEC service initialization."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        
        aec_service = AECService("TestAEC", config, filter_length=256)
        
        assert aec_service.service_name == "TestAEC"
        assert aec_service.filter_length == 256
        assert aec_service.mode == AECMode.FULL_DUPLEX
        assert not aec_service.is_running
    
    async def test_aec_service_lifecycle(self):
        """Test AEC service start/stop lifecycle."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        aec_service = AECService("TestAEC", config)
        
        # Start service
        await aec_service.start()
        assert aec_service.is_running
        
        # Stop service
        await aec_service.stop()
        assert not aec_service.is_running
    
    async def test_aec_frame_processing(self):
        """Test AEC frame processing."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        aec_service = AECService("TestAEC", config)
        
        # Enable test reference signal
        aec_service._enable_test_reference(True)
        
        await aec_service.start()
        
        try:
            # Create test frame
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=1,
                frame_size=480,
                data=np.random.randn(1, 480).astype(np.float32) * 0.1
            )
            
            # Process frame
            result = await aec_service.process(frame)
            
            assert result.success
            assert result.data is not None
            assert result.data.channels == 1
            
            # Check AEC metadata was added
            metadata = result.data.metadata
            assert 'aec_applied' in metadata
            assert 'aec_mode' in metadata
            assert 'double_talk_state' in metadata
            
            # Validate metadata values
            assert metadata['aec_applied'] is True
            assert metadata['aec_mode'] == AECMode.FULL_DUPLEX.value
            assert metadata['double_talk_state'] in [state.value for state in DoubleTalkState]
        
        finally:
            await aec_service.stop()
    
    async def test_aec_metrics(self):
        """Test AEC metrics collection."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        aec_service = AECService("TestAEC", config)
        
        aec_service._enable_test_reference(True)
        await aec_service.start()
        
        try:
            # Process a frame to generate metrics
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=1,
                frame_size=480,
                data=np.random.randn(1, 480).astype(np.float32) * 0.1
            )
            
            await aec_service.process(frame)
            
            # Get AEC metrics
            metrics = aec_service.get_aec_metrics()
            
            assert 'erle_db' in metrics
            assert 'filter_length' in metrics
            assert 'adaptation_enabled' in metrics
            assert 'mode' in metrics
            assert 'total_frames_processed' in metrics
            
            assert metrics['filter_length'] == aec_service.filter_length
            assert metrics['mode'] == AECMode.FULL_DUPLEX.value
            assert metrics['total_frames_processed'] >= 1
        
        finally:
            await aec_service.stop()
    
    async def test_filter_length_configuration(self):
        """Test filter length configuration."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        aec_service = AECService("TestAEC", config, filter_length=128)
        
        # Test valid filter lengths
        aec_service.set_filter_length(256)
        assert aec_service.filter_length == 256
        
        aec_service.set_filter_length(512)
        assert aec_service.filter_length == 512
        
        # Test invalid filter lengths
        with pytest.raises(ValueError):
            aec_service.set_filter_length(64)  # Too small
        
        with pytest.raises(ValueError):
            aec_service.set_filter_length(1024)  # Too large
    
    async def test_mode_switching(self):
        """Test AEC mode switching."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        aec_service = AECService("TestAEC", config)
        
        # Test mode switching
        aec_service.set_mode(AECMode.CALIBRATION)
        assert aec_service.mode == AECMode.CALIBRATION
        assert aec_service.calibration_active is True
        
        aec_service.set_mode(AECMode.BYPASS)
        assert aec_service.mode == AECMode.BYPASS
        assert aec_service.calibration_active is False
        
        aec_service.set_mode(AECMode.FULL_DUPLEX)
        assert aec_service.mode == AECMode.FULL_DUPLEX
    
    async def test_adaptation_control(self):
        """Test adaptation enable/disable."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        aec_service = AECService("TestAEC", config)
        
        # Test adaptation control
        aec_service.enable_adaptation(False)
        assert aec_service.adaptation_enabled is False
        
        aec_service.enable_adaptation(True)
        assert aec_service.adaptation_enabled is True
    
    async def test_calibration_mode(self):
        """Test calibration mode functionality."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        aec_service = AECService("TestAEC", config)
        
        aec_service._enable_test_reference(True)
        await aec_service.start()
        
        try:
            # Start calibration
            aec_service.start_calibration()
            assert aec_service.mode == AECMode.CALIBRATION
            
            # Process frame in calibration mode
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=1,
                frame_size=480,
                data=np.random.randn(1, 480).astype(np.float32) * 0.1
            )
            
            result = await aec_service.process(frame)
            
            # Should have calibration metadata
            assert 'aec_calibration_active' in result.data.metadata
            assert result.data.metadata['aec_calibration_active'] is True
            
            # Stop calibration
            aec_service.stop_calibration()
            assert aec_service.mode == AECMode.FULL_DUPLEX
        
        finally:
            await aec_service.stop()
    
    async def test_reference_signal_handling(self):
        """Test reference signal handling."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        aec_service = AECService("TestAEC", config)
        
        # Set reference signal
        reference_samples = np.random.randn(480) * 0.1
        aec_service.set_reference_signal(reference_samples)
        
        # Should be in buffer
        assert len(aec_service.reference_buffer) == 480
        
        await aec_service.start()
        
        try:
            # Process frame with reference in buffer
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=1,
                frame_size=480,
                data=np.random.randn(1, 480).astype(np.float32) * 0.1
            )
            
            result = await aec_service.process(frame)
            assert result.success
            
            # Test frame with reference in metadata
            frame_with_ref = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=1,
                frame_size=480,
                data=np.random.randn(1, 480).astype(np.float32) * 0.1,
                metadata={'reference_signal': reference_samples.tolist()}
            )
            
            result_with_ref = await aec_service.process(frame_with_ref)
            assert result_with_ref.success
        
        finally:
            await aec_service.stop()
    
    async def test_reset_adaptation(self):
        """Test adaptation reset functionality."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        aec_service = AECService("TestAEC", config)
        
        aec_service._enable_test_reference(True)
        await aec_service.start()
        
        try:
            # Process some frames to build up state
            for _ in range(5):
                frame = AudioFrame(
                    timestamp=datetime.now(),
                    sample_rate=48000,
                    channels=1,
                    frame_size=480,
                    data=np.random.randn(1, 480).astype(np.float32) * 0.1
                )
                await aec_service.process(frame)
            
            # Should have some metrics
            metrics_before = aec_service.get_aec_metrics()
            assert metrics_before['total_frames_processed'] > 0
            
            # Reset adaptation
            aec_service.reset_adaptation()
            
            # Metrics should be reset
            metrics_after = aec_service.get_aec_metrics()
            assert metrics_after['total_frames_processed'] == 0
            assert metrics_after['erle_db'] == 0.0
        
        finally:
            await aec_service.stop()
    
    async def test_invalid_input_handling(self):
        """Test handling of invalid inputs."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        aec_service = AECService("TestAEC", config)
        
        await aec_service.start()
        
        try:
            # Test multi-channel input (should fail)
            multi_channel_frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=2,  # Invalid for AEC
                frame_size=480,
                data=np.random.randn(2, 480).astype(np.float32) * 0.1
            )
            
            result = await aec_service.process(multi_channel_frame)
            assert not result.success
            assert "single-channel" in result.error
        
        finally:
            await aec_service.stop()


# Integration test
class TestAECIntegration:
    """Integration tests for AEC service."""
    
    async def test_aec_classroom_scenario(self):
        """Test AEC service in classroom scenario."""
        # Setup classroom AEC configuration
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        
        aec_service = AECService(
            "ClassroomAEC", 
            config, 
            filter_length=256,  # Suitable for classroom
            step_size=0.3       # Conservative adaptation
        )
        
        aec_service._enable_test_reference(True)
        await aec_service.start()
        
        try:
            # Simulate classroom audio processing
            erle_values = []
            
            for i in range(10):
                # Simulate microphone input with some echo
                microphone_signal = np.random.randn(480) * 0.1
                
                frame = AudioFrame(
                    timestamp=datetime.now(),
                    sample_rate=48000,
                    channels=1,
                    frame_size=480,
                    data=microphone_signal.reshape(1, -1).astype(np.float32)
                )
                
                result = await aec_service.process(frame)
                assert result.success
                
                # Collect ERLE values
                if 'erle_db' in result.data.metadata:
                    erle_values.append(result.data.metadata['erle_db'])
            
            # Check that AEC is working
            metrics = aec_service.get_aec_metrics()
            assert metrics['total_frames_processed'] == 10
            assert metrics['filter_length'] == 256
            
            # Should have processed multiple frames
            assert len(erle_values) >= 5  # At least some ERLE measurements
        
        finally:
            await aec_service.stop()
