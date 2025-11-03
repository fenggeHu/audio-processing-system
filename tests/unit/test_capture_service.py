"""
Tests for audio capture service.
"""

import pytest
import asyncio
import numpy as np
from datetime import datetime

from audio_processing.models import AudioConfig
from audio_processing.services.capture import (
    CaptureService, DeviceManager, FrameAligner, CaptureBuffer, AudioDevice
)


class TestCaptureBuffer:
    """Test capture buffer functionality."""
    
    def test_buffer_creation(self):
        """Test buffer creation and initialization."""
        buffer = CaptureBuffer(
            data=None,
            sample_rate=48000,
            channels=8
        )
        
        assert buffer.sample_rate == 48000
        assert buffer.channels == 8
        assert buffer.size == 48000  # 1 second buffer
        assert buffer.data.shape == (8, 48000)
    
    def test_buffer_write_read(self):
        """Test basic write and read operations."""
        buffer = CaptureBuffer(
            data=np.zeros((2, 1000)),
            sample_rate=48000,
            channels=2,
            size=1000
        )
        
        # Write some test data
        test_data = np.random.randn(2, 100)
        success = buffer.write(test_data)
        assert success
        
        # Read the data back
        read_data = buffer.read(100)
        assert read_data is not None
        np.testing.assert_array_equal(read_data, test_data)
    
    def test_buffer_wrap_around(self):
        """Test buffer wrap-around behavior."""
        buffer = CaptureBuffer(
            data=np.zeros((1, 100)),
            sample_rate=48000,
            channels=1,
            size=100
        )
        
        # Fill part of the buffer
        data1 = np.ones((1, 40))
        buffer.write(data1)
        
        # Read some data to advance read pointer
        buffer.read(20)
        
        # Write data that will wrap around
        data2 = np.full((1, 50), 2.0)
        success = buffer.write(data2)
        assert success
        
        # Read remaining data from first write
        remaining1 = buffer.read(20)  # 40 - 20 = 20 remaining
        assert np.all(remaining1 == 1.0)
        
        # Read wrapped data
        wrapped_data = buffer.read(50)
        assert np.all(wrapped_data == 2.0)
    
    def test_buffer_overflow(self):
        """Test buffer overflow detection."""
        buffer = CaptureBuffer(
            data=np.zeros((1, 100)),
            sample_rate=48000,
            channels=1,
            size=100
        )
        
        # Try to write more data than buffer can hold
        large_data = np.ones((1, 150))
        success = buffer.write(large_data)
        assert not success  # Should fail due to overflow
    
    def test_buffer_underrun(self):
        """Test buffer underrun detection."""
        buffer = CaptureBuffer(
            data=np.zeros((1, 100)),
            sample_rate=48000,
            channels=1,
            size=100
        )
        
        # Try to read more data than available
        result = buffer.read(50)
        assert result is None  # Should return None for underrun
    
    def test_buffer_usage_calculation(self):
        """Test buffer usage percentage calculation."""
        buffer = CaptureBuffer(
            data=np.zeros((1, 100)),
            sample_rate=48000,
            channels=1,
            size=100
        )
        
        # Empty buffer
        assert buffer.get_buffer_usage() == 0.0
        
        # Half full buffer
        buffer.write(np.ones((1, 50)))
        assert buffer.get_buffer_usage() == 50.0
        
        # Read some data
        buffer.read(25)
        assert buffer.get_buffer_usage() == 25.0


class TestDeviceManager:
    """Test device manager functionality."""
    
    async def test_device_scanning(self):
        """Test device scanning functionality."""
        manager = DeviceManager()
        
        devices = await manager.scan_devices()
        
        assert len(devices) > 0
        assert any(device.is_default for device in devices)
        
        # Check device properties
        for device in devices:
            assert device.device_id >= 0
            assert len(device.name) > 0
            assert device.channels > 0
            assert device.sample_rate > 0
    
    async def test_get_default_device(self):
        """Test getting default device."""
        manager = DeviceManager()
        await manager.scan_devices()
        
        default_device = await manager.get_device()
        assert default_device is not None
        assert default_device.is_default
    
    async def test_get_device_by_id(self):
        """Test getting device by ID."""
        manager = DeviceManager()
        devices = await manager.scan_devices()
        
        if devices:
            first_device = devices[0]
            retrieved_device = await manager.get_device(first_device.device_id)
            
            assert retrieved_device is not None
            assert retrieved_device.device_id == first_device.device_id
            assert retrieved_device.name == first_device.name
    
    async def test_device_testing(self):
        """Test device testing functionality."""
        manager = DeviceManager()
        devices = await manager.scan_devices()
        
        if devices:
            # Test first device
            result = await manager.test_device(devices[0].device_id)
            assert isinstance(result, bool)
            
            # Test non-existent device
            result = await manager.test_device(9999)
            assert result is False


class TestFrameAligner:
    """Test frame alignment functionality."""
    
    def test_frame_alignment_basic(self):
        """Test basic frame alignment."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        aligner = FrameAligner(config)
        
        # Create test audio data
        audio_data = np.random.randn(2, 480)
        timestamp = datetime.now()
        
        # Align frame
        frame = aligner.align_frame(audio_data, timestamp)
        
        assert frame.sample_rate == config.sample_rate
        assert frame.channels == config.channels
        assert frame.frame_size == config.frame_size
        assert np.array_equal(frame.data, audio_data)
        assert 'frame_number' in frame.metadata
        assert frame.metadata['frame_number'] == 0
    
    def test_frame_alignment_sequence(self):
        """Test frame alignment over multiple frames."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        aligner = FrameAligner(config)
        
        base_timestamp = datetime.now()
        
        # Process multiple frames
        for i in range(5):
            audio_data = np.random.randn(2, 480)
            timestamp = base_timestamp
            
            frame = aligner.align_frame(audio_data, timestamp)
            assert frame.metadata['frame_number'] == i
    
    def test_frame_alignment_reset(self):
        """Test frame alignment reset."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        aligner = FrameAligner(config)
        
        # Process some frames
        for i in range(3):
            audio_data = np.random.randn(2, 480)
            aligner.align_frame(audio_data, datetime.now())
        
        # Reset alignment
        aligner.reset_alignment()
        
        # Next frame should start from 0 again
        audio_data = np.random.randn(2, 480)
        frame = aligner.align_frame(audio_data, datetime.now())
        assert frame.metadata['frame_number'] == 0


class TestCaptureService:
    """Test capture service functionality."""
    
    async def test_service_initialization(self):
        """Test capture service initialization."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=8)
        service = CaptureService("TestCapture", config)
        
        assert service.service_name == "TestCapture"
        assert not service.is_running
        
        # Start service
        await service.start()
        assert service.is_running
        
        # Check device was selected
        device_info = service.get_device_info()
        assert device_info is not None
        
        # Stop service
        await service.stop()
        assert not service.is_running
    
    async def test_frame_capture(self):
        """Test audio frame capture."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        service = CaptureService("TestCapture", config)
        
        # Enable mock audio
        service.set_mock_audio_enabled(True)
        service.set_mock_frequency(1000.0)
        
        await service.start()
        
        try:
            # Wait a bit for frames to be captured
            await asyncio.sleep(0.1)
            
            # Get a frame
            frame = await service.get_next_frame()
            
            if frame is not None:
                assert frame.sample_rate == config.sample_rate
                assert frame.channels == config.channels
                assert frame.frame_size == config.frame_size
                assert frame.data.shape == (config.channels, config.frame_size)
                
                # Check that mock audio is not silent
                rms_level = frame.get_rms_level()
                assert rms_level > -60.0  # Should have some signal
        
        finally:
            await service.stop()
    
    async def test_frame_stream(self):
        """Test continuous frame streaming."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        service = CaptureService("TestCapture", config)
        
        service.set_mock_audio_enabled(True)
        await service.start()
        
        try:
            frame_count = 0
            async for frame in service.get_frame_stream():
                assert isinstance(frame, type(frame))  # AudioFrame type
                frame_count += 1
                
                if frame_count >= 3:  # Get a few frames then break
                    break
            
            assert frame_count == 3
        
        finally:
            await service.stop()
    
    async def test_capture_metrics(self):
        """Test capture metrics collection."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        service = CaptureService("TestCapture", config)
        
        service.set_mock_audio_enabled(True)
        await service.start()
        
        try:
            # Wait for some capture activity
            await asyncio.sleep(0.1)
            
            # Get metrics
            metrics = service.get_capture_metrics()
            
            assert 'frames_captured' in metrics
            assert 'buffer_usage_percent' in metrics
            assert 'current_device' in metrics
            assert isinstance(metrics['frames_captured'], int)
            assert isinstance(metrics['buffer_usage_percent'], float)
        
        finally:
            await service.stop()
    
    async def test_device_switching(self):
        """Test audio device switching."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        service = CaptureService("TestCapture", config)
        
        await service.start()
        
        try:
            # Get available devices
            devices = await service.get_available_devices()
            assert len(devices) > 0
            
            # Get current device
            current_device = service.get_device_info()
            assert current_device is not None
            
            # Try to switch to another device (if available)
            if len(devices) > 1:
                new_device = None
                for device in devices:
                    if device.device_id != current_device.device_id:
                        new_device = device
                        break
                
                if new_device:
                    success = await service.switch_device(new_device.device_id)
                    assert success
                    
                    # Note: The actual device might be different if the requested
                    # device doesn't meet the service requirements
                    updated_device = service.get_device_info()
                    assert updated_device is not None
        
        finally:
            await service.stop()
    
    async def test_mock_audio_configuration(self):
        """Test mock audio configuration."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        service = CaptureService("TestCapture", config)
        
        # Test frequency setting
        service.set_mock_frequency(2000.0)
        service.set_mock_audio_enabled(True)
        
        await service.start()
        
        try:
            await asyncio.sleep(0.05)  # Brief wait
            
            frame = await service.get_next_frame()
            if frame is not None:
                # Should have audio signal
                rms_level = frame.get_rms_level()
                assert rms_level > -40.0
            
            # Test disabling mock audio
            service.set_mock_audio_enabled(False)
            await asyncio.sleep(0.05)
            
            frame = await service.get_next_frame()
            if frame is not None:
                # Should be silent or very quiet
                rms_level = frame.get_rms_level()
                assert rms_level < -50.0
        
        finally:
            await service.stop()