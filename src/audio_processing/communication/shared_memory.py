"""
Shared memory management for high-performance audio frame transmission.

This module provides optimized shared memory mechanisms for transferring
large audio data between processes with minimal copying overhead.
"""

import mmap
import struct
import time
from dataclasses import dataclass
from typing import Dict, Any, Optional
from enum import Enum
import threading
import multiprocessing
import numpy as np
import structlog

from ..models import AudioFrame

logger = structlog.get_logger(__name__)


class BufferState(Enum):
    """Shared buffer states."""
    FREE = 0
    WRITING = 1
    READY = 2
    READING = 3
    ERROR = 4


@dataclass
class BufferHeader:
    """
    Header structure for shared memory buffers.
    
    Contains metadata about the audio frame stored in the buffer.
    """
    state: int = BufferState.FREE.value
    timestamp_ns: int = 0  # Nanosecond timestamp
    sample_rate: int = 0
    channels: int = 0
    frame_size: int = 0
    data_size: int = 0  # Size of audio data in bytes
    sequence_number: int = 0
    producer_id: int = 0
    consumer_count: int = 0
    checksum: int = 0  # Simple checksum for data integrity
    
    # Padding to align to cache line (64 bytes)
    _padding: bytes = b'\x00' * 16
    
    @classmethod
    def size(cls) -> int:
        """Get the size of the header in bytes."""
        return 64  # Fixed size for cache alignment
    
    def pack(self) -> bytes:
        """Pack header into bytes."""
        # Pack the 10 integers first (40 bytes)
        packed_ints = struct.pack(
            '=10I',  # 10 unsigned ints
            self.state & 0xFFFFFFFF,
            self.timestamp_ns & 0xFFFFFFFF,
            self.sample_rate & 0xFFFFFFFF,
            self.channels & 0xFFFFFFFF,
            self.frame_size & 0xFFFFFFFF,
            self.data_size & 0xFFFFFFFF,
            self.sequence_number & 0xFFFFFFFF,
            self.producer_id & 0xFFFFFFFF,
            self.consumer_count & 0xFFFFFFFF,
            self.checksum & 0xFFFFFFFF
        )
        # Add padding to reach 64 bytes total
        padding = b'\x00' * (64 - len(packed_ints))
        return packed_ints + padding
    
    @classmethod
    def unpack(cls, data: bytes) -> 'BufferHeader':
        """Unpack header from bytes."""
        # Unpack only the first 40 bytes (10 integers)
        values = struct.unpack('=10I', data[:40])
        return cls(
            state=values[0],
            timestamp_ns=values[1],
            sample_rate=values[2],
            channels=values[3],
            frame_size=values[4],
            data_size=values[5],
            sequence_number=values[6],
            producer_id=values[7],
            consumer_count=values[8],
            checksum=values[9]
        )


class AudioFrameBuffer:
    """
    High-performance shared memory buffer for audio frames.
    
    Provides lock-free access patterns optimized for single producer,
    multiple consumer scenarios common in audio processing pipelines.
    """
    
    def __init__(self, buffer_id: str, max_frame_size: int = 8192,
                 max_channels: int = 32, buffer_count: int = 16):
        self.buffer_id = buffer_id
        self.max_frame_size = max_frame_size
        self.max_channels = max_channels
        self.buffer_count = buffer_count
        
        # Calculate buffer sizes
        self.header_size = BufferHeader.size()
        self.audio_data_size = max_frame_size * max_channels * 4  # 32-bit float
        self.single_buffer_size = self.header_size + self.audio_data_size
        self.total_size = self.single_buffer_size * buffer_count
        
        # Shared memory objects
        self._shm: Optional[mmap.mmap] = None
        self._lock = threading.RLock()
        
        # Buffer management
        self._current_write_index = 0
        self._sequence_counter = 0
        self._producer_id = multiprocessing.current_process().pid
        
        # Statistics
        self._frames_written = 0
        self._frames_read = 0
        self._buffer_overruns = 0
        self._checksum_errors = 0
    
    def create(self) -> bool:
        """
        Create the shared memory buffer.
        
        Returns:
            True if creation successful, False otherwise
        """
        try:
            # Create memory-mapped file
            self._shm = mmap.mmap(-1, self.total_size, access=mmap.ACCESS_WRITE)
            
            # Initialize all buffer headers
            for i in range(self.buffer_count):
                offset = i * self.single_buffer_size
                header = BufferHeader()
                self._shm[offset:offset + self.header_size] = header.pack()
            
            logger.info(
                "Shared memory buffer created",
                buffer_id=self.buffer_id,
                total_size=self.total_size,
                buffer_count=self.buffer_count
            )
            return True
            
        except Exception as e:
            logger.error("Failed to create shared memory buffer", error=str(e))
            return False
    
    def attach(self) -> bool:
        """
        Attach to existing shared memory buffer.
        
        Returns:
            True if attachment successful, False otherwise
        """
        # For mmap, attach is the same as create in this implementation
        # In a real implementation, this would connect to existing shared memory
        return self.create()
    
    def detach(self) -> None:
        """Detach from shared memory buffer."""
        if self._shm:
            self._shm.close()
            self._shm = None
            logger.info("Detached from shared memory buffer", buffer_id=self.buffer_id)
    
    def write_frame(self, frame: AudioFrame) -> bool:
        """
        Write an audio frame to the shared buffer.
        
        Args:
            frame: Audio frame to write
            
        Returns:
            True if write successful, False otherwise
        """
        if not self._shm:
            return False
        
        # Validate frame size
        if (frame.channels > self.max_channels or 
            frame.frame_size > self.max_frame_size):
            logger.warning(
                "Frame too large for buffer",
                channels=frame.channels,
                frame_size=frame.frame_size,
                max_channels=self.max_channels,
                max_frame_size=self.max_frame_size
            )
            return False
        
        with self._lock:
            # Find next available buffer
            buffer_index = self._find_free_buffer()
            if buffer_index is None:
                self._buffer_overruns += 1
                logger.warning("No free buffers available", buffer_id=self.buffer_id)
                return False
            
            try:
                # Calculate buffer offset
                buffer_offset = buffer_index * self.single_buffer_size
                header_offset = buffer_offset
                data_offset = buffer_offset + self.header_size
                
                # Mark buffer as being written
                self._set_buffer_state(buffer_index, BufferState.WRITING)
                
                # Prepare audio data
                audio_data = frame.data.astype(np.float32)
                audio_bytes = audio_data.tobytes()
                
                # Calculate checksum
                checksum = self._calculate_checksum(audio_bytes)
                
                # Create header (use relative timestamp to avoid overflow)
                timestamp_ns = int((frame.timestamp.timestamp() % 1000) * 1e9) & 0xFFFFFFFF  # Ensure 32-bit range
                header = BufferHeader(
                    state=BufferState.WRITING.value,
                    timestamp_ns=timestamp_ns,
                    sample_rate=frame.sample_rate,
                    channels=frame.channels,
                    frame_size=frame.frame_size,
                    data_size=len(audio_bytes),
                    sequence_number=self._sequence_counter,
                    producer_id=self._producer_id,
                    consumer_count=0,
                    checksum=checksum
                )
                
                # Write audio data first
                self._shm[data_offset:data_offset + len(audio_bytes)] = audio_bytes
                
                # Write header last and mark as ready (atomic operation)
                header.state = BufferState.READY.value
                self._shm[header_offset:header_offset + self.header_size] = header.pack()
                
                # Update counters
                self._sequence_counter += 1
                self._frames_written += 1
                
                logger.debug(
                    "Frame written to shared buffer",
                    buffer_index=buffer_index,
                    sequence=self._sequence_counter - 1,
                    frame_size=frame.frame_size
                )
                
                return True
                
            except Exception as e:
                # Mark buffer as error state
                self._set_buffer_state(buffer_index, BufferState.ERROR)
                logger.error("Error writing frame to buffer", error=str(e))
                return False
    
    def read_frame(self, timeout_ms: float = 10.0) -> Optional[AudioFrame]:
        """
        Read an audio frame from the shared buffer.
        
        Args:
            timeout_ms: Maximum time to wait for frame
            
        Returns:
            Audio frame or None if no frame available
        """
        if not self._shm:
            return None
        
        start_time = time.time()
        timeout_seconds = timeout_ms / 1000.0
        
        while (time.time() - start_time) < timeout_seconds:
            # Find buffer with ready data
            buffer_index = self._find_ready_buffer()
            if buffer_index is None:
                time.sleep(0.001)  # Brief sleep before retry
                continue
            
            try:
                # Read frame from buffer
                frame = self._read_frame_from_buffer(buffer_index)
                if frame:
                    self._frames_read += 1
                    return frame
                
            except Exception as e:
                logger.error("Error reading frame from buffer", error=str(e))
                self._set_buffer_state(buffer_index, BufferState.ERROR)
            
            time.sleep(0.001)
        
        return None
    
    def _find_free_buffer(self) -> Optional[int]:
        """Find a free buffer for writing."""
        # Start from current write index and search circularly
        for i in range(self.buffer_count):
            buffer_index = (self._current_write_index + i) % self.buffer_count
            state = self._get_buffer_state(buffer_index)
            
            if state in [BufferState.FREE, BufferState.ERROR]:
                self._current_write_index = (buffer_index + 1) % self.buffer_count
                return buffer_index
        
        return None
    
    def _find_ready_buffer(self) -> Optional[int]:
        """Find a buffer with ready data for reading."""
        latest_sequence = -1
        latest_buffer = None
        
        # Find buffer with latest sequence number
        for i in range(self.buffer_count):
            state = self._get_buffer_state(i)
            if state == BufferState.READY:
                header = self._read_buffer_header(i)
                if header and header.sequence_number > latest_sequence:
                    latest_sequence = header.sequence_number
                    latest_buffer = i
        
        return latest_buffer
    
    def _get_buffer_state(self, buffer_index: int) -> BufferState:
        """Get the state of a specific buffer."""
        offset = buffer_index * self.single_buffer_size
        state_bytes = self._shm[offset:offset + 4]
        state_value = struct.unpack('=I', state_bytes)[0]
        return BufferState(state_value)
    
    def _set_buffer_state(self, buffer_index: int, state: BufferState) -> None:
        """Set the state of a specific buffer."""
        offset = buffer_index * self.single_buffer_size
        state_bytes = struct.pack('=I', state.value)
        self._shm[offset:offset + 4] = state_bytes
    
    def _read_buffer_header(self, buffer_index: int) -> Optional[BufferHeader]:
        """Read header from a specific buffer."""
        try:
            offset = buffer_index * self.single_buffer_size
            header_bytes = self._shm[offset:offset + self.header_size]
            return BufferHeader.unpack(header_bytes)
        except Exception as e:
            logger.error("Error reading buffer header", error=str(e))
            return None
    
    def _read_frame_from_buffer(self, buffer_index: int) -> Optional[AudioFrame]:
        """Read complete audio frame from buffer."""
        # Mark buffer as being read
        self._set_buffer_state(buffer_index, BufferState.READING)
        
        try:
            # Read header
            header = self._read_buffer_header(buffer_index)
            if not header:
                return None
            
            # Read audio data
            buffer_offset = buffer_index * self.single_buffer_size
            data_offset = buffer_offset + self.header_size
            audio_bytes = self._shm[data_offset:data_offset + header.data_size]
            
            # Verify checksum
            if self._calculate_checksum(audio_bytes) != header.checksum:
                self._checksum_errors += 1
                logger.warning("Checksum mismatch in buffer", buffer_index=buffer_index)
                self._set_buffer_state(buffer_index, BufferState.ERROR)
                return None
            
            # Convert bytes back to numpy array
            audio_data = np.frombuffer(audio_bytes, dtype=np.float32)
            audio_data = audio_data.reshape((header.channels, header.frame_size))
            
            # Create AudioFrame (reconstruct approximate timestamp)
            from datetime import datetime
            # Use current time as base since we used modulo during write
            current_time = time.time()
            base_time = int(current_time / 1000) * 1000  # Round to nearest 1000 seconds
            timestamp = datetime.fromtimestamp(base_time + (header.timestamp_ns / 1e9))
            
            frame = AudioFrame(
                timestamp=timestamp,
                sample_rate=header.sample_rate,
                channels=header.channels,
                frame_size=header.frame_size,
                data=audio_data,
                metadata={
                    'sequence_number': header.sequence_number,
                    'producer_id': header.producer_id,
                    'buffer_index': buffer_index
                }
            )
            
            # Mark buffer as free
            self._set_buffer_state(buffer_index, BufferState.FREE)
            
            return frame
            
        except Exception as e:
            logger.error("Error reading frame from buffer", error=str(e))
            self._set_buffer_state(buffer_index, BufferState.ERROR)
            return None
    
    def _calculate_checksum(self, data: bytes) -> int:
        """Calculate simple checksum for data integrity."""
        return sum(data) & 0xFFFFFFFF
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get buffer statistics."""
        buffer_states = {}
        for i in range(self.buffer_count):
            state = self._get_buffer_state(i)
            state_name = state.name
            buffer_states[state_name] = buffer_states.get(state_name, 0) + 1
        
        return {
            'buffer_id': self.buffer_id,
            'frames_written': self._frames_written,
            'frames_read': self._frames_read,
            'buffer_overruns': self._buffer_overruns,
            'checksum_errors': self._checksum_errors,
            'buffer_count': self.buffer_count,
            'buffer_states': buffer_states,
            'utilization_percent': (
                buffer_states.get('READY', 0) + buffer_states.get('READING', 0)
            ) / self.buffer_count * 100
        }


class SharedMemoryManager:
    """
    Manager for multiple shared memory buffers.
    
    Provides centralized management of shared memory resources
    for audio processing pipelines.
    """
    
    def __init__(self, manager_name: str):
        self.manager_name = manager_name
        self._buffers: Dict[str, AudioFrameBuffer] = {}
        self._lock = threading.RLock()
    
    def create_buffer(self, buffer_id: str, max_frame_size: int = 8192,
                     max_channels: int = 32, buffer_count: int = 16) -> bool:
        """
        Create a new shared memory buffer.
        
        Args:
            buffer_id: Unique identifier for the buffer
            max_frame_size: Maximum frame size in samples
            max_channels: Maximum number of channels
            buffer_count: Number of buffers in the ring
            
        Returns:
            True if creation successful
        """
        with self._lock:
            if buffer_id in self._buffers:
                logger.warning("Buffer already exists", buffer_id=buffer_id)
                return False
            
            buffer = AudioFrameBuffer(
                buffer_id=buffer_id,
                max_frame_size=max_frame_size,
                max_channels=max_channels,
                buffer_count=buffer_count
            )
            
            if buffer.create():
                self._buffers[buffer_id] = buffer
                logger.info("Shared memory buffer created", buffer_id=buffer_id)
                return True
            
            return False
    
    def get_buffer(self, buffer_id: str) -> Optional[AudioFrameBuffer]:
        """
        Get a shared memory buffer by ID.
        
        Args:
            buffer_id: Buffer identifier
            
        Returns:
            AudioFrameBuffer or None if not found
        """
        with self._lock:
            return self._buffers.get(buffer_id)
    
    def remove_buffer(self, buffer_id: str) -> bool:
        """
        Remove a shared memory buffer.
        
        Args:
            buffer_id: Buffer identifier
            
        Returns:
            True if removal successful
        """
        with self._lock:
            if buffer_id not in self._buffers:
                return False
            
            buffer = self._buffers[buffer_id]
            buffer.detach()
            del self._buffers[buffer_id]
            
            logger.info("Shared memory buffer removed", buffer_id=buffer_id)
            return True
    
    def cleanup(self) -> None:
        """Clean up all shared memory buffers."""
        with self._lock:
            for buffer_id in list(self._buffers.keys()):
                self.remove_buffer(buffer_id)
            
            logger.info("All shared memory buffers cleaned up")
    
    def get_manager_statistics(self) -> Dict[str, Any]:
        """Get statistics for all managed buffers."""
        with self._lock:
            buffer_stats = {}
            total_frames_written = 0
            total_frames_read = 0
            
            for buffer_id, buffer in self._buffers.items():
                stats = buffer.get_statistics()
                buffer_stats[buffer_id] = stats
                total_frames_written += stats['frames_written']
                total_frames_read += stats['frames_read']
            
            return {
                'manager_name': self.manager_name,
                'buffer_count': len(self._buffers),
                'total_frames_written': total_frames_written,
                'total_frames_read': total_frames_read,
                'buffer_statistics': buffer_stats
            }


# Utility functions
def create_audio_buffer_pool(pool_name: str, buffer_count: int = 4,
                           max_frame_size: int = 8192, max_channels: int = 32) -> SharedMemoryManager:
    """
    Create a pool of shared memory buffers for audio processing.
    
    Args:
        pool_name: Name for the buffer pool
        buffer_count: Number of buffers to create
        max_frame_size: Maximum frame size for each buffer
        max_channels: Maximum channels for each buffer
        
    Returns:
        Configured SharedMemoryManager
    """
    manager = SharedMemoryManager(pool_name)
    
    for i in range(buffer_count):
        buffer_id = f"{pool_name}_buffer_{i}"
        manager.create_buffer(
            buffer_id=buffer_id,
            max_frame_size=max_frame_size,
            max_channels=max_channels,
            buffer_count=16
        )
    
    logger.info("Audio buffer pool created", 
               pool_name=pool_name, 
               buffer_count=buffer_count)
    
    return manager