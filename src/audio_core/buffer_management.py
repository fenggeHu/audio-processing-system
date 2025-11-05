"""
High-Performance Buffer Management System

This module implements a high-performance circular buffer system with overflow/underflow
detection, dynamic sizing, and thread-safe access for real-time audio processing.

Implements requirements: 4.1, 4.4, 5.1, 5.2, 5.4
"""

import threading
import time
import logging
from typing import Optional, Any, List, Callable, Dict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import numpy as np

from .models import AudioFrame


class BufferState(Enum):
    """Buffer state enumeration"""
    EMPTY = "empty"
    NORMAL = "normal"
    NEARLY_FULL = "nearly_full"
    FULL = "full"
    OVERFLOW = "overflow"
    UNDERFLOW = "underflow"
    ERROR = "error"


class BufferEvent(Enum):
    """Buffer event types"""
    OVERFLOW_DETECTED = "overflow_detected"
    UNDERFLOW_DETECTED = "underflow_detected"
    THRESHOLD_REACHED = "threshold_reached"
    SIZE_CHANGED = "size_changed"
    ERROR_OCCURRED = "error_occurred"


@dataclass
class BufferStatistics:
    """Buffer performance statistics"""
    total_writes: int = 0
    total_reads: int = 0
    overflow_count: int = 0
    underflow_count: int = 0
    resize_count: int = 0
    
    # Performance metrics
    average_fill_level: float = 0.0
    peak_fill_level: float = 0.0
    average_write_time_us: float = 0.0
    average_read_time_us: float = 0.0
    
    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    last_reset: datetime = field(default_factory=datetime.now)
    
    def reset(self):
        """Reset statistics"""
        self.total_writes = 0
        self.total_reads = 0
        self.overflow_count = 0
        self.underflow_count = 0
        self.resize_count = 0
        self.average_fill_level = 0.0
        self.peak_fill_level = 0.0
        self.average_write_time_us = 0.0
        self.average_read_time_us = 0.0
        self.last_reset = datetime.now()


class CircularBuffer:
    """
    High-performance circular buffer with thread-safe access and dynamic sizing
    """
    
    def __init__(self, initial_size: int = 1024, max_size: int = 8192, element_type: type = AudioFrame):
        self.logger = logging.getLogger(__name__ + ".CircularBuffer")
        
        # Buffer configuration
        self._initial_size = initial_size
        self._max_size = max_size
        self._element_type = element_type
        
        # Buffer storage
        self._buffer: List[Optional[Any]] = [None] * initial_size
        self._capacity = initial_size
        self._size = 0
        self._head = 0  # Write position
        self._tail = 0  # Read position
        
        # Thread safety
        self._lock = threading.RLock()
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)
        
        # State tracking
        self._state = BufferState.EMPTY
        self._statistics = BufferStatistics()
        
        # Event callbacks
        self._event_callbacks: Dict[BufferEvent, List[Callable[[BufferEvent, Dict[str, Any]], None]]] = {
            event: [] for event in BufferEvent
        }
        
        # Thresholds
        self._overflow_threshold = 0.9  # 90% full
        self._underflow_threshold = 0.1  # 10% full
        self._resize_threshold_high = 0.8  # 80% full - consider growing
        self._resize_threshold_low = 0.3   # 30% full - consider shrinking
        
        # Dynamic sizing
        self._auto_resize_enabled = True
        self._resize_factor = 1.5
        self._min_resize_interval = timedelta(seconds=1)
        self._last_resize_time = datetime.now()
    
    def write(self, item: Any, timeout: Optional[float] = None) -> bool:
        """Write item to buffer with optional timeout"""
        start_time = time.perf_counter()
        
        try:
            with self._not_full:
                # Wait for space if buffer is full
                if timeout is not None:
                    end_time = time.time() + timeout
                    while self._size >= self._capacity:
                        remaining = end_time - time.time()
                        if remaining <= 0:
                            return False
                        if not self._not_full.wait(remaining):
                            return False
                else:
                    while self._size >= self._capacity:
                        self._not_full.wait()
                
                # Write item
                self._buffer[self._head] = item
                self._head = (self._head + 1) % self._capacity
                self._size += 1
                
                # Update statistics
                self._statistics.total_writes += 1
                write_time = (time.perf_counter() - start_time) * 1_000_000  # microseconds
                self._update_average_write_time(write_time)
                
                # Update state and check thresholds
                self._update_state()
                self._check_thresholds()
                
                # Notify readers
                self._not_empty.notify()
                
                return True
                
        except Exception as e:
            self.logger.error(f"Error writing to buffer: {e}")
            self._notify_event(BufferEvent.ERROR_OCCURRED, {"error": str(e)})
            return False
    
    def read(self, timeout: Optional[float] = None) -> Optional[Any]:
        """Read item from buffer with optional timeout"""
        start_time = time.perf_counter()
        
        try:
            with self._not_empty:
                # Wait for data if buffer is empty
                if timeout is not None:
                    end_time = time.time() + timeout
                    while self._size == 0:
                        remaining = end_time - time.time()
                        if remaining <= 0:
                            return None
                        if not self._not_empty.wait(remaining):
                            return None
                else:
                    while self._size == 0:
                        self._not_empty.wait()
                
                # Read item
                item = self._buffer[self._tail]
                self._buffer[self._tail] = None  # Clear reference
                self._tail = (self._tail + 1) % self._capacity
                self._size -= 1
                
                # Update statistics
                self._statistics.total_reads += 1
                read_time = (time.perf_counter() - start_time) * 1_000_000  # microseconds
                self._update_average_read_time(read_time)
                
                # Update state and check thresholds
                self._update_state()
                self._check_thresholds()
                
                # Notify writers
                self._not_full.notify()
                
                return item
                
        except Exception as e:
            self.logger.error(f"Error reading from buffer: {e}")
            self._notify_event(BufferEvent.ERROR_OCCURRED, {"error": str(e)})
            return None
    
    def try_write(self, item: Any) -> bool:
        """Try to write item without blocking"""
        return self.write(item, timeout=0)
    
    def try_read(self) -> Optional[Any]:
        """Try to read item without blocking"""
        return self.read(timeout=0)
    
    def peek(self) -> Optional[Any]:
        """Peek at next item without removing it"""
        with self._lock:
            if self._size == 0:
                return None
            return self._buffer[self._tail]
    
    def clear(self):
        """Clear all items from buffer"""
        with self._lock:
            for i in range(self._capacity):
                self._buffer[i] = None
            self._size = 0
            self._head = 0
            self._tail = 0
            self._state = BufferState.EMPTY
            
            # Notify all waiting threads
            self._not_full.notify_all()
    
    def resize(self, new_size: int) -> bool:
        """Resize buffer to new capacity"""
        if new_size < self._size or new_size > self._max_size:
            return False
        
        try:
            with self._lock:
                # Create new buffer
                new_buffer = [None] * new_size
                
                # Copy existing data
                for i in range(self._size):
                    src_index = (self._tail + i) % self._capacity
                    new_buffer[i] = self._buffer[src_index]
                
                # Update buffer
                self._buffer = new_buffer
                self._capacity = new_size
                self._head = self._size
                self._tail = 0
                
                # Update statistics
                self._statistics.resize_count += 1
                self._last_resize_time = datetime.now()
                
                self.logger.debug(f"Buffer resized to {new_size}")
                self._notify_event(BufferEvent.SIZE_CHANGED, {"new_size": new_size, "old_size": len(self._buffer)})
                
                # Notify waiting threads
                self._not_full.notify_all()
                
                return True
                
        except Exception as e:
            self.logger.error(f"Error resizing buffer: {e}")
            return False
    
    def get_size(self) -> int:
        """Get current number of items in buffer"""
        with self._lock:
            return self._size
    
    def get_capacity(self) -> int:
        """Get buffer capacity"""
        with self._lock:
            return self._capacity
    
    def get_fill_level(self) -> float:
        """Get fill level as percentage (0.0 to 1.0)"""
        with self._lock:
            return self._size / self._capacity if self._capacity > 0 else 0.0
    
    def is_empty(self) -> bool:
        """Check if buffer is empty"""
        with self._lock:
            return self._size == 0
    
    def is_full(self) -> bool:
        """Check if buffer is full"""
        with self._lock:
            return self._size >= self._capacity
    
    def get_state(self) -> BufferState:
        """Get current buffer state"""
        with self._lock:
            return self._state
    
    def get_statistics(self) -> BufferStatistics:
        """Get buffer statistics"""
        with self._lock:
            # Update average fill level
            current_fill = self.get_fill_level()
            if self._statistics.total_writes > 0:
                self._statistics.average_fill_level = (
                    (self._statistics.average_fill_level * (self._statistics.total_writes - 1) + current_fill) /
                    self._statistics.total_writes
                )
            self._statistics.peak_fill_level = max(self._statistics.peak_fill_level, current_fill)
            
            return self._statistics
    
    def reset_statistics(self):
        """Reset buffer statistics"""
        with self._lock:
            self._statistics.reset()
    
    def register_event_callback(self, event: BufferEvent, callback: Callable[[BufferEvent, Dict[str, Any]], None]):
        """Register callback for buffer events"""
        self._event_callbacks[event].append(callback)
    
    def unregister_event_callback(self, event: BufferEvent, callback: Callable[[BufferEvent, Dict[str, Any]], None]):
        """Unregister event callback"""
        if callback in self._event_callbacks[event]:
            self._event_callbacks[event].remove(callback)
    
    def enable_auto_resize(self, enabled: bool):
        """Enable or disable automatic resizing"""
        with self._lock:
            self._auto_resize_enabled = enabled
    
    def set_thresholds(self, overflow: float = None, underflow: float = None, 
                      resize_high: float = None, resize_low: float = None):
        """Set buffer thresholds"""
        with self._lock:
            if overflow is not None:
                self._overflow_threshold = max(0.0, min(1.0, overflow))
            if underflow is not None:
                self._underflow_threshold = max(0.0, min(1.0, underflow))
            if resize_high is not None:
                self._resize_threshold_high = max(0.0, min(1.0, resize_high))
            if resize_low is not None:
                self._resize_threshold_low = max(0.0, min(1.0, resize_low))
    
    def _update_state(self):
        """Update buffer state based on current fill level"""
        fill_level = self.get_fill_level()
        
        if fill_level == 0.0:
            self._state = BufferState.EMPTY
        elif fill_level >= 1.0:
            self._state = BufferState.FULL
        elif fill_level >= self._overflow_threshold:
            self._state = BufferState.NEARLY_FULL
        else:
            self._state = BufferState.NORMAL
    
    def _check_thresholds(self):
        """Check thresholds and trigger events"""
        fill_level = self.get_fill_level()
        
        # Check overflow
        if fill_level >= self._overflow_threshold:
            self._statistics.overflow_count += 1
            self._notify_event(BufferEvent.OVERFLOW_DETECTED, {"fill_level": fill_level})
        
        # Check underflow
        if fill_level <= self._underflow_threshold and self._size > 0:
            self._statistics.underflow_count += 1
            self._notify_event(BufferEvent.UNDERFLOW_DETECTED, {"fill_level": fill_level})
        
        # Check auto-resize
        if self._auto_resize_enabled:
            self._check_auto_resize(fill_level)
    
    def _check_auto_resize(self, fill_level: float):
        """Check if buffer should be automatically resized"""
        now = datetime.now()
        if (now - self._last_resize_time) < self._min_resize_interval:
            return
        
        # Consider growing
        if fill_level >= self._resize_threshold_high and self._capacity < self._max_size:
            new_size = min(int(self._capacity * self._resize_factor), self._max_size)
            if new_size > self._capacity:
                self.resize(new_size)
        
        # Consider shrinking
        elif fill_level <= self._resize_threshold_low and self._capacity > self._initial_size:
            new_size = max(int(self._capacity / self._resize_factor), self._initial_size)
            if new_size < self._capacity and new_size >= self._size:
                self.resize(new_size)
    
    def _update_average_write_time(self, write_time_us: float):
        """Update average write time"""
        if self._statistics.total_writes == 1:
            self._statistics.average_write_time_us = write_time_us
        else:
            self._statistics.average_write_time_us = (
                (self._statistics.average_write_time_us * (self._statistics.total_writes - 1) + write_time_us) /
                self._statistics.total_writes
            )
    
    def _update_average_read_time(self, read_time_us: float):
        """Update average read time"""
        if self._statistics.total_reads == 1:
            self._statistics.average_read_time_us = read_time_us
        else:
            self._statistics.average_read_time_us = (
                (self._statistics.average_read_time_us * (self._statistics.total_reads - 1) + read_time_us) /
                self._statistics.total_reads
            )
    
    def _notify_event(self, event: BufferEvent, data: Dict[str, Any]):
        """Notify event callbacks"""
        for callback in self._event_callbacks[event]:
            try:
                callback(event, data)
            except Exception as e:
                self.logger.error(f"Error in event callback: {e}")


class BufferPool:
    """
    Pool of circular buffers for efficient memory management
    """
    
    def __init__(self, pool_size: int = 10, buffer_size: int = 1024):
        self.logger = logging.getLogger(__name__ + ".BufferPool")
        self._pool_size = pool_size
        self._buffer_size = buffer_size
        
        # Pool management
        self._available_buffers: List[CircularBuffer] = []
        self._used_buffers: Set[CircularBuffer] = set()
        self._lock = threading.Lock()
        
        # Initialize pool
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize buffer pool"""
        for _ in range(self._pool_size):
            buffer = CircularBuffer(self._buffer_size)
            self._available_buffers.append(buffer)
    
    def acquire_buffer(self) -> Optional[CircularBuffer]:
        """Acquire buffer from pool"""
        with self._lock:
            if self._available_buffers:
                buffer = self._available_buffers.pop()
                self._used_buffers.add(buffer)
                buffer.clear()  # Ensure buffer is clean
                return buffer
            else:
                # Pool exhausted - create new buffer
                self.logger.warning("Buffer pool exhausted, creating new buffer")
                buffer = CircularBuffer(self._buffer_size)
                self._used_buffers.add(buffer)
                return buffer
    
    def release_buffer(self, buffer: CircularBuffer):
        """Release buffer back to pool"""
        with self._lock:
            if buffer in self._used_buffers:
                self._used_buffers.remove(buffer)
                buffer.clear()  # Clean buffer before returning to pool
                
                # Only return to pool if we haven't exceeded pool size
                if len(self._available_buffers) < self._pool_size:
                    self._available_buffers.append(buffer)
    
    def get_pool_status(self) -> Dict[str, int]:
        """Get pool status"""
        with self._lock:
            return {
                "available": len(self._available_buffers),
                "used": len(self._used_buffers),
                "total": len(self._available_buffers) + len(self._used_buffers)
            }


class BufferManager:
    """
    High-level buffer manager for coordinating multiple buffers
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__ + ".BufferManager")
        self._buffers: Dict[str, CircularBuffer] = {}
        self._buffer_pool = BufferPool()
        self._lock = threading.RLock()
        
        # Monitoring
        self._monitoring_active = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_interval = 1.0  # seconds
        self._monitor_callbacks: List[Callable[[Dict[str, Any]], None]] = []
    
    def create_buffer(self, buffer_id: str, size: int = 1024, max_size: int = 8192) -> bool:
        """Create a new buffer"""
        try:
            with self._lock:
                if buffer_id in self._buffers:
                    self.logger.warning(f"Buffer {buffer_id} already exists")
                    return False
                
                buffer = CircularBuffer(size, max_size)
                self._buffers[buffer_id] = buffer
                
                # Register for overflow/underflow events
                buffer.register_event_callback(BufferEvent.OVERFLOW_DETECTED, self._on_buffer_overflow)
                buffer.register_event_callback(BufferEvent.UNDERFLOW_DETECTED, self._on_buffer_underflow)
                
                self.logger.info(f"Created buffer {buffer_id} with size {size}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error creating buffer {buffer_id}: {e}")
            return False
    
    def remove_buffer(self, buffer_id: str) -> bool:
        """Remove buffer"""
        try:
            with self._lock:
                if buffer_id not in self._buffers:
                    return False
                
                buffer = self._buffers[buffer_id]
                buffer.clear()
                del self._buffers[buffer_id]
                
                self.logger.info(f"Removed buffer {buffer_id}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error removing buffer {buffer_id}: {e}")
            return False
    
    def get_buffer(self, buffer_id: str) -> Optional[CircularBuffer]:
        """Get buffer by ID"""
        with self._lock:
            return self._buffers.get(buffer_id)
    
    def list_buffers(self) -> List[str]:
        """List all buffer IDs"""
        with self._lock:
            return list(self._buffers.keys())
    
    def get_buffer_status(self, buffer_id: str) -> Optional[Dict[str, Any]]:
        """Get buffer status"""
        buffer = self.get_buffer(buffer_id)
        if not buffer:
            return None
        
        stats = buffer.get_statistics()
        return {
            "buffer_id": buffer_id,
            "size": buffer.get_size(),
            "capacity": buffer.get_capacity(),
            "fill_level": buffer.get_fill_level(),
            "state": buffer.get_state().value,
            "statistics": {
                "total_writes": stats.total_writes,
                "total_reads": stats.total_reads,
                "overflow_count": stats.overflow_count,
                "underflow_count": stats.underflow_count,
                "average_fill_level": stats.average_fill_level,
                "peak_fill_level": stats.peak_fill_level
            }
        }
    
    def get_all_buffer_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all buffers"""
        status = {}
        for buffer_id in self.list_buffers():
            buffer_status = self.get_buffer_status(buffer_id)
            if buffer_status:
                status[buffer_id] = buffer_status
        return status
    
    def start_monitoring(self):
        """Start buffer monitoring"""
        if self._monitoring_active:
            return
        
        self._monitoring_active = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        self.logger.info("Started buffer monitoring")
    
    def stop_monitoring(self):
        """Stop buffer monitoring"""
        self._monitoring_active = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        
        self.logger.info("Stopped buffer monitoring")
    
    def register_monitor_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Register monitoring callback"""
        self._monitor_callbacks.append(callback)
    
    def _monitor_loop(self):
        """Buffer monitoring loop"""
        while self._monitoring_active:
            try:
                # Collect status from all buffers
                all_status = self.get_all_buffer_status()
                
                # Calculate aggregate metrics
                total_buffers = len(all_status)
                total_overflow_count = sum(status["statistics"]["overflow_count"] for status in all_status.values())
                total_underflow_count = sum(status["statistics"]["underflow_count"] for status in all_status.values())
                average_fill_level = sum(status["fill_level"] for status in all_status.values()) / max(1, total_buffers)
                
                monitor_data = {
                    "timestamp": datetime.now().isoformat(),
                    "total_buffers": total_buffers,
                    "total_overflow_count": total_overflow_count,
                    "total_underflow_count": total_underflow_count,
                    "average_fill_level": average_fill_level,
                    "buffer_status": all_status,
                    "pool_status": self._buffer_pool.get_pool_status()
                }
                
                # Notify callbacks
                for callback in self._monitor_callbacks:
                    try:
                        callback(monitor_data)
                    except Exception as e:
                        self.logger.error(f"Error in monitor callback: {e}")
                
                time.sleep(self._monitor_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitor loop: {e}")
                time.sleep(0.1)
    
    def _on_buffer_overflow(self, event: BufferEvent, data: Dict[str, Any]):
        """Handle buffer overflow events"""
        self.logger.warning(f"Buffer overflow detected: fill_level={data.get('fill_level', 0):.2%}")
    
    def _on_buffer_underflow(self, event: BufferEvent, data: Dict[str, Any]):
        """Handle buffer underflow events"""
        self.logger.warning(f"Buffer underflow detected: fill_level={data.get('fill_level', 0):.2%}")


# Factory functions
def create_circular_buffer(size: int = 1024, max_size: int = 8192) -> CircularBuffer:
    """Create a circular buffer instance"""
    return CircularBuffer(size, max_size)


def create_buffer_manager() -> BufferManager:
    """Create a buffer manager instance"""
    return BufferManager()