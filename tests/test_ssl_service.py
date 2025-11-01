"""
Tests for SSL (Sound Source Localization) Service.
"""

import pytest
import asyncio
import numpy as np
import math
from datetime import datetime

from audio_processing.models import AudioConfig, AudioFrame
from audio_processing.services.ssl import (
    SSLService, MicrophonePosition, DirectionEstimate, ClassroomArea,
    ClassroomGeometry, SRPPHATProcessor, DirectionTracker,
    create_linear_array, create_circular_array, create_classroom_array
)


class TestMicrophonePosition:
    """Test microphone position functionality."""
    
    def test_microphone_position_creation(self):
        """Test microphone position creation."""
        mic = MicrophonePosition(x=0.1, y=0.2, z=0.3, channel=0)
        
        assert mic.x == 0.1
        assert mic.y == 0.2
        assert mic.z == 0.3
        assert mic.channel == 0
    
    def test_distance_calculation(self):
        """Test distance calculation between microphones."""
        mic1 = MicrophonePosition(x=0.0, y=0.0, z=0.0, channel=0)
        mic2 = MicrophonePosition(x=0.3, y=0.4, z=0.0, channel=1)
        
        distance = mic1.distance_to(mic2)
        expected_distance = 0.5  # 3-4-5 triangle
        
        assert abs(distance - expected_distance) < 0.001


class TestDirectionEstimate:
    """Test direction estimate functionality."""
    
    def test_direction_estimate_creation(self):
        """Test direction estimate creation and normalization."""
        estimate = DirectionEstimate(
            azimuth=270.0,  # Will be normalized to -90.0
            elevation=100.0,  # Will be clamped to 90.0
            confidence=1.5,  # Will be clamped to 1.0
            timestamp=datetime.now(),
            area=ClassroomArea.TEACHER_AREA
        )
        
        assert estimate.azimuth == -90.0  # Normalized
        assert estimate.elevation == 90.0  # Clamped
        assert estimate.confidence == 1.0  # Clamped
        assert estimate.area == ClassroomArea.TEACHER_AREA
    
    def test_angle_normalization(self):
        """Test angle normalization."""
        # Test azimuth normalization
        estimate1 = DirectionEstimate(
            azimuth=450.0, elevation=0.0, confidence=1.0,
            timestamp=datetime.now(), area=ClassroomArea.UNKNOWN
        )
        assert estimate1.azimuth == 90.0  # 450 - 360 = 90
        
        estimate2 = DirectionEstimate(
            azimuth=-270.0, elevation=0.0, confidence=1.0,
            timestamp=datetime.now(), area=ClassroomArea.UNKNOWN
        )
        assert estimate2.azimuth == 90.0  # -270 + 360 = 90


class TestClassroomGeometry:
    """Test classroom geometry functionality."""
    
    def test_area_classification(self):
        """Test classroom area classification."""
        geometry = ClassroomGeometry(
            length=12.0, width=8.0, height=3.0,
            teacher_area_bounds=(0.0, 4.0, 0.0, 8.0),
            microphone_array_position=(6.0, 4.0, 2.5)
        )
        
        # Test teacher area (front)
        teacher_area = geometry.classify_direction(azimuth=0.0, elevation=0.0)
        assert teacher_area == ClassroomArea.TEACHER_AREA
        
        # Test student area (side)
        student_area = geometry.classify_direction(azimuth=90.0, elevation=0.0)
        assert student_area == ClassroomArea.STUDENT_AREA
        
        # Test ambient (high elevation) - but front direction still classifies as teacher
        # The current logic prioritizes azimuth over elevation
        front_high_area = geometry.classify_direction(azimuth=0.0, elevation=45.0)
        assert front_high_area == ClassroomArea.TEACHER_AREA  # Front direction takes priority
        
        # Test true ambient (back + high elevation)
        ambient_area = geometry.classify_direction(azimuth=180.0, elevation=45.0)
        assert ambient_area == ClassroomArea.AMBIENT


class TestMicrophoneArrays:
    """Test microphone array creation functions."""
    
    def test_linear_array_creation(self):
        """Test linear array creation."""
        array = create_linear_array(num_mics=4, spacing=0.05)
        
        assert len(array) == 4
        
        # Check positions are linear and centered (with floating point tolerance)
        assert abs(array[0].x - (-0.075)) < 1e-10  # -(4-1)*0.05/2
        assert abs(array[1].x - (-0.025)) < 1e-10
        assert abs(array[2].x - 0.025) < 1e-10
        assert abs(array[3].x - 0.075) < 1e-10
        
        # Check all y and z are zero
        for mic in array:
            assert mic.y == 0.0
            assert mic.z == 0.0
    
    def test_circular_array_creation(self):
        """Test circular array creation."""
        array = create_circular_array(num_mics=4, radius=0.1)
        
        assert len(array) == 4
        
        # Check positions form a circle
        for i, mic in enumerate(array):
            expected_angle = 2 * math.pi * i / 4
            expected_x = 0.1 * math.cos(expected_angle)
            expected_y = 0.1 * math.sin(expected_angle)
            
            assert abs(mic.x - expected_x) < 0.001
            assert abs(mic.y - expected_y) < 0.001
            assert mic.z == 0.0
    
    def test_classroom_array_creation(self):
        """Test classroom array creation."""
        array = create_classroom_array()
        
        assert len(array) == 8  # 4 inner + 4 outer
        
        # Check channel assignments
        channels = [mic.channel for mic in array]
        assert channels == list(range(8))


class TestDirectionTracker:
    """Test direction tracking functionality."""
    
    def test_direction_tracker_initialization(self):
        """Test direction tracker initialization."""
        tracker = DirectionTracker(
            smoothing_factor=0.8,
            confidence_threshold=0.4,
            max_history=30
        )
        
        assert tracker.smoothing_factor == 0.8
        assert tracker.confidence_threshold == 0.4
        assert tracker.max_history == 30
        assert tracker.current_direction is None
    
    def test_direction_smoothing(self):
        """Test direction smoothing."""
        tracker = DirectionTracker(smoothing_factor=0.5, confidence_threshold=0.1)
        
        # First estimate
        estimate1 = DirectionEstimate(
            azimuth=0.0, elevation=0.0, confidence=0.8,
            timestamp=datetime.now(), area=ClassroomArea.TEACHER_AREA
        )
        
        result1 = tracker.update(estimate1)
        assert result1.azimuth == 0.0  # First estimate, no smoothing
        
        # Second estimate
        estimate2 = DirectionEstimate(
            azimuth=20.0, elevation=0.0, confidence=0.8,
            timestamp=datetime.now(), area=ClassroomArea.TEACHER_AREA
        )
        
        result2 = tracker.update(estimate2)
        # Should be smoothed: 0.5 * 0.0 + 0.5 * 20.0 = 10.0
        assert abs(result2.azimuth - 10.0) < 0.1
    
    def test_low_confidence_filtering(self):
        """Test low confidence estimate filtering."""
        tracker = DirectionTracker(confidence_threshold=0.5)
        
        # High confidence estimate
        high_conf = DirectionEstimate(
            azimuth=0.0, elevation=0.0, confidence=0.8,
            timestamp=datetime.now(), area=ClassroomArea.TEACHER_AREA
        )
        
        result1 = tracker.update(high_conf)
        assert result1.confidence == 0.8
        
        # Low confidence estimate
        low_conf = DirectionEstimate(
            azimuth=90.0, elevation=0.0, confidence=0.3,
            timestamp=datetime.now(), area=ClassroomArea.STUDENT_AREA
        )
        
        result2 = tracker.update(low_conf)
        # Should return previous direction with decayed confidence
        assert result2.azimuth == 0.0  # Previous direction
        assert result2.confidence < 0.8  # Decayed


class TestSRPPHATProcessor:
    """Test SRP-PHAT processor functionality."""
    
    def test_srp_processor_initialization(self):
        """Test SRP-PHAT processor initialization."""
        mic_positions = create_linear_array(4, spacing=0.05)
        
        processor = SRPPHATProcessor(
            microphone_positions=mic_positions,
            sample_rate=48000,
            frame_size=480,
            search_resolution=10.0
        )
        
        assert len(processor.microphone_positions) == 4
        assert processor.sample_rate == 48000
        assert processor.frame_size == 480
        assert processor.search_resolution == 10.0
        assert len(processor.mic_pairs) == 6  # C(4,2) = 6 pairs
    
    def test_direction_estimation(self):
        """Test basic direction estimation."""
        mic_positions = create_linear_array(4, spacing=0.05)
        
        processor = SRPPHATProcessor(
            microphone_positions=mic_positions,
            sample_rate=48000,
            frame_size=480,
            search_resolution=15.0  # Coarse resolution for speed
        )
        
        # Create test frame with random audio
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=4,
            frame_size=480,
            data=np.random.randn(4, 480).astype(np.float32) * 0.1
        )
        
        estimate = processor.estimate_direction(frame)
        
        # Basic validation
        assert isinstance(estimate, DirectionEstimate)
        assert -180 <= estimate.azimuth <= 180
        assert -90 <= estimate.elevation <= 90
        assert 0.0 <= estimate.confidence <= 1.0


class TestSSLService:
    """Test SSL service functionality."""
    
    async def test_ssl_service_initialization(self):
        """Test SSL service initialization."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=8)
        mic_array = create_classroom_array()
        
        ssl_service = SSLService("TestSSL", config, mic_array)
        
        assert ssl_service.service_name == "TestSSL"
        assert len(ssl_service.microphone_positions) == 8
        assert ssl_service.estimation_interval_ms == 100.0
        assert not ssl_service.is_running
    
    async def test_ssl_service_lifecycle(self):
        """Test SSL service start/stop lifecycle."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        ssl_service = SSLService("TestSSL", config, mic_array)
        
        # Start service
        await ssl_service.start()
        assert ssl_service.is_running
        
        # Stop service
        await ssl_service.stop()
        assert not ssl_service.is_running
    
    async def test_ssl_frame_processing(self):
        """Test SSL frame processing."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        ssl_service = SSLService("TestSSL", config, mic_array)
        await ssl_service.start()
        
        try:
            # Create test frame
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=4,
                frame_size=480,
                data=np.random.randn(4, 480).astype(np.float32) * 0.1
            )
            
            # Process frame
            result = await ssl_service.process(frame)
            
            assert result.success
            assert result.data is not None
            
            # Check SSL metadata was added
            metadata = result.data.metadata
            assert 'ssl_azimuth' in metadata
            assert 'ssl_elevation' in metadata
            assert 'ssl_confidence' in metadata
            assert 'ssl_area' in metadata
            
            # Validate metadata values
            assert isinstance(metadata['ssl_azimuth'], (int, float))
            assert isinstance(metadata['ssl_elevation'], (int, float))
            assert 0.0 <= metadata['ssl_confidence'] <= 1.0
            assert metadata['ssl_area'] in [area.value for area in ClassroomArea]
        
        finally:
            await ssl_service.stop()
    
    async def test_ssl_metrics(self):
        """Test SSL metrics collection."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        ssl_service = SSLService("TestSSL", config, mic_array)
        await ssl_service.start()
        
        try:
            # Process a frame to generate metrics
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=4,
                frame_size=480,
                data=np.random.randn(4, 480).astype(np.float32) * 0.1
            )
            
            await ssl_service.process(frame)
            
            # Get SSL metrics
            metrics = ssl_service.get_ssl_metrics()
            
            assert 'directions_estimated' in metrics
            assert 'direction_changes' in metrics
            assert 'current_azimuth' in metrics
            assert 'current_area' in metrics
            assert 'estimation_interval_ms' in metrics
            assert 'microphone_count' in metrics
            
            assert metrics['directions_estimated'] >= 1
            assert metrics['microphone_count'] == 4
            assert metrics['estimation_interval_ms'] == 100.0
        
        finally:
            await ssl_service.stop()
    
    async def test_estimation_interval_setting(self):
        """Test estimation interval configuration."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        ssl_service = SSLService("TestSSL", config, mic_array)
        
        # Test valid interval
        ssl_service.set_estimation_interval(200.0)
        assert ssl_service.estimation_interval_ms == 200.0
        
        # Test too small interval (should be clamped)
        ssl_service.set_estimation_interval(10.0)
        assert ssl_service.estimation_interval_ms == 50.0
        
        # Test too large interval (should be clamped)
        ssl_service.set_estimation_interval(2000.0)
        assert ssl_service.estimation_interval_ms == 1000.0
    
    async def test_direction_tracking_reset(self):
        """Test direction tracking reset."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        mic_array = create_linear_array(4)
        
        ssl_service = SSLService("TestSSL", config, mic_array)
        await ssl_service.start()
        
        try:
            # Process frame to establish tracking
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=4,
                frame_size=480,
                data=np.random.randn(4, 480).astype(np.float32) * 0.1
            )
            
            await ssl_service.process(frame)
            
            # Should have direction now
            assert ssl_service.get_current_direction() is not None
            
            # Reset tracking
            ssl_service.reset_tracking()
            
            # Should be reset
            assert ssl_service.get_current_direction() is None
            assert ssl_service.get_current_area() == ClassroomArea.UNKNOWN
        
        finally:
            await ssl_service.stop()
    
    async def test_microphone_validation(self):
        """Test microphone configuration validation."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=4)
        
        # Test insufficient microphones
        single_mic = [MicrophonePosition(0.0, 0.0, 0.0, 0)]
        
        ssl_service = SSLService("TestSSL", config, single_mic)
        
        with pytest.raises(Exception):  # Should raise ServiceError
            await ssl_service.start()
        
        # Test microphone count mismatch
        wrong_count_mics = create_linear_array(2)  # 2 mics for 4 channels
        
        ssl_service2 = SSLService("TestSSL2", config, wrong_count_mics)
        
        with pytest.raises(Exception):  # Should raise ServiceError
            await ssl_service2.start()


# Integration test
class TestSSLIntegration:
    """Integration tests for SSL service."""
    
    async def test_ssl_classroom_scenario(self):
        """Test SSL service in classroom scenario."""
        # Setup classroom configuration
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=8)
        mic_array = create_classroom_array()
        
        classroom_geometry = ClassroomGeometry(
            length=12.0, width=8.0, height=3.0,
            teacher_area_bounds=(0.0, 4.0, 0.0, 8.0),
            microphone_array_position=(6.0, 4.0, 2.5)
        )
        
        ssl_service = SSLService("ClassroomSSL", config, mic_array, classroom_geometry)
        await ssl_service.start()
        
        try:
            # Simulate multiple frames
            for i in range(5):
                frame = AudioFrame(
                    timestamp=datetime.now(),
                    sample_rate=48000,
                    channels=8,
                    frame_size=480,
                    data=np.random.randn(8, 480).astype(np.float32) * 0.1
                )
                
                result = await ssl_service.process(frame)
                assert result.success
                
                # Brief delay to allow estimation interval
                await asyncio.sleep(0.11)  # Slightly more than 100ms
            
            # Check that multiple directions were estimated
            metrics = ssl_service.get_ssl_metrics()
            assert metrics['directions_estimated'] >= 3  # Should have estimated several times
            
            # Check current direction is available
            current_direction = ssl_service.get_current_direction()
            assert current_direction is not None
            assert isinstance(current_direction.area, ClassroomArea)
        
        finally:
            await ssl_service.stop()
