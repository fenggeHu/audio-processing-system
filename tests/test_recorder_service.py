"""
Tests for RecorderService - Recording and Streaming Service.

This module tests the RecorderService functionality including
audio encoding, file management, streaming, and synchronization.
"""

import pytest
import asyncio
import tempfile
import shutil
import os
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np

from src.audio_processing.services.recorder import (
    RecorderService, RecordingConfig, StreamingConfig,
    AudioCodec, StreamingProtocol, FileFormat, RecordingMode,
    PCMEncoder, CompressedEncoder, FileWriter, StreamingClient
)
from src.audio_processing.models import AudioFrame, AudioConfig
from src.audio_processing.exceptions import ServiceError


class TestPCMEncoder:
    """Test PCM audio encoder."""
    
    @pytest.fixture
    def pcm_encoder(self):
        """Create PCM encoder instance."""
        return PCMEncoder()
    
    @pytest.fixture
    def recording_config(self):
        """Create recording configuration."""
        return RecordingConfig(
            codec=AudioCodec.PCM_16,
            sample_rate=48000,
            channels=2,
            bit_depth=16
        )
    
    @pytest.fixture
    def test_frame(self):
        """Create test audio frame."""
        sample_rate = 48000
        frame_size = 480  # 10ms at 48kHz
        channels = 2
        
        # Generate test audio data (sine wave)
        t = np.linspace(0, frame_size / sample_rate, frame_size)
        frequency = 440  # A4 note
        audio_data = np.sin(2 * np.pi * frequency * t) * 0.5
        
        # Create stereo data
        stereo_data = np.array([audio_data, audio_data * 0.8])  # Slightly different channels
        
        return AudioFrame(
            timestamp=datetime.now(),
            sample_rate=sample_rate,
            channels=channels,
            frame_size=frame_size,
            data=stereo_data
        )
    
    async def test_pcm_encoder_initialization(self, pcm_encoder, recording_config):
        """Test PCM encoder initialization."""
        await pcm_encoder.initialize(recording_config)
        
        assert pcm_encoder.bit_depth == 16
        assert pcm_encoder.sample_rate == 48000
        assert pcm_encoder.channels == 2
        assert pcm_encoder.bytes_per_sample == 2
    
    async def test_pcm_16_encoding(self, pcm_encoder, recording_config, test_frame):
        """Test 16-bit PCM encoding."""
        await pcm_encoder.initialize(recording_config)
        
        encoded_data = await pcm_encoder.encode_frame(test_frame)
        
        # Check encoded data size
        expected_size = test_frame.channels * test_frame.frame_size * 2  # 2 bytes per sample
        assert len(encoded_data) == expected_size
        
        # Verify data is not empty
        assert encoded_data != b'\x00' * expected_size
    
    async def test_pcm_24_encoding(self, pcm_encoder):
        """Test 24-bit PCM encoding."""
        config = RecordingConfig(
            codec=AudioCodec.PCM_24,
            bit_depth=24
        )
        
        await pcm_encoder.initialize(config)
        assert pcm_encoder.bytes_per_sample == 3
    
    async def test_codec_info(self, pcm_encoder, recording_config):
        """Test codec information retrieval."""
        await pcm_encoder.initialize(recording_config)
        
        codec_info = pcm_encoder.get_codec_info()
        
        assert codec_info['codec'] == 'pcm'
        assert codec_info['bit_depth'] == 16
        assert codec_info['sample_rate'] == 48000
        assert codec_info['channels'] == 2
        assert codec_info['compressed'] is False


class TestFileWriter:
    """Test file writer functionality."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def recording_config(self, temp_dir):
        """Create recording configuration with temp directory."""
        return RecordingConfig(
            output_directory=temp_dir,
            filename_template="test_recording_{timestamp}",
            max_file_size_mb=1,  # Small size for testing
            max_file_duration_minutes=1,
            auto_segment=True,
            file_format=FileFormat.WAV
        )
    
    @pytest.fixture
    def file_writer(self, recording_config):
        """Create file writer instance."""
        return FileWriter(recording_config)
    
    async def test_file_writer_initialization(self, file_writer, temp_dir):
        """Test file writer initialization."""
        assert file_writer.config.output_directory == temp_dir
        assert os.path.exists(temp_dir)
        assert file_writer.session_id is not None
        assert len(file_writer.session_id) > 0
    
    async def test_start_new_file(self, file_writer):
        """Test starting a new recording file."""
        file_path = await file_writer.start_new_file()
        
        assert file_path is not None
        assert file_path.endswith('.wav')
        assert os.path.exists(file_path)
        assert file_writer.current_file is not None
        assert file_writer.current_file_size >= 0
    
    async def test_write_data(self, file_writer):
        """Test writing data to file."""
        await file_writer.start_new_file()
        
        test_data = b"test audio data" * 100
        await file_writer.write_data(test_data)
        
        assert file_writer.current_file_size >= len(test_data)
        
        # Get file info
        file_info = file_writer.get_current_file_info()
        assert file_info['size_mb'] > 0
        assert file_info['duration_s'] >= 0
    
    async def test_close_file(self, file_writer):
        """Test closing recording file."""
        file_path = await file_writer.start_new_file()
        test_data = b"test audio data" * 50
        await file_writer.write_data(test_data)
        
        closed_path = await file_writer.close_current_file()
        
        assert closed_path == file_path
        assert file_writer.current_file is None
        assert os.path.exists(file_path)
        
        # Check file size
        file_size = os.path.getsize(file_path)
        assert file_size > len(test_data)  # Should include WAV header
    
    async def test_metadata_file_creation(self, file_writer):
        """Test metadata file creation."""
        file_path = await file_writer.start_new_file()
        await file_writer.write_data(b"test data")
        await file_writer.close_current_file()
        
        metadata_path = file_path + '.metadata.json'
        assert os.path.exists(metadata_path)
        
        # Verify metadata content
        import json
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        assert 'recording_info' in metadata
        assert 'audio_config' in metadata
        assert 'system_info' in metadata
        assert metadata['recording_info']['session_id'] == file_writer.session_id


class TestStreamingClient:
    """Test streaming client functionality."""
    
    @pytest.fixture
    def streaming_config(self):
        """Create streaming configuration."""
        return StreamingConfig(
            protocol=StreamingProtocol.RTMP,
            server_url="rtmp://test.server.com/live",
            stream_key="test_key",
            codec=AudioCodec.AAC,
            bitrate_kbps=128
        )
    
    @pytest.fixture
    def streaming_client(self, streaming_config):
        """Create streaming client instance."""
        return StreamingClient(streaming_config)
    
    async def test_streaming_client_initialization(self, streaming_client, streaming_config):
        """Test streaming client initialization."""
        assert streaming_client.config == streaming_config
        assert not streaming_client.connected
        assert streaming_client.buffer_size_ms == 0
        assert streaming_client.reconnect_count == 0
    
    async def test_connection_attempt(self, streaming_client):
        """Test connection attempt (will use placeholder implementation)."""
        # This will use the placeholder implementation
        connected = await streaming_client.connect()
        
        # Placeholder implementation returns True
        assert connected
        assert streaming_client.connected
    
    async def test_send_audio_data(self, streaming_client):
        """Test sending audio data."""
        await streaming_client.connect()
        
        test_data = b"audio_data" * 100
        timestamp = datetime.now()
        
        success = await streaming_client.send_audio_data(test_data, timestamp)
        assert success
        
        # Check statistics
        stats = streaming_client.get_streaming_stats()
        assert stats['connected']
        assert stats['bytes_sent'] > 0
        assert stats['frames_sent'] > 0
    
    async def test_disconnect(self, streaming_client):
        """Test disconnection."""
        await streaming_client.connect()
        assert streaming_client.connected
        
        await streaming_client.disconnect()
        assert not streaming_client.connected


class TestRecorderService:
    """Test RecorderService main functionality."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def audio_config(self):
        """Create audio configuration."""
        return AudioConfig(
            sample_rate=48000,
            frame_size=480,
            channels=2
        )
    
    @pytest.fixture
    def recording_config(self, temp_dir):
        """Create recording configuration."""
        return RecordingConfig(
            codec=AudioCodec.PCM_16,
            output_directory=temp_dir,
            max_file_size_mb=1,
            auto_segment=True
        )
    
    @pytest.fixture
    def streaming_config(self):
        """Create streaming configuration."""
        return StreamingConfig(
            protocol=StreamingProtocol.RTMP,
            server_url="rtmp://test.server.com/live",
            stream_key="test_key"
        )
    
    @pytest.fixture
    async def recorder_service(self, audio_config, recording_config, streaming_config):
        """Create and initialize recorder service."""
        service = RecorderService(
            service_name="test_recorder",
            config=audio_config,
            recording_config=recording_config,
            streaming_config=streaming_config
        )
        await service.start()
        yield service
        await service.stop()
    
    @pytest.fixture
    def test_frame(self):
        """Create test audio frame."""
        sample_rate = 48000
        frame_size = 480
        channels = 2
        
        # Generate test audio
        t = np.linspace(0, frame_size / sample_rate, frame_size)
        audio_data = np.sin(2 * np.pi * 440 * t) * 0.3  # 440Hz sine wave
        stereo_data = np.array([audio_data, audio_data])
        
        return AudioFrame(
            timestamp=datetime.now(),
            sample_rate=sample_rate,
            channels=channels,
            frame_size=frame_size,
            data=stereo_data
        )
    
    async def test_recorder_service_initialization(self, recorder_service):
        """Test recorder service initialization."""
        assert recorder_service.is_running
        assert recorder_service.encoder is not None
        assert recorder_service.file_writer is not None
        assert recorder_service.streaming_client is not None
        assert not recorder_service.recording_active
        assert not recorder_service.streaming_active
    
    async def test_start_stop_recording(self, recorder_service, temp_dir):
        """Test starting and stopping recording."""
        # Start recording
        success = await recorder_service.start_recording(RecordingMode.MANUAL)
        assert success
        assert recorder_service.recording_active
        
        status = recorder_service.get_recording_status()
        assert status['recording_active']
        assert status['current_file'] is not None
        
        # Stop recording
        file_path = await recorder_service.stop_recording()
        assert file_path is not None
        assert os.path.exists(file_path)
        assert not recorder_service.recording_active
    
    async def test_start_stop_streaming(self, recorder_service):
        """Test starting and stopping streaming."""
        # Start streaming
        success = await recorder_service.start_streaming()
        assert success
        assert recorder_service.streaming_active
        
        status = recorder_service.get_recording_status()
        assert status['streaming_active']
        assert status['streaming_connected']
        
        # Stop streaming
        await recorder_service.stop_streaming()
        assert not recorder_service.streaming_active
    
    async def test_frame_processing(self, recorder_service, test_frame):
        """Test audio frame processing."""
        # Start recording
        await recorder_service.start_recording()
        
        # Process frame
        result = await recorder_service.process(test_frame)
        
        # Should return original frame (pass-through)
        assert result.success
        assert result.data is not None
        assert result.data.timestamp == test_frame.timestamp
        
        # Check metrics
        metrics = recorder_service.get_recorder_metrics()
        assert metrics['recording_active']
        assert metrics['audio_level_dbfs'] != -60.0  # Should have detected audio
    
    async def test_multiple_frame_processing(self, recorder_service, test_frame):
        """Test processing multiple frames."""
        await recorder_service.start_recording()
        
        # Process multiple frames
        for i in range(10):
            frame = AudioFrame(
                timestamp=datetime.now() + timedelta(milliseconds=i * 10),
                sample_rate=test_frame.sample_rate,
                channels=test_frame.channels,
                frame_size=test_frame.frame_size,
                data=test_frame.data.copy()
            )
            
            result = await recorder_service.process(frame)
            assert result.success
        
        # Check sync info
        sync_info = recorder_service.get_sync_info()
        assert sync_info['frame_count'] == 10
        assert sync_info['avg_frame_interval_ms'] > 0
    
    async def test_config_updates(self, recorder_service):
        """Test configuration updates."""
        # Update recording config
        new_recording_config = RecordingConfig(
            codec=AudioCodec.PCM_24,
            bit_depth=24
        )
        
        await recorder_service.update_recording_config(new_recording_config)
        assert recorder_service.recording_config.codec == AudioCodec.PCM_24
        
        # Update streaming config
        new_streaming_config = StreamingConfig(
            protocol=StreamingProtocol.WEBRTC,
            server_url="wss://test.webrtc.com"
        )
        
        await recorder_service.update_streaming_config(new_streaming_config)
        assert recorder_service.streaming_config.protocol == StreamingProtocol.WEBRTC
    
    async def test_metrics_collection(self, recorder_service, test_frame):
        """Test metrics collection."""
        await recorder_service.start_recording()
        await recorder_service.start_streaming()
        
        # Process some frames
        for _ in range(5):
            await recorder_service.process(test_frame)
        
        # Get metrics
        metrics = recorder_service.get_recorder_metrics()
        
        assert metrics['recording_active']
        assert metrics['streaming_active']
        assert metrics['audio_level_dbfs'] != -60.0
        assert metrics['encoding_latency_ms'] >= 0
        
        # Get status
        status = recorder_service.get_recording_status()
        assert status['recording_active']
        assert status['streaming_active']
    
    async def test_config_schema(self, recorder_service):
        """Test configuration schema."""
        schema = recorder_service.get_config_schema()
        
        assert 'type' in schema
        assert schema['type'] == 'object'
        assert 'properties' in schema
        assert 'recording' in schema['properties']
        assert 'streaming' in schema['properties']
        
        # Check recording properties
        recording_props = schema['properties']['recording']['properties']
        assert 'codec' in recording_props
        assert 'file_format' in recording_props
        assert 'sample_rate' in recording_props
        
        # Check streaming properties
        streaming_props = schema['properties']['streaming']['properties']
        assert 'protocol' in streaming_props
        assert 'server_url' in streaming_props
        assert 'bitrate_kbps' in streaming_props


class TestIntegration:
    """Integration tests for recorder service."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    async def test_full_recording_workflow(self, temp_dir):
        """Test complete recording workflow."""
        # Setup
        audio_config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        recording_config = RecordingConfig(
            codec=AudioCodec.PCM_16,
            output_directory=temp_dir,
            max_file_size_mb=1
        )
        
        service = RecorderService(
            service_name="integration_test",
            config=audio_config,
            recording_config=recording_config
        )
        
        try:
            # Start service
            await service.start()
            
            # Start recording
            await service.start_recording()
            
            # Generate and process test audio
            for i in range(20):  # Process 20 frames (200ms of audio)
                t = np.linspace(0, 480 / 48000, 480)
                audio_data = np.sin(2 * np.pi * 440 * t) * 0.5
                stereo_data = np.array([audio_data, audio_data])
                
                frame = AudioFrame(
                    timestamp=datetime.now(),
                    sample_rate=48000,
                    channels=2,
                    frame_size=480,
                    data=stereo_data
                )
                
                result = await service.process(frame)
                assert result.success
            
            # Stop recording
            file_path = await service.stop_recording()
            assert file_path is not None
            assert os.path.exists(file_path)
            
            # Verify file was created with content
            file_size = os.path.getsize(file_path)
            assert file_size > 1000  # Should have WAV header + audio data
            
            # Verify metadata file
            metadata_path = file_path + '.metadata.json'
            assert os.path.exists(metadata_path)
            
        finally:
            await service.stop()
    
    async def test_concurrent_recording_and_streaming(self, temp_dir):
        """Test concurrent recording and streaming."""
        audio_config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        recording_config = RecordingConfig(
            codec=AudioCodec.PCM_16,
            output_directory=temp_dir
        )
        streaming_config = StreamingConfig(
            protocol=StreamingProtocol.RTMP,
            server_url="rtmp://test.server.com/live"
        )
        
        service = RecorderService(
            service_name="concurrent_test",
            config=audio_config,
            recording_config=recording_config,
            streaming_config=streaming_config
        )
        
        try:
            await service.start()
            
            # Start both recording and streaming
            recording_started = await service.start_recording()
            streaming_started = await service.start_streaming()
            
            assert recording_started
            assert streaming_started
            
            # Process frames
            for i in range(10):
                frame = AudioFrame(
                    timestamp=datetime.now(),
                    sample_rate=48000,
                    channels=2,
                    frame_size=480,
                    data=np.random.random((2, 480)) * 0.1
                )
                
                result = await service.process(frame)
                assert result.success
            
            # Verify both are active
            status = service.get_recording_status()
            assert status['recording_active']
            assert status['streaming_active']
            
            # Stop both
            await service.stop_recording()
            await service.stop_streaming()
            
            # Verify both stopped
            status = service.get_recording_status()
            assert not status['recording_active']
            assert not status['streaming_active']
            
        finally:
            await service.stop()


if __name__ == "__main__":
    pytest.main([__file__])