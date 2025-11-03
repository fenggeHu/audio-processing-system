"""
Integration tests for core framework components.
"""

import pytest
import asyncio
import numpy as np
from datetime import datetime

from audio_processing.models import AudioFrame, AudioConfig, ProcessingResult
from audio_processing.interfaces import IAudioService
from audio_processing.base import BaseAudioProcessor
from audio_processing.container import DIContainer
from audio_processing.service_manager import ServiceManager


class MockAudioProcessor(BaseAudioProcessor):
    """Mock audio processor for testing."""
    
    def __init__(self, service_name: str, config: AudioConfig):
        super().__init__(service_name, config)
        self.processed_frames = []
    
    async def _initialize(self) -> None:
        """Initialize mock processor."""
        pass
    
    async def _cleanup(self) -> None:
        """Cleanup mock processor."""
        pass
    
    async def _process_frame(self, frame: AudioFrame) -> AudioFrame:
        """Mock frame processing - just add some metadata."""
        processed_frame = frame.copy()
        processed_frame.metadata = processed_frame.metadata or {}
        processed_frame.metadata['processed_by'] = self.service_name
        processed_frame.metadata['processing_count'] = len(self.processed_frames) + 1
        
        self.processed_frames.append(frame)
        
        # Simulate some processing time
        await asyncio.sleep(0.001)  # 1ms
        
        return processed_frame


class TestDIContainer:
    """Test dependency injection container."""
    
    def test_register_and_get_singleton(self):
        """Test singleton service registration and retrieval."""
        container = DIContainer()
        config = AudioConfig()
        
        # Register service
        container.register_singleton(
            IAudioService,
            MockAudioProcessor,
            name="TestProcessor",
            config={"service_name": "TestProcessor", "config": config}
        )
        
        assert container.is_registered(name="TestProcessor")
    
    async def test_service_creation(self):
        """Test service instance creation."""
        container = DIContainer()
        config = AudioConfig()
        
        # Register service with proper config
        container.register_singleton(
            MockAudioProcessor,
            name="TestProcessor",
            config={"config": config}
        )
        
        # Get service instance
        service = await container.get_by_name("TestProcessor")
        
        assert isinstance(service, MockAudioProcessor)
        assert service.service_name == "TestProcessor"


class TestServiceManager:
    """Test service manager functionality."""
    
    async def test_service_registration_and_startup(self):
        """Test service registration and startup process."""
        config = AudioConfig()
        manager = ServiceManager(config)
        
        # Register a mock service
        manager.register_service(
            MockAudioProcessor,
            name="TestProcessor",
            config={"config": config}
        )
        
        # Start service manager
        await manager.start()
        
        assert manager.is_running
        
        # Get service status
        status = manager.get_service_status()
        assert "TestProcessor" in status
        
        # Stop service manager
        await manager.stop()
        
        assert not manager.is_running
    
    async def test_service_processing(self):
        """Test end-to-end service processing."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        manager = ServiceManager(config)
        
        # Register service
        manager.register_service(
            MockAudioProcessor,
            name="TestProcessor",
            config={"config": config}
        )
        
        # Start manager
        await manager.start()
        
        try:
            # Get service instance
            service = await manager.get_service_by_name("TestProcessor")
            
            # Create test audio frame
            timestamp = datetime.now()
            data = np.random.randn(2, 480) * 0.1  # Small amplitude
            
            frame = AudioFrame(
                timestamp=timestamp,
                sample_rate=48000,
                channels=2,
                frame_size=480,
                data=data
            )
            
            # Process frame
            result = await service.process(frame)
            
            # Verify processing result
            assert result.success
            assert result.data is not None
            assert result.data.metadata['processed_by'] == "TestProcessor"
            assert result.data.metadata['processing_count'] == 1
            assert result.processing_time_ms > 0
            
            # Process another frame
            result2 = await service.process(frame)
            assert result2.data.metadata['processing_count'] == 2
            
        finally:
            await manager.stop()


class TestBaseAudioProcessor:
    """Test base audio processor functionality."""
    
    async def test_processor_lifecycle(self):
        """Test processor start/stop lifecycle."""
        config = AudioConfig()
        processor = MockAudioProcessor("TestProcessor", config)
        
        assert not processor.is_running
        
        # Start processor
        await processor.start()
        assert processor.is_running
        
        # Stop processor
        await processor.stop()
        assert not processor.is_running
    
    async def test_frame_processing_with_metrics(self):
        """Test frame processing with metrics collection."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        processor = MockAudioProcessor("TestProcessor", config)
        
        await processor.start()
        
        try:
            # Create test frame
            timestamp = datetime.now()
            data = np.random.randn(1, 480) * 0.1
            
            frame = AudioFrame(
                timestamp=timestamp,
                sample_rate=48000,
                channels=1,
                frame_size=480,
                data=data
            )
            
            # Process frame
            result = await processor.process(frame)
            
            # Check result
            assert result.success
            assert result.processing_time_ms > 0
            
            # Check metrics
            metrics = processor.get_metrics()
            assert metrics.frames_processed == 1
            assert metrics.frames_dropped == 0
            assert metrics.processing_latency_ms > 0
            
        finally:
            await processor.stop()
    
    async def test_invalid_frame_handling(self):
        """Test handling of invalid audio frames."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        processor = MockAudioProcessor("TestProcessor", config)
        
        await processor.start()
        
        try:
            # Create frame with wrong sample rate
            timestamp = datetime.now()
            data = np.random.randn(2, 480)
            
            invalid_frame = AudioFrame(
                timestamp=timestamp,
                sample_rate=44100,  # Wrong sample rate
                channels=2,
                frame_size=480,
                data=data
            )
            
            # Process invalid frame
            result = await processor.process(invalid_frame)
            
            # Should fail
            assert not result.success
            assert result.error is not None
            assert "Sample rate mismatch" in result.error
            
            # Check metrics
            metrics = processor.get_metrics()
            assert metrics.frames_processed == 0
            assert metrics.frames_dropped == 1
            
        finally:
            await processor.stop()


class TestAudioFrameProcessing:
    """Test audio frame processing utilities."""
    
    def test_frame_operations(self):
        """Test various frame operations."""
        # Create stereo frame
        timestamp = datetime.now()
        left_channel = np.sin(2 * np.pi * 1000 * np.linspace(0, 0.01, 480))  # 1kHz
        right_channel = np.sin(2 * np.pi * 2000 * np.linspace(0, 0.01, 480))  # 2kHz
        data = np.array([left_channel, right_channel])
        
        frame = AudioFrame(
            timestamp=timestamp,
            sample_rate=48000,
            channels=2,
            frame_size=480,
            data=data
        )
        
        # Test mono conversion
        mono_frame = frame.to_mono()
        assert mono_frame.channels == 1
        assert mono_frame.frame_size == 480
        
        # Test RMS level calculation
        rms_level = frame.get_rms_level()
        assert -10 < rms_level < 0  # Should be reasonable level
        
        # Test frame copying
        copied_frame = frame.copy()
        assert np.array_equal(copied_frame.data, frame.data)
        
        # Modify copy and ensure original is unchanged
        copied_frame.data[0, 0] = 999
        assert frame.data[0, 0] != 999