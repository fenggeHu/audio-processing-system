"""
Recording and Streaming Service for audio capture and distribution.

This module implements the RecorderService with support for multiple audio
encoding formats, real-time streaming, and intelligent file management.
"""

import asyncio
import time
import os
import json
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Union, AsyncGenerator, Callable
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import numpy as np
import structlog
from collections import deque

from ..interfaces import IAudioService, IMetricsCollector
from ..base import BaseAudioProcessor
from ..models import AudioFrame, AudioConfig, ProcessingResult, AudioMetrics
from ..exceptions import ProcessingError, ServiceError
from ..communication.audio_pipeline import AudioPipeline, PipelineNode

logger = structlog.get_logger(__name__)


class AudioCodec(Enum):
    """Supported audio codecs for recording and streaming."""
    PCM_16 = "pcm_16"           # 16-bit PCM (uncompressed)
    PCM_24 = "pcm_24"           # 24-bit PCM (uncompressed)
    PCM_32 = "pcm_32"           # 32-bit PCM (uncompressed)
    AAC = "aac"                 # Advanced Audio Coding
    MP3 = "mp3"                 # MPEG-1 Audio Layer III
    OPUS = "opus"               # Opus codec (for streaming)
    FLAC = "flac"               # Free Lossless Audio Codec


class StreamingProtocol(Enum):
    """Supported streaming protocols."""
    RTMP = "rtmp"               # Real-Time Messaging Protocol
    WEBRTC = "webrtc"           # Web Real-Time Communication
    HLS = "hls"                 # HTTP Live Streaming
    DASH = "dash"               # Dynamic Adaptive Streaming over HTTP
    SRT = "srt"                 # Secure Reliable Transport


class RecordingMode(Enum):
    """Recording operation modes."""
    CONTINUOUS = "continuous"    # Continuous recording
    TRIGGERED = "triggered"      # Voice-activated recording
    SCHEDULED = "scheduled"      # Time-based recording
    MANUAL = "manual"           # Manual start/stop


class FileFormat(Enum):
    """Output file formats."""
    WAV = "wav"                 # WAV container
    MP4 = "mp4"                 # MP4 container
    MKV = "mkv"                 # Matroska container
    WEBM = "webm"               # WebM container


@dataclass
class RecordingConfig:
    """Configuration for recording operations."""
    # Basic settings
    codec: AudioCodec = AudioCodec.PCM_24
    file_format: FileFormat = FileFormat.WAV
    sample_rate: int = 48000
    channels: int = 2
    bit_depth: int = 24
    
    # File management
    output_directory: str = "./recordings"
    filename_template: str = "recording_{timestamp}_{session_id}"
    max_file_size_mb: int = 1000
    max_file_duration_minutes: int = 60
    auto_segment: bool = True
    
    # Quality settings
    bitrate_kbps: Optional[int] = None  # For compressed formats
    quality_level: float = 0.8  # 0.0-1.0 quality scale
    
    # Metadata
    include_metadata: bool = True
    metadata_format: str = "json"  # json, xml, or embedded
    
    # Storage management
    max_storage_gb: float = 100.0
    cleanup_policy: str = "oldest_first"  # oldest_first, largest_first, manual
    backup_enabled: bool = False
    backup_location: Optional[str] = None


@dataclass
class StreamingConfig:
    """Configuration for streaming operations."""
    # Protocol settings
    protocol: StreamingProtocol = StreamingProtocol.RTMP
    server_url: str = ""
    stream_key: str = ""
    
    # Audio settings
    codec: AudioCodec = AudioCodec.AAC
    sample_rate: int = 48000
    channels: int = 2
    bitrate_kbps: int = 128
    
    # Connection settings
    connection_timeout_s: int = 30
    reconnect_attempts: int = 5
    reconnect_delay_s: int = 5
    
    # Buffer settings
    buffer_size_ms: int = 500
    max_buffer_size_ms: int = 2000
    
    # Quality adaptation
    adaptive_bitrate: bool = True
    min_bitrate_kbps: int = 64
    max_bitrate_kbps: int = 320


@dataclass
class RecorderMetrics:
    """Recording and streaming performance metrics."""
    # Recording metrics
    recording_active: bool = False
    current_file_size_mb: float = 0.0
    current_file_duration_s: float = 0.0
    total_recorded_mb: float = 0.0
    files_created: int = 0
    
    # Streaming metrics
    streaming_active: bool = False
    stream_bitrate_kbps: float = 0.0
    stream_buffer_ms: float = 0.0
    stream_drops: int = 0
    stream_reconnects: int = 0
    
    # Performance metrics
    encoding_latency_ms: float = 0.0
    disk_write_latency_ms: float = 0.0
    network_latency_ms: float = 0.0
    
    # Quality metrics
    audio_level_dbfs: float = -60.0
    peak_level_dbfs: float = -60.0
    dynamic_range_db: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'recording_active': self.recording_active,
            'current_file_size_mb': self.current_file_size_mb,
            'current_file_duration_s': self.current_file_duration_s,
            'total_recorded_mb': self.total_recorded_mb,
            'files_created': self.files_created,
            'streaming_active': self.streaming_active,
            'stream_bitrate_kbps': self.stream_bitrate_kbps,
            'stream_buffer_ms': self.stream_buffer_ms,
            'stream_drops': self.stream_drops,
            'stream_reconnects': self.stream_reconnects,
            'encoding_latency_ms': self.encoding_latency_ms,
            'disk_write_latency_ms': self.disk_write_latency_ms,
            'network_latency_ms': self.network_latency_ms,
            'audio_level_dbfs': self.audio_level_dbfs,
            'peak_level_dbfs': self.peak_level_dbfs,
            'dynamic_range_db': self.dynamic_range_db
        }


class AudioEncoder(ABC):
    """Abstract base class for audio encoders."""
    
    @abstractmethod
    async def initialize(self, config: RecordingConfig) -> None:
        """Initialize encoder with configuration."""
        pass
    
    @abstractmethod
    async def encode_frame(self, frame: AudioFrame) -> bytes:
        """Encode audio frame to bytes."""
        pass
    
    @abstractmethod
    async def finalize(self) -> bytes:
        """Finalize encoding and return any remaining data."""
        pass
    
    @abstractmethod
    def get_codec_info(self) -> Dict[str, Any]:
        """Get codec information and parameters."""
        pass


class PCMEncoder(AudioEncoder):
    """PCM audio encoder for uncompressed audio."""
    
    def __init__(self):
        self.bit_depth = 16
        self.sample_rate = 48000
        self.channels = 2
        self.bytes_per_sample = 2
        
    async def initialize(self, config: RecordingConfig) -> None:
        """Initialize PCM encoder."""
        self.bit_depth = config.bit_depth
        self.sample_rate = config.sample_rate
        self.channels = config.channels
        
        if config.codec == AudioCodec.PCM_16:
            self.bytes_per_sample = 2
        elif config.codec == AudioCodec.PCM_24:
            self.bytes_per_sample = 3
        elif config.codec == AudioCodec.PCM_32:
            self.bytes_per_sample = 4
        else:
            raise ValueError(f"Unsupported PCM codec: {config.codec}")
        
        logger.info("PCM encoder initialized", 
                   bit_depth=self.bit_depth,
                   sample_rate=self.sample_rate,
                   channels=self.channels)
    
    async def encode_frame(self, frame: AudioFrame) -> bytes:
        """Encode audio frame to PCM bytes."""
        # Convert float32 data to integer PCM
        if self.bit_depth == 16:
            # Convert to 16-bit signed integers
            pcm_data = (frame.data * 32767).astype(np.int16)
        elif self.bit_depth == 24:
            # Convert to 24-bit signed integers (stored as 32-bit)
            pcm_data = (frame.data * 8388607).astype(np.int32)
        elif self.bit_depth == 32:
            # Convert to 32-bit signed integers
            pcm_data = (frame.data * 2147483647).astype(np.int32)
        else:
            raise ValueError(f"Unsupported bit depth: {self.bit_depth}")
        
        # Interleave channels and convert to bytes
        if frame.channels > 1:
            # Interleave channels: [L0, R0, L1, R1, ...]
            interleaved = np.empty((frame.channels * frame.frame_size,), dtype=pcm_data.dtype)
            for ch in range(frame.channels):
                interleaved[ch::frame.channels] = pcm_data[ch, :]
            pcm_data = interleaved
        else:
            pcm_data = pcm_data.flatten()
        
        return pcm_data.tobytes()
    
    async def finalize(self) -> bytes:
        """Finalize PCM encoding."""
        return b""  # No finalization needed for PCM
    
    def get_codec_info(self) -> Dict[str, Any]:
        """Get PCM codec information."""
        return {
            'codec': 'pcm',
            'bit_depth': self.bit_depth,
            'sample_rate': self.sample_rate,
            'channels': self.channels,
            'bytes_per_sample': self.bytes_per_sample,
            'compressed': False
        }


class CompressedEncoder(AudioEncoder):
    """Placeholder for compressed audio encoders (AAC, MP3, etc.)."""
    
    def __init__(self, codec: AudioCodec):
        self.codec = codec
        self.config = None
        
    async def initialize(self, config: RecordingConfig) -> None:
        """Initialize compressed encoder."""
        self.config = config
        
        # In production, would initialize actual codec libraries
        # (e.g., ffmpeg, libfdk-aac, lame, etc.)
        logger.info("Compressed encoder initialized", 
                   codec=self.codec.value,
                   bitrate=config.bitrate_kbps)
    
    async def encode_frame(self, frame: AudioFrame) -> bytes:
        """Encode audio frame using compressed codec."""
        # Placeholder implementation
        # In production, would use actual codec libraries
        
        # Simulate compressed data (much smaller than PCM)
        compression_ratio = 0.1 if self.codec == AudioCodec.MP3 else 0.15
        original_size = frame.data.nbytes
        compressed_size = int(original_size * compression_ratio)
        
        # Return placeholder compressed data
        return b"compressed_audio_data" + os.urandom(compressed_size - 20)
    
    async def finalize(self) -> bytes:
        """Finalize compressed encoding."""
        # Return any remaining encoded data
        return b"final_compressed_data"
    
    def get_codec_info(self) -> Dict[str, Any]:
        """Get compressed codec information."""
        return {
            'codec': self.codec.value,
            'bitrate_kbps': self.config.bitrate_kbps if self.config else None,
            'sample_rate': self.config.sample_rate if self.config else None,
            'channels': self.config.channels if self.config else None,
            'compressed': True
        }


class FileWriter:
    """File writer for audio recordings with automatic segmentation."""
    
    def __init__(self, config: RecordingConfig):
        self.config = config
        self.current_file = None
        self.current_file_path = None
        self.current_file_size = 0
        self.current_file_start_time = None
        self.session_id = self._generate_session_id()
        self.file_counter = 0
        
        # Ensure output directory exists
        os.makedirs(config.output_directory, exist_ok=True)
        
        logger.info("File writer initialized", 
                   output_dir=config.output_directory,
                   session_id=self.session_id)
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = hashlib.md5(os.urandom(16)).hexdigest()[:8]
        return f"{timestamp}_{random_suffix}"
    
    async def start_new_file(self) -> str:
        """Start a new recording file."""
        # Close current file if open
        if self.current_file:
            await self.close_current_file()
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.config.filename_template.format(
            timestamp=timestamp,
            session_id=self.session_id,
            counter=self.file_counter
        )
        
        # Add file extension based on format
        if self.config.file_format == FileFormat.WAV:
            filename += ".wav"
        elif self.config.file_format == FileFormat.MP4:
            filename += ".mp4"
        elif self.config.file_format == FileFormat.MKV:
            filename += ".mkv"
        elif self.config.file_format == FileFormat.WEBM:
            filename += ".webm"
        
        self.current_file_path = os.path.join(self.config.output_directory, filename)
        
        # Open file for writing
        self.current_file = open(self.current_file_path, 'wb')
        self.current_file_size = 0
        self.current_file_start_time = datetime.now()
        self.file_counter += 1
        
        # Write file header if needed
        await self._write_file_header()
        
        logger.info("New recording file started", 
                   filename=filename,
                   path=self.current_file_path)
        
        return self.current_file_path
    
    async def write_data(self, data: bytes) -> None:
        """Write audio data to current file."""
        if not self.current_file:
            await self.start_new_file()
        
        start_time = time.time()
        
        # Write data to file
        self.current_file.write(data)
        self.current_file_size += len(data)
        
        # Force write to disk periodically
        if self.current_file_size % (1024 * 1024) == 0:  # Every 1MB
            self.current_file.flush()
            os.fsync(self.current_file.fileno())
        
        write_time = (time.time() - start_time) * 1000  # ms
        
        # Check if file needs to be segmented
        if self.config.auto_segment:
            await self._check_segmentation()
        
        return write_time
    
    async def close_current_file(self) -> Optional[str]:
        """Close current recording file."""
        if not self.current_file:
            return None
        
        # Write file footer if needed
        await self._write_file_footer()
        
        # Close file
        self.current_file.close()
        file_path = self.current_file_path
        
        # Write metadata file
        if self.config.include_metadata:
            await self._write_metadata_file(file_path)
        
        # Reset state
        self.current_file = None
        self.current_file_path = None
        self.current_file_size = 0
        self.current_file_start_time = None
        
        logger.info("Recording file closed", path=file_path)
        return file_path
    
    async def _write_file_header(self) -> None:
        """Write file format header."""
        if self.config.file_format == FileFormat.WAV:
            # Write WAV header
            header = self._create_wav_header()
            self.current_file.write(header)
            self.current_file_size += len(header)
    
    async def _write_file_footer(self) -> None:
        """Write file format footer and update header."""
        if self.config.file_format == FileFormat.WAV:
            # Update WAV header with final file size
            self.current_file.seek(0)
            header = self._create_wav_header(final_size=self.current_file_size)
            self.current_file.write(header)
    
    def _create_wav_header(self, final_size: Optional[int] = None) -> bytes:
        """Create WAV file header."""
        # Simplified WAV header creation
        # In production, would use proper WAV library
        
        sample_rate = self.config.sample_rate
        channels = self.config.channels
        bits_per_sample = self.config.bit_depth
        
        # Calculate sizes
        byte_rate = sample_rate * channels * bits_per_sample // 8
        block_align = channels * bits_per_sample // 8
        
        if final_size:
            data_size = final_size - 44  # Subtract header size
            file_size = final_size - 8
        else:
            data_size = 0
            file_size = 36
        
        # Create header
        header = b'RIFF'
        header += file_size.to_bytes(4, 'little')
        header += b'WAVE'
        header += b'fmt '
        header += (16).to_bytes(4, 'little')  # fmt chunk size
        header += (1).to_bytes(2, 'little')   # PCM format
        header += channels.to_bytes(2, 'little')
        header += sample_rate.to_bytes(4, 'little')
        header += byte_rate.to_bytes(4, 'little')
        header += block_align.to_bytes(2, 'little')
        header += bits_per_sample.to_bytes(2, 'little')
        header += b'data'
        header += data_size.to_bytes(4, 'little')
        
        return header
    
    async def _check_segmentation(self) -> None:
        """Check if current file should be segmented."""
        if not self.current_file_start_time:
            return
        
        # Check file size limit
        size_mb = self.current_file_size / (1024 * 1024)
        if size_mb >= self.config.max_file_size_mb:
            logger.info("File size limit reached, starting new segment", 
                       size_mb=size_mb)
            await self.start_new_file()
            return
        
        # Check duration limit
        duration = datetime.now() - self.current_file_start_time
        duration_minutes = duration.total_seconds() / 60
        if duration_minutes >= self.config.max_file_duration_minutes:
            logger.info("File duration limit reached, starting new segment", 
                       duration_minutes=duration_minutes)
            await self.start_new_file()
    
    async def _write_metadata_file(self, audio_file_path: str) -> None:
        """Write metadata file for recording."""
        metadata = {
            'recording_info': {
                'session_id': self.session_id,
                'file_path': audio_file_path,
                'start_time': self.current_file_start_time.isoformat() if self.current_file_start_time else None,
                'end_time': datetime.now().isoformat(),
                'file_size_bytes': self.current_file_size
            },
            'audio_config': {
                'codec': self.config.codec.value,
                'sample_rate': self.config.sample_rate,
                'channels': self.config.channels,
                'bit_depth': self.config.bit_depth,
                'file_format': self.config.file_format.value
            },
            'system_info': {
                'recorder_version': '1.0.0',
                'platform': os.name,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        # Write metadata file
        metadata_path = audio_file_path + '.metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.debug("Metadata file written", path=metadata_path)
    
    def get_current_file_info(self) -> Dict[str, Any]:
        """Get information about current recording file."""
        if not self.current_file:
            return {}
        
        duration_s = 0
        if self.current_file_start_time:
            duration_s = (datetime.now() - self.current_file_start_time).total_seconds()
        
        return {
            'file_path': self.current_file_path,
            'size_mb': self.current_file_size / (1024 * 1024),
            'duration_s': duration_s,
            'session_id': self.session_id
        }


class StreamingClient:
    """Streaming client for real-time audio distribution."""
    
    def __init__(self, config: StreamingConfig):
        self.config = config
        self.connected = False
        self.connection = None
        self.buffer = deque()
        self.buffer_size_ms = 0
        self.reconnect_count = 0
        self.last_reconnect_time = None
        
        # Statistics
        self.bytes_sent = 0
        self.frames_sent = 0
        self.connection_drops = 0
        
        logger.info("Streaming client initialized", 
                   protocol=config.protocol.value,
                   server=config.server_url)
    
    async def connect(self) -> bool:
        """Connect to streaming server."""
        try:
            logger.info("Connecting to streaming server", 
                       protocol=self.config.protocol.value,
                       server=self.config.server_url)
            
            # Placeholder connection logic
            # In production, would implement actual protocol connections
            if self.config.protocol == StreamingProtocol.RTMP:
                success = await self._connect_rtmp()
            elif self.config.protocol == StreamingProtocol.WEBRTC:
                success = await self._connect_webrtc()
            else:
                logger.warning("Unsupported streaming protocol", 
                             protocol=self.config.protocol.value)
                success = False
            
            if success:
                self.connected = True
                self.reconnect_count = 0
                logger.info("Successfully connected to streaming server")
            else:
                logger.error("Failed to connect to streaming server")
            
            return success
            
        except Exception as e:
            logger.error("Error connecting to streaming server", error=str(e))
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from streaming server."""
        if not self.connected:
            return
        
        try:
            # Close connection
            if self.connection:
                await self._close_connection()
            
            self.connected = False
            self.connection = None
            
            logger.info("Disconnected from streaming server")
            
        except Exception as e:
            logger.error("Error disconnecting from streaming server", error=str(e))
    
    async def send_audio_data(self, data: bytes, timestamp: datetime) -> bool:
        """Send audio data to streaming server."""
        if not self.connected:
            return False
        
        try:
            # Add to buffer
            self.buffer.append((data, timestamp))
            self.buffer_size_ms += len(data) / (self.config.sample_rate * self.config.channels * 2) * 1000
            
            # Manage buffer size
            while self.buffer_size_ms > self.config.max_buffer_size_ms:
                dropped_data, _ = self.buffer.popleft()
                self.buffer_size_ms -= len(dropped_data) / (self.config.sample_rate * self.config.channels * 2) * 1000
                self.connection_drops += 1
            
            # Send buffered data
            while self.buffer:
                data_to_send, send_timestamp = self.buffer.popleft()
                
                success = await self._send_data_packet(data_to_send, send_timestamp)
                if success:
                    self.bytes_sent += len(data_to_send)
                    self.frames_sent += 1
                    self.buffer_size_ms -= len(data_to_send) / (self.config.sample_rate * self.config.channels * 2) * 1000
                else:
                    # Re-add to buffer on failure
                    self.buffer.appendleft((data_to_send, send_timestamp))
                    break
            
            return True
            
        except Exception as e:
            logger.error("Error sending audio data", error=str(e))
            return False
    
    async def _connect_rtmp(self) -> bool:
        """Connect using RTMP protocol."""
        # Placeholder RTMP connection
        # In production, would use libraries like python-rtmp or ffmpeg
        await asyncio.sleep(0.1)  # Simulate connection time
        return True
    
    async def _connect_webrtc(self) -> bool:
        """Connect using WebRTC protocol."""
        # Placeholder WebRTC connection
        # In production, would use libraries like aiortc
        await asyncio.sleep(0.1)  # Simulate connection time
        return True
    
    async def _close_connection(self) -> None:
        """Close streaming connection."""
        # Placeholder connection cleanup
        pass
    
    async def _send_data_packet(self, data: bytes, timestamp: datetime) -> bool:
        """Send data packet to streaming server."""
        # Placeholder data sending
        # In production, would format and send according to protocol
        await asyncio.sleep(0.001)  # Simulate network latency
        return True
    
    async def reconnect(self) -> bool:
        """Attempt to reconnect to streaming server."""
        if self.reconnect_count >= self.config.reconnect_attempts:
            logger.error("Maximum reconnection attempts reached")
            return False
        
        # Check reconnection delay
        if self.last_reconnect_time:
            time_since_last = datetime.now() - self.last_reconnect_time
            if time_since_last.total_seconds() < self.config.reconnect_delay_s:
                return False
        
        self.reconnect_count += 1
        self.last_reconnect_time = datetime.now()
        
        logger.info("Attempting to reconnect", attempt=self.reconnect_count)
        
        # Disconnect first
        await self.disconnect()
        
        # Attempt reconnection
        return await self.connect()
    
    def get_streaming_stats(self) -> Dict[str, Any]:
        """Get streaming statistics."""
        return {
            'connected': self.connected,
            'bytes_sent': self.bytes_sent,
            'frames_sent': self.frames_sent,
            'buffer_size_ms': self.buffer_size_ms,
            'connection_drops': self.connection_drops,
            'reconnect_count': self.reconnect_count
        }


class RecorderService(BaseAudioProcessor):
    """
    Recording and Streaming Service for audio capture and distribution.
    
    Provides comprehensive recording capabilities with multiple codec support,
    real-time streaming, automatic file management, and audio-video synchronization.
    """
    
    def __init__(self, service_name: str, config: AudioConfig,
                 recording_config: Optional[RecordingConfig] = None,
                 streaming_config: Optional[StreamingConfig] = None,
                 metrics_collector: Optional[IMetricsCollector] = None):
        super().__init__(service_name, config, metrics_collector)
        
        # Configuration
        self.recording_config = recording_config or RecordingConfig()
        self.streaming_config = streaming_config
        
        # Core components
        self.encoder: Optional[AudioEncoder] = None
        self.file_writer: Optional[FileWriter] = None
        self.streaming_client: Optional[StreamingClient] = None
        
        # State management
        self.recording_active = False
        self.streaming_active = False
        self.recording_mode = RecordingMode.MANUAL
        
        # Performance metrics
        self.recorder_metrics = RecorderMetrics()
        
        # Frame synchronization
        self.frame_timestamps = deque(maxlen=1000)  # Keep last 1000 frame timestamps
        self.sync_reference_time = None
        
        # Background tasks
        self.recording_task: Optional[asyncio.Task] = None
        self.streaming_task: Optional[asyncio.Task] = None
        self.monitoring_task: Optional[asyncio.Task] = None
        
        logger.info(
            "Recorder Service initialized",
            service=service_name,
            recording_codec=self.recording_config.codec.value,
            streaming_enabled=streaming_config is not None
        )
    
    async def _initialize(self) -> None:
        """Initialize recorder service."""
        logger.info("Initializing Recorder Service", service=self.service_name)
        
        # Initialize encoder
        await self._initialize_encoder()
        
        # Initialize file writer
        if self.recording_config:
            self.file_writer = FileWriter(self.recording_config)
        
        # Initialize streaming client
        if self.streaming_config:
            self.streaming_client = StreamingClient(self.streaming_config)
        
        # Start monitoring task
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # Reset metrics
        self.recorder_metrics = RecorderMetrics()
        self.frame_timestamps.clear()
        self.sync_reference_time = datetime.now()
    
    async def _cleanup(self) -> None:
        """Cleanup recorder service."""
        logger.info("Cleaning up Recorder Service", service=self.service_name)
        
        # Stop recording and streaming
        await self.stop_recording()
        await self.stop_streaming()
        
        # Cancel monitoring task
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Cleanup encoder
        if self.encoder:
            await self.encoder.finalize()
        
        # Close file writer
        if self.file_writer:
            await self.file_writer.close_current_file()
        
        # Disconnect streaming client
        if self.streaming_client:
            await self.streaming_client.disconnect()
    
    async def _initialize_encoder(self) -> None:
        """Initialize audio encoder based on configuration."""
        codec = self.recording_config.codec
        
        if codec in [AudioCodec.PCM_16, AudioCodec.PCM_24, AudioCodec.PCM_32]:
            self.encoder = PCMEncoder()
        else:
            self.encoder = CompressedEncoder(codec)
        
        await self.encoder.initialize(self.recording_config)
        
        logger.info("Audio encoder initialized", 
                   codec=codec.value,
                   encoder_type=type(self.encoder).__name__)
    
    async def _process_frame(self, frame: AudioFrame) -> AudioFrame:
        """
        Process audio frame for recording and streaming.
        
        Args:
            frame: Input audio frame
            
        Returns:
            Original audio frame (pass-through)
        """
        # Record frame timestamp for synchronization
        self.frame_timestamps.append(frame.timestamp)
        
        # Update audio level metrics
        audio_level = frame.get_rms_level()
        self.recorder_metrics.audio_level_dbfs = audio_level
        
        peak_level = 20 * np.log10(np.max(np.abs(frame.data))) if np.max(np.abs(frame.data)) > 0 else -np.inf
        self.recorder_metrics.peak_level_dbfs = max(self.recorder_metrics.peak_level_dbfs, peak_level)
        
        # Process for recording
        if self.recording_active:
            await self._process_recording_frame(frame)
        
        # Process for streaming
        if self.streaming_active:
            await self._process_streaming_frame(frame)
        
        # Return original frame (recorder is a side-chain processor)
        return frame
    
    async def _process_recording_frame(self, frame: AudioFrame) -> None:
        """Process frame for recording."""
        try:
            start_time = time.time()
            
            # Encode audio frame
            encoded_data = await self.encoder.encode_frame(frame)
            
            encoding_time = (time.time() - start_time) * 1000
            self.recorder_metrics.encoding_latency_ms = encoding_time
            
            # Write to file
            if self.file_writer and encoded_data:
                write_start = time.time()
                write_time = await self.file_writer.write_data(encoded_data)
                
                if write_time:
                    self.recorder_metrics.disk_write_latency_ms = write_time
                
                # Update file metrics
                file_info = self.file_writer.get_current_file_info()
                self.recorder_metrics.current_file_size_mb = file_info.get('size_mb', 0)
                self.recorder_metrics.current_file_duration_s = file_info.get('duration_s', 0)
            
        except Exception as e:
            logger.error("Error processing recording frame", error=str(e))
    
    async def _process_streaming_frame(self, frame: AudioFrame) -> None:
        """Process frame for streaming."""
        try:
            if not self.streaming_client or not self.streaming_client.connected:
                return
            
            start_time = time.time()
            
            # Encode for streaming (may use different codec than recording)
            # For now, use the same encoder
            encoded_data = await self.encoder.encode_frame(frame)
            
            # Send to streaming client
            if encoded_data:
                success = await self.streaming_client.send_audio_data(encoded_data, frame.timestamp)
                
                network_time = (time.time() - start_time) * 1000
                self.recorder_metrics.network_latency_ms = network_time
                
                if not success:
                    self.recorder_metrics.stream_drops += 1
            
            # Update streaming metrics
            stream_stats = self.streaming_client.get_streaming_stats()
            self.recorder_metrics.stream_buffer_ms = stream_stats.get('buffer_size_ms', 0)
            
        except Exception as e:
            logger.error("Error processing streaming frame", error=str(e))
    
    async def start_recording(self, mode: RecordingMode = RecordingMode.MANUAL) -> bool:
        """
        Start audio recording.
        
        Args:
            mode: Recording mode (manual, continuous, triggered, scheduled)
            
        Returns:
            True if recording started successfully
        """
        if self.recording_active:
            logger.warning("Recording already active")
            return True
        
        try:
            logger.info("Starting recording", mode=mode.value)
            
            # Initialize file writer if needed
            if not self.file_writer:
                self.file_writer = FileWriter(self.recording_config)
            
            # Start new recording file
            file_path = await self.file_writer.start_new_file()
            
            # Update state
            self.recording_active = True
            self.recording_mode = mode
            self.recorder_metrics.recording_active = True
            
            logger.info("Recording started", file_path=file_path, mode=mode.value)
            return True
            
        except Exception as e:
            logger.error("Failed to start recording", error=str(e))
            return False
    
    async def stop_recording(self) -> Optional[str]:
        """
        Stop audio recording.
        
        Returns:
            Path to the recorded file, or None if no recording was active
        """
        if not self.recording_active:
            logger.warning("No recording active")
            return None
        
        try:
            logger.info("Stopping recording")
            
            # Finalize encoder
            if self.encoder:
                final_data = await self.encoder.finalize()
                if final_data and self.file_writer:
                    await self.file_writer.write_data(final_data)
            
            # Close current file
            file_path = None
            if self.file_writer:
                file_path = await self.file_writer.close_current_file()
                self.recorder_metrics.files_created += 1
            
            # Update state
            self.recording_active = False
            self.recorder_metrics.recording_active = False
            
            logger.info("Recording stopped", file_path=file_path)
            return file_path
            
        except Exception as e:
            logger.error("Error stopping recording", error=str(e))
            return None
    
    async def start_streaming(self) -> bool:
        """
        Start audio streaming.
        
        Returns:
            True if streaming started successfully
        """
        if not self.streaming_config:
            logger.error("No streaming configuration provided")
            return False
        
        if self.streaming_active:
            logger.warning("Streaming already active")
            return True
        
        try:
            logger.info("Starting streaming")
            
            # Initialize streaming client if needed
            if not self.streaming_client:
                self.streaming_client = StreamingClient(self.streaming_config)
            
            # Connect to streaming server
            connected = await self.streaming_client.connect()
            if not connected:
                logger.error("Failed to connect to streaming server")
                return False
            
            # Update state
            self.streaming_active = True
            self.recorder_metrics.streaming_active = True
            
            logger.info("Streaming started")
            return True
            
        except Exception as e:
            logger.error("Failed to start streaming", error=str(e))
            return False
    
    async def stop_streaming(self) -> None:
        """Stop audio streaming."""
        if not self.streaming_active:
            logger.warning("No streaming active")
            return
        
        try:
            logger.info("Stopping streaming")
            
            # Disconnect streaming client
            if self.streaming_client:
                await self.streaming_client.disconnect()
            
            # Update state
            self.streaming_active = False
            self.recorder_metrics.streaming_active = False
            
            logger.info("Streaming stopped")
            
        except Exception as e:
            logger.error("Error stopping streaming", error=str(e))
    
    async def _monitoring_loop(self) -> None:
        """Background monitoring loop for health checks and reconnections."""
        while self._is_running:
            try:
                # Check streaming connection health
                if self.streaming_active and self.streaming_client:
                    if not self.streaming_client.connected:
                        logger.warning("Streaming connection lost, attempting reconnection")
                        reconnected = await self.streaming_client.reconnect()
                        if reconnected:
                            self.recorder_metrics.stream_reconnects += 1
                        else:
                            logger.error("Failed to reconnect streaming client")
                
                # Update dynamic range calculation
                if len(self.frame_timestamps) > 10:
                    # Calculate dynamic range from recent audio levels
                    # This is a simplified calculation
                    self.recorder_metrics.dynamic_range_db = (
                        self.recorder_metrics.peak_level_dbfs - 
                        self.recorder_metrics.audio_level_dbfs
                    )
                
                # Storage management
                await self._manage_storage()
                
                await asyncio.sleep(5.0)  # Check every 5 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in monitoring loop", error=str(e))
                await asyncio.sleep(1.0)
    
    async def _manage_storage(self) -> None:
        """Manage storage space and cleanup old files."""
        if not self.recording_config.max_storage_gb:
            return
        
        try:
            # Check available storage
            output_dir = Path(self.recording_config.output_directory)
            if not output_dir.exists():
                return
            
            # Calculate total size of recordings
            total_size_gb = 0
            recording_files = []
            
            for file_path in output_dir.glob("*"):
                if file_path.is_file() and not file_path.name.endswith('.metadata.json'):
                    size_gb = file_path.stat().st_size / (1024**3)
                    total_size_gb += size_gb
                    recording_files.append((file_path, size_gb, file_path.stat().st_mtime))
            
            # Check if cleanup is needed
            if total_size_gb > self.recording_config.max_storage_gb:
                logger.info("Storage limit exceeded, cleaning up old files", 
                           total_size_gb=total_size_gb,
                           limit_gb=self.recording_config.max_storage_gb)
                
                # Sort files based on cleanup policy
                if self.recording_config.cleanup_policy == "oldest_first":
                    recording_files.sort(key=lambda x: x[2])  # Sort by modification time
                elif self.recording_config.cleanup_policy == "largest_first":
                    recording_files.sort(key=lambda x: x[1], reverse=True)  # Sort by size
                
                # Remove files until under limit
                for file_path, size_gb, _ in recording_files:
                    if total_size_gb <= self.recording_config.max_storage_gb:
                        break
                    
                    try:
                        file_path.unlink()  # Delete file
                        
                        # Also delete metadata file if exists
                        metadata_path = file_path.with_suffix(file_path.suffix + '.metadata.json')
                        if metadata_path.exists():
                            metadata_path.unlink()
                        
                        total_size_gb -= size_gb
                        logger.info("Deleted old recording file", 
                                   file_path=str(file_path),
                                   size_gb=size_gb)
                        
                    except Exception as e:
                        logger.error("Error deleting file", 
                                   file_path=str(file_path),
                                   error=str(e))
            
            # Update total recorded size metric
            self.recorder_metrics.total_recorded_mb = total_size_gb * 1024
            
        except Exception as e:
            logger.error("Error in storage management", error=str(e))
    
    def get_recording_status(self) -> Dict[str, Any]:
        """Get current recording status."""
        status = {
            'recording_active': self.recording_active,
            'streaming_active': self.streaming_active,
            'recording_mode': self.recording_mode.value if self.recording_mode else None,
            'current_file': None,
            'streaming_connected': False
        }
        
        if self.file_writer:
            status['current_file'] = self.file_writer.get_current_file_info()
        
        if self.streaming_client:
            status['streaming_connected'] = self.streaming_client.connected
            status['streaming_stats'] = self.streaming_client.get_streaming_stats()
        
        return status
    
    def get_recorder_metrics(self) -> Dict[str, Any]:
        """Get recorder-specific metrics."""
        return self.recorder_metrics.to_dict()
    
    def get_sync_info(self) -> Dict[str, Any]:
        """Get audio-video synchronization information."""
        if not self.frame_timestamps:
            return {}
        
        # Calculate frame timing statistics
        timestamps = list(self.frame_timestamps)
        if len(timestamps) < 2:
            return {}
        
        # Calculate frame intervals
        intervals = []
        for i in range(1, len(timestamps)):
            interval = (timestamps[i] - timestamps[i-1]).total_seconds() * 1000  # ms
            intervals.append(interval)
        
        avg_interval = sum(intervals) / len(intervals)
        expected_interval = (self._audio_config.frame_size / self._audio_config.sample_rate) * 1000
        
        return {
            'frame_count': len(timestamps),
            'avg_frame_interval_ms': avg_interval,
            'expected_frame_interval_ms': expected_interval,
            'timing_accuracy_ms': abs(avg_interval - expected_interval),
            'sync_reference_time': self.sync_reference_time.isoformat() if self.sync_reference_time else None,
            'latest_frame_time': timestamps[-1].isoformat() if timestamps else None
        }
    
    async def update_recording_config(self, config: RecordingConfig) -> None:
        """Update recording configuration."""
        old_config = self.recording_config
        self.recording_config = config
        
        # Reinitialize encoder if codec changed
        if old_config.codec != config.codec:
            await self._initialize_encoder()
        
        # Update file writer if needed
        if self.file_writer:
            self.file_writer.config = config
        
        logger.info("Recording configuration updated", 
                   old_codec=old_config.codec.value,
                   new_codec=config.codec.value)
    
    async def update_streaming_config(self, config: StreamingConfig) -> None:
        """Update streaming configuration."""
        was_streaming = self.streaming_active
        
        # Stop streaming if active
        if was_streaming:
            await self.stop_streaming()
        
        # Update configuration
        self.streaming_config = config
        self.streaming_client = StreamingClient(config)
        
        # Restart streaming if it was active
        if was_streaming:
            await self.start_streaming()
        
        logger.info("Streaming configuration updated", 
                   protocol=config.protocol.value,
                   server=config.server_url)
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Get configuration schema for recorder service."""
        return {
            "type": "object",
            "properties": {
                "recording": {
                    "type": "object",
                    "properties": {
                        "codec": {
                            "type": "string",
                            "enum": [codec.value for codec in AudioCodec],
                            "description": "Audio codec for recording"
                        },
                        "file_format": {
                            "type": "string",
                            "enum": [fmt.value for fmt in FileFormat],
                            "description": "Output file format"
                        },
                        "sample_rate": {
                            "type": "integer",
                            "enum": [44100, 48000, 96000],
                            "description": "Recording sample rate"
                        },
                        "channels": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 8,
                            "description": "Number of recording channels"
                        },
                        "bit_depth": {
                            "type": "integer",
                            "enum": [16, 24, 32],
                            "description": "Audio bit depth"
                        },
                        "max_file_size_mb": {
                            "type": "integer",
                            "minimum": 10,
                            "maximum": 10000,
                            "description": "Maximum file size in MB"
                        },
                        "auto_segment": {
                            "type": "boolean",
                            "description": "Enable automatic file segmentation"
                        }
                    }
                },
                "streaming": {
                    "type": "object",
                    "properties": {
                        "protocol": {
                            "type": "string",
                            "enum": [proto.value for proto in StreamingProtocol],
                            "description": "Streaming protocol"
                        },
                        "server_url": {
                            "type": "string",
                            "description": "Streaming server URL"
                        },
                        "bitrate_kbps": {
                            "type": "integer",
                            "minimum": 32,
                            "maximum": 320,
                            "description": "Streaming bitrate in kbps"
                        },
                        "buffer_size_ms": {
                            "type": "integer",
                            "minimum": 100,
                            "maximum": 2000,
                            "description": "Streaming buffer size in ms"
                        }
                    }
                }
            },
            "required": []
        }