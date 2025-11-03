"""
Tests for Beamformer Service.
"""

import pytest
import asyncio
import numpy as np
import math
from datetime import datetime

from src.audio_processing.models import AudioConfig, AudioFrame
from src.audio_processing.services.beamformer import (
    BeamformerService, BeamformingAlgorithm, BeamformingMode,
    BeamPattern, DelayAndSumBeamformer, MVDRBeamformer
)
from src.audio_processing.services.ssl import MicrophonePosition, create_linear_array


class TestBeamPattern:
    """Test beam pattern functionality."""
    
    def test_beam_pattern_creation(self):
        """Test beam pattern creation and normalization."""
        pattern = BeamPattern(
            target_azimuth=270.0,  # Will be normalized to -90.0
            target_elevation=100.0,  # Will be clamped to 90.0
            beam_width=30.0,
            sidelobe_level=-20.0
        )
        
        assert pattern.target_azimuth == -90.0  # Normalized
        assert pattern.target_elevation == 90.0  # Clamped
        assert pattern.beam_width == 30.0
        assert pattern.sidelobe_level == -20.0
    
    def test_angle_normalization(self):
        """Test angle normalization."""
        # Test azimuth normalization
        pattern1 = BeamPattern(
            target_azimuth=450.0, target_elevation=0.0,
            beam_width=30.0, sidelobe_level=-20.0
        )
        assert pattern1.target_azimuth == 90.0  # 450 - 360 = 90
        
        pattern2 = BeamPattern(
            target_azimuth=-270.0, target_elevation=0.0,
            beam_width=30.0, sidelobe_level=-20.0
        )
        assert pattern2.target_azimuth == 90.0  # -270 + 360 = 90


class TestDelayAndSumBeamformer:
    """Test Delay-and-Sum beamformer functionality."""
    
    def test_das_beamformer_initialization(self):
        """Test DAS beamformer initialization."""
        mic_positions = create_linear_array(4, spacing=0.05)
        
        beamformer = DelayAndSumBeamformer(
            microphone_positions=mic_positions,
            sample_rate=48000,
            frame_size=480
        )
        
        assert len(beamformer.microphone_positions) == 4
        assert beamformer.sample_rate == 48000
        assert beamformer.frame_size == 480
        assert beamformer.sound_speed == 343.0
        assert beamformer.reference_mic == 0
    
    def test_weight_computation(self):
        """Test beamforming weight computation."""
        mic_positions = create_linear_array(4, spacing=0.05)
        beamformer = DelayAndSumBeamformer(mic_positions, 48000, 480)
        
        # Compute weights for front direction
        weights = beamformer.compute_weights(target_azimuth=0.0, target_elevation=0.0)
        
        assert weights.algorithm == BeamformingAlgorithm.DAS
        assert weights.target_direction == (0.0, 0.0)
        assert weights.weights.shape[0] == 4  # Number of microphones
        assert weights.weights.shape[1] > 0   # Number of frequency bins
        
        # Check that weights are complex numbers
        assert np.iscomplexobj(weights.weights)
        
        # Check metadata
        assert 'delays_seconds' in weights.metadata
        assert 'reference_mic' in weights.metadata
        assert len(weights.metadata['delays_seconds']) == 4
    
    def test_beamforming_application(self):
        """Test applying beamforming to audio frame."""
        mic_positions = create_linear_array(4, spacing=0.05)
        beamformer = DelayAndSumBeamformer(mic_positions, 48000, 480)
        
        # Create test frame
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=4,
            frame_size=480,
            data=np.random.randn(4, 480).astype(np.float32) * 0.1
        )
        
        # Compute weights and apply beamforming
        weights = beamformer.compute_weights(0.0, 0.0)
        beamformed_frame = beamformer.apply_beamforming(frame, weights)
        
        # Check output frame
        assert beamformed_frame.channels == 1  # Should be single channel
        assert beamformed_frame.frame_size == 480
        assert beamformed_frame.sample_rate == 48000
        
        # Check metadata
        metadata = beamformed_frame.metadata
        assert metadata['beamforming_applied'] is True
        assert metadata['beamforming_algorithm'] == BeamformingAlgorithm.DAS.value
        assert metadata['target_azimuth'] == 0.0
        assert metadata['target_elevation'] == 0.0
    
    def test_channel_mismatch_error(self):
        """Test error handling for channel mismatch."""
        mic_positions = create_linear_array(4, spacing=0.05)
        beamformer = DelayAndSumBeamformer(mic_positions, 48000, 480)
        
        # Create frame with wrong number of channels
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=2,  # Wrong number of channels
            frame_size=480,
            data=np.random.randn(2, 480).astype(np.float32) * 0.1
        )
        
        weights = beamformer.compute_weights(0.0, 0.0)
        
        with pytest.raises(Exception):  # Should raise ProcessingError
            beamformer.apply_beamforming(frame, weights)


class TestMVDRBeamformer:
    """Test MVDR beamformer functionality."""
    
    def test_mvdr_beamformer_initialization(self):
        """Test MVDR beamformer initialization."""
        mic_positions = create_linear_array(4, spacing=0.05)
        
        beamformer = MVDRBeamformer(
            microphone_positions=mic_positions,
            sample_rate=48000,
            frame_size=480,
            adaptation_rate=0.01
        )
        
        assert len(beamformer.microphone_positions) == 4
        assert beamformer.sample_rate == 48000
        assert beamformer.frame_size == 480
        assert beamformer.adaptation_rate == 0.01
        assert beamformer.covariance_matrices is None
        assert beamformer.adaptation_count == 0
    
    def test_covariance_update(self):
        """Test covariance matrix update."""
        mic_positions = create_linear_array(4, spacing=0.05)
        beamformer = MVDRBeamformer(mic_positions, 48000, 480)
        
        # Create test frame
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=4,
            frame_size=480,
            data=np.random.randn(4, 480).astype(np.float32) * 0.1
        )
        
        # Update covariance
        beamformer.update_covariance(frame)
        
        # Check that covariance matrices were initialized
        assert beamformer.covariance_matrices is not None
        assert beamformer.adaptation_count == 1
        
        # Check matrix dimensions
        num_freq_bins = len(beamformer.frequency_bins)
        assert beamformer.covariance_matrices.shape == (num_freq_bins, 4, 4)
    
    def test_mvdr_weight_computation(self):
        """Test MVDR weight computation."""
        mic_positions = create_linear_array(4, spacing=0.05)
        beamformer = MVDRBeamformer(mic_positions, 48000, 480)
        
        # Initialize covariance with some frames
        for _ in range(5):
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=4,
                frame_size=480,
                data=np.random.randn(4, 480).astype(np.float32) * 0.1
            )
            beamformer.update_covariance(frame)
        
        # Compute MVDR weights
        weights = beamformer.compute_weights(target_azimuth=0.0, target_elevation=0.0)
        
        assert weights.algorithm == BeamformingAlgorithm.MVDR
        assert weights.target_direction == (0.0, 0.0)
        assert weights.weights.shape[0] == 4  # Number of microphones
        
        # Check metadata
        assert 'adaptation_count' in weights.metadata
        assert 'regularization' in weights.metadata
        assert weights.metadata['adaptation_count'] == 5
    
    def test_mvdr_beamforming_application(self):
        """Test MVDR beamforming application."""
        mic_positions = create_linear_array(4, spacing=0.05)
        beamformer = MVDRBeamformer(mic_positions, 48000, 480)
        
        # Initialize with some frames
        for _ in range(3):
            init_frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=4,
                frame_size=480,
                data=np.random.randn(4, 480).astype(np.float32) * 0.1
            )
            beamformer.update_covariance(init_frame)
        
        # Create test frame
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=4,
            frame_size=480,
            data=np.random.randn(4, 480).astype(np.float32) * 0.1
        )
        
        # Compute weights and apply beamforming
        weights = beamformer.compute_weights(0.0, 0.0)
        beamformed_frame = beamformer.apply_beamforming(frame, weights)
        
        # Check output
        assert beamformed_frame.channels == 1
        assert beamformed_frame.frame_size == 480
        
        # Check MVDR-specific metadata
        metadata = beamformed_frame.metadata
        assert metadata['beamforming_algorithm'] == BeamformingAlgorithm.MVDR.value
        assert 'mvdr_adaptation_count' in metadata
    
    def test_adaptation_reset(self):
        """Test MVDR adaptation reset."""
        mic_positions = create_linear_array(4, spacing=0.05)
        beamformer = MVDRBeamformer(mic_positions, 48000, 480)
        
        # Build up some adaptation state
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=4,
            frame_size=480,
            data=np.random.randn(4, 480).astype(np.float32) * 0.1
        )
        beamformer.update_covariance(frame)
        
        assert beamformer.adaptation_count > 0
        assert beamformer.covariance_matrices is not None
        
        # Reset adaptation
        beamformer.reset_adaptation()
        
        assert beamformer.adaptation_count == 0
        assert beamformer.covariance_matrices is Nonecl
ass TestBeamformerService:
    """Test beamformer service functionality."""
    
    async def test_beamformer_service_initialization(self):
        """Test beamformer service initialization."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        beamformer_service = BeamformerService("TestBeamformer", config, mic_array)
        
        assert beamformer_service.service_name == "TestBeamformer"
        assert len(beamformer_service.microphone_positions) == 4
        assert beamformer_service.algorithm == BeamformingAlgorithm.DAS
        assert beamformer_service.mode == BeamformingMode.ADAPTIVE
        assert not beamformer_service.is_running
    
    async def test_beamformer_service_lifecycle(self):
        """Test beamformer service start/stop lifecycle."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        beamformer_service = BeamformerService("TestBeamformer", config, mic_array)
        
        # Start service
        await beamformer_service.start()
        assert beamformer_service.is_running
        
        # Stop service
        await beamformer_service.stop()
        assert not beamformer_service.is_running
    
    async def test_das_frame_processing(self):
        """Test DAS beamforming frame processing."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        beamformer_service = BeamformerService(
            "TestBeamformer", config, mic_array,
            algorithm=BeamformingAlgorithm.DAS
        )
        
        await beamformer_service.start()
        
        try:
            # Create test frame with SSL direction
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=4,
                frame_size=480,
                data=np.random.randn(4, 480).astype(np.float32) * 0.1,
                metadata={
                    'ssl_azimuth': 0.0,
                    'ssl_elevation': 0.0,
                    'ssl_confidence': 0.8
                }
            )
            
            # Process frame
            result = await beamformer_service.process(frame)
            
            assert result.success
            assert result.data is not None
            assert result.data.channels == 1  # Beamformed to single channel
            
            # Check beamforming metadata
            metadata = result.data.metadata
            assert metadata['beamforming_applied'] is True
            assert metadata['beamforming_algorithm'] == BeamformingAlgorithm.DAS.value
            assert 'target_azimuth' in metadata
            assert 'target_elevation' in metadata
        
        finally:
            await beamformer_service.stop()
    
    async def test_mvdr_frame_processing(self):
        """Test MVDR beamforming frame processing."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        beamformer_service = BeamformerService(
            "TestBeamformer", config, mic_array,
            algorithm=BeamformingAlgorithm.MVDR
        )
        
        await beamformer_service.start()
        
        try:
            # Process several frames to build up MVDR adaptation
            for i in range(5):
                frame = AudioFrame(
                    timestamp=datetime.now(),
                    sample_rate=48000,
                    channels=4,
                    frame_size=480,
                    data=np.random.randn(4, 480).astype(np.float32) * 0.1,
                    metadata={
                        'ssl_azimuth': 0.0,
                        'ssl_elevation': 0.0,
                        'ssl_confidence': 0.8
                    }
                )
                
                result = await beamformer_service.process(frame)
                assert result.success
                assert result.data.channels == 1
                
                # Check MVDR-specific metadata
                if i >= 2:  # After some adaptation
                    metadata = result.data.metadata
                    assert metadata['beamforming_algorithm'] == BeamformingAlgorithm.MVDR.value
                    assert 'mvdr_adaptation_count' in metadata
        
        finally:
            await beamformer_service.stop()
    
    async def test_fixed_mode_beamforming(self):
        """Test fixed mode beamforming."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        beamformer_service = BeamformerService(
            "TestBeamformer", config, mic_array,
            mode=BeamformingMode.FIXED
        )
        
        # Set fixed beam direction
        beamformer_service.set_beam_direction(azimuth=45.0, elevation=0.0)
        
        await beamformer_service.start()
        
        try:
            # Create frame without SSL metadata
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=4,
                frame_size=480,
                data=np.random.randn(4, 480).astype(np.float32) * 0.1
            )
            
            result = await beamformer_service.process(frame)
            
            assert result.success
            assert result.data.channels == 1
            
            # Should use fixed direction
            metadata = result.data.metadata
            assert metadata['target_azimuth'] == 45.0
            assert metadata['target_elevation'] == 0.0
        
        finally:
            await beamformer_service.stop()
    
    async def test_beamformer_metrics(self):
        """Test beamformer metrics collection."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        beamformer_service = BeamformerService("TestBeamformer", config, mic_array)
        
        await beamformer_service.start()
        
        try:
            # Process a frame to generate metrics
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=4,
                frame_size=480,
                data=np.random.randn(4, 480).astype(np.float32) * 0.1,
                metadata={'ssl_azimuth': 0.0, 'ssl_elevation': 0.0, 'ssl_confidence': 0.8}
            )
            
            await beamformer_service.process(frame)
            
            # Get beamformer metrics
            metrics = beamformer_service.get_beamformer_metrics()
            
            assert 'algorithm' in metrics
            assert 'mode' in metrics
            assert 'frames_processed' in metrics
            assert 'microphone_count' in metrics
            assert 'current_azimuth' in metrics
            assert 'current_elevation' in metrics
            
            assert metrics['algorithm'] == BeamformingAlgorithm.DAS.value
            assert metrics['mode'] == BeamformingMode.ADAPTIVE.value
            assert metrics['frames_processed'] >= 1
            assert metrics['microphone_count'] == 4
        
        finally:
            await beamformer_service.stop()
    
    async def test_algorithm_switching(self):
        """Test switching beamforming algorithms."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        beamformer_service = BeamformerService("TestBeamformer", config, mic_array)
        
        # Test algorithm switching
        beamformer_service.set_algorithm(BeamformingAlgorithm.MVDR)
        assert beamformer_service.algorithm == BeamformingAlgorithm.MVDR
        
        beamformer_service.set_algorithm(BeamformingAlgorithm.DAS)
        assert beamformer_service.algorithm == BeamformingAlgorithm.DAS
    
    async def test_mode_switching(self):
        """Test switching beamforming modes."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        beamformer_service = BeamformerService("TestBeamformer", config, mic_array)
        
        # Test mode switching
        beamformer_service.set_mode(BeamformingMode.FIXED)
        assert beamformer_service.mode == BeamformingMode.FIXED
        
        beamformer_service.set_mode(BeamformingMode.TRACKING)
        assert beamformer_service.mode == BeamformingMode.TRACKING
        
        beamformer_service.set_mode(BeamformingMode.ADAPTIVE)
        assert beamformer_service.mode == BeamformingMode.ADAPTIVE
    
    async def test_beam_direction_setting(self):
        """Test setting beam direction."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        beamformer_service = BeamformerService("TestBeamformer", config, mic_array)
        
        # Set beam direction
        beamformer_service.set_beam_direction(azimuth=30.0, elevation=15.0)
        
        # Get current direction
        current_az, current_el = beamformer_service.get_beam_direction()
        assert current_az == 30.0
        assert current_el == 15.0
    
    async def test_invalid_input_handling(self):
        """Test handling of invalid inputs."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        beamformer_service = BeamformerService("TestBeamformer", config, mic_array)
        
        await beamformer_service.start()
        
        try:
            # Test wrong number of channels
            wrong_channels_frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=2,  # Wrong number of channels
                frame_size=480,
                data=np.random.randn(2, 480).astype(np.float32) * 0.1
            )
            
            result = await beamformer_service.process(wrong_channels_frame)
            assert not result.success
            assert "channels" in result.error.lower()
        
        finally:
            await beamformer_service.stop()
    
    async def test_microphone_validation(self):
        """Test microphone configuration validation."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        
        # Test insufficient microphones
        single_mic = [MicrophonePosition(0.0, 0.0, 0.0, 0)]
        
        beamformer_service = BeamformerService("TestBeamformer", config, single_mic)
        
        with pytest.raises(Exception):  # Should raise ServiceError
            await beamformer_service.start()
        
        # Test microphone count mismatch
        wrong_count_mics = create_linear_array(2)  # 2 mics for 4 channels
        
        beamformer_service2 = BeamformerService("TestBeamformer2", config, wrong_count_mics)
        
        with pytest.raises(Exception):  # Should raise ServiceError
            await beamformer_service2.start()


# Integration test
class TestBeamformerIntegration:
    """Integration tests for beamformer service."""
    
    async def test_beamformer_classroom_scenario(self):
        """Test beamformer service in classroom scenario."""
        # Setup classroom configuration
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=8)
        mic_array = create_linear_array(8, spacing=0.04)  # Classroom array
        
        beamformer_service = BeamformerService(
            "ClassroomBeamformer", 
            config, 
            mic_array,
            algorithm=BeamformingAlgorithm.DAS,
            mode=BeamformingMode.ADAPTIVE
        )
        
        await beamformer_service.start()
        
        try:
            # Simulate teacher speaking from front
            teacher_directions = []
            for i in range(5):
                frame = AudioFrame(
                    timestamp=datetime.now(),
                    sample_rate=48000,
                    channels=8,
                    frame_size=480,
                    data=np.random.randn(8, 480).astype(np.float32) * 0.1,
                    metadata={
                        'ssl_azimuth': 0.0 + np.random.randn() * 5.0,  # Small variations
                        'ssl_elevation': 0.0,
                        'ssl_confidence': 0.9
                    }
                )
                
                result = await beamformer_service.process(frame)
                assert result.success
                assert result.data.channels == 1
                
                teacher_directions.append(result.data.metadata['target_azimuth'])
            
            # Simulate student question from side
            student_directions = []
            for i in range(5):
                frame = AudioFrame(
                    timestamp=datetime.now(),
                    sample_rate=48000,
                    channels=8,
                    frame_size=480,
                    data=np.random.randn(8, 480).astype(np.float32) * 0.1,
                    metadata={
                        'ssl_azimuth': 90.0 + np.random.randn() * 10.0,  # Side direction
                        'ssl_elevation': 0.0,
                        'ssl_confidence': 0.7
                    }
                )
                
                result = await beamformer_service.process(frame)
                assert result.success
                
                student_directions.append(result.data.metadata['target_azimuth'])
            
            # Check that beamformer adapted to different directions
            metrics = beamformer_service.get_beamformer_metrics()
            assert metrics['frames_processed'] == 10
            
            # Teacher directions should be around 0 degrees
            teacher_avg = np.mean(teacher_directions)
            assert abs(teacher_avg) < 15.0  # Should be close to front
            
            # Student directions should be around 90 degrees
            student_avg = np.mean(student_directions)
            assert abs(student_avg - 90.0) < 20.0  # Should be close to side
            
        finally:
            await beamformer_service.stop()