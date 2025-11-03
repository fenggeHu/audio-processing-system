"""
Audio capture service for multi-channel synchronized audio input.

This module provides the CaptureService class that handles audio device
management, multi-channel synchronized capture, buffering, and frame alignment.
"""

import asyncio
import time
from typing import Dict, List, Optional, AsyncGenerator, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import numpy as np
import structlog

from ..interfaces import IMetricsCollector
from ..base import BaseAudioProcessor
from ..models import AudioFrame, AudioConfig
from ..exceptions import DeviceError

logger = structlog.get_logger(__name__)


@dataclass
class AudioDevice:
    """Audio device information."""
    device_id: int
    name: str
    channels: int
    sample_rate: int
    is_default: bool = False
    is_available: bool = True
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaptureBuffer:
    """Audio capture buffer for frame alignment."""
    data: np.ndarray  # Circular buffer
    write_pos: int = 0
    read_pos: int = 0
    size: int = 0
    sample_rate: int = 48000
    channels: int = 8
    
    def __post_init__(self):
        """Initialize buffer after creation."""
        if self.data is None:
            # Default to 1 second buffer
            buffer_samples = self.sample_rate
            self.data = np.zeros((self.channels, buffer_samples), dtype=np.float32)
            self.size = buffer_samples
    
    def write(self, audio_data: np.ndarray) -> bool:
        """
        Write audio data to buffer.
        
        Args:
            audio_data: Audio data to write (channels, samples)
            
        Returns:
            True if write successful, False if buffer overflow
        """
        samples = audio_data.shape[1]
        
        # Check for buffer overflow
        available_space = self._get_available_write_space()
        if samples > available_space:
            logger.warning(
                "Buffer overflow detected",
                samples=samples,
                available=available_space
            )
            return False
        
        # Handle wrap-around
        if self.write_pos + samples <= self.size:
            # No wrap-around needed
            self.data[:, self.write_pos:self.write_pos + samples] = audio_data
        else:
            # Split write across buffer boundary
            first_part = self.size - self.write_pos
            second_part = samples - first_part
            
            self.data[:, self.write_pos:] = audio_data[:, :first_part]
            self.data[:, :second_part] = audio_data[:, first_part:]
        
        self.write_pos = (self.write_pos + samples) % self.size
        return True
    
    def read(self, num_samples: int) -> Optional[np.ndarray]:
        """
        Read audio data from buffer.
        
        Args:
            num_samples: Number of samples to read
            
        Returns:
            Audio data (channels, samples) or None if not enough data
        """
        available_samples = self._get_available_read_samples()
        if num_samples > available_samples:
            return None
        
        # Handle wrap-around
        if self.read_pos + num_samples <= self.size:
            # No wrap-around needed
            result = self.data[:, self.read_pos:self.read_pos + num_samples].copy()
        else:
            # Split read across buffer boundary
            first_part = self.size - self.read_pos
            second_part = num_samples - first_part
            
            result = np.zeros((self.channels, num_samples), dtype=np.float32)
            result[:, :first_part] = self.data[:, self.read_pos:]
            result[:, first_part:] = self.data[:, :second_part]
        
        self.read_pos = (self.read_pos + num_samples) % self.size
        return result
    
    def _get_available_write_space(self) -> int:
        """Get available space for writing."""
        used_samples = self._get_available_read_samples()
        return self.size - used_samples - 1  # -1 to prevent write_pos == read_pos
    
    def _get_available_read_samples(self) -> int:
        """Get available samples for reading."""
        if self.write_pos >= self.read_pos:
            return self.write_pos - self.read_pos
        else:
            return self.size - (self.read_pos - self.write_pos)
    
    def get_buffer_usage(self) -> float:
        """Get buffer usage as percentage."""
        used_samples = self._get_available_read_samples()
        return (used_samples / self.size) * 100.0


class DeviceManager:
    """Manages audio input devices and their configuration."""
    
    def __init__(self):
        self._devices: Dict[int, AudioDevice] = {}
        self._default_device: Optional[AudioDevice] = None
        self._device_lock = asyncio.Lock()
    
    async def scan_devices(self) -> List[AudioDevice]:
        """
        Scan for available audio input devices.
        
        Returns:
            List of available audio devices
        """
        async with self._device_lock:
            # Mock device scanning - in real implementation would use PyAudio
            mock_devices = [
                AudioDevice(
                    device_id=0,
                    name="Built-in Microphone",
                    channels=2,
                    sample_rate=48000,
                    is_default=True,
                    latency_ms=10.0
                ),
                AudioDevice(
                    device_id=1,
                    name="USB Audio Array",
                    channels=8,
                    sample_rate=48000,
                    is_default=False,
                    latency_ms=15.0
                ),
                AudioDevice(
                    device_id=2,
                    name="Professional Audio Interface",
                    channels=16,
                    sample_rate=96000,
                    is_default=False,
                    latency_ms=5.0
                )
            ]
            
            self._devices.clear()
            for device in mock_devices:
                self._devices[device.device_id] = device
                if device.is_default:
                    self._default_device = device
            
            logger.info("Audio devices scanned", device_count=len(mock_devices))
            return mock_devices
    
    async def get_device(self, device_id: Optional[int] = None) -> Optional[AudioDevice]:
        """
        Get audio device by ID or default device.
        
        Args:
            device_id: Device ID, or None for default device
            
        Returns:
            AudioDevice or None if not found
        """
        async with self._device_lock:
            if device_id is None:
                return self._default_device
            return self._devices.get(device_id)
    
    async def get_all_devices(self) -> List[AudioDevice]:
        """Get all available devices."""
        async with self._device_lock:
            return list(self._devices.values())
    
    async def test_device(self, device_id: int) -> bool:
        """
        Test if device is working properly.
        
        Args:
            device_id: Device ID to test
            
        Returns:
            True if device is working
        """
        device = await self.get_device(device_id)
        if not device:
            return False
        
        # Mock device test - in real implementation would try to open device
        await asyncio.sleep(0.1)  # Simulate test time
        
        is_working = device.is_available
        logger.debug("Device test completed", device_id=device_id, working=is_working)
        return is_working


class FrameAligner:
    """Handles frame alignment and synchronization across channels."""
    
    def __init__(self, config: AudioConfig):
        self.config = config
        self._reference_timestamp: Optional[datetime] = None
        self._frame_counter = 0
        self._drift_compensation = 0.0
        self._max_drift_ms = 5.0  # Maximum allowed drift
    
    def align_frame(self, raw_data: np.ndarray, capture_timestamp: datetime) -> AudioFrame:
        """
        Align raw audio data to frame boundaries.
        
        Args:
            raw_data: Raw audio data (channels, samples)
            capture_timestamp: When the data was captured
            
        Returns:
            Aligned AudioFrame
        """
        if self._reference_timestamp is None:
            self._reference_timestamp = capture_timestamp
        
        # Calculate expected timestamp based on frame counter
        expected_timestamp = self._reference_timestamp + timedelta(
            milliseconds=self._frame_counter * self.config.get_frame_duration_ms()
        )
        
        # Calculate drift
        actual_drift = (capture_timestamp - expected_timestamp).total_seconds() * 1000
        
        # Apply drift compensation if needed
        if abs(actual_drift) > self._max_drift_ms:
            logger.warning(
                "Frame drift detected",
                drift_ms=actual_drift,
                frame=self._frame_counter
            )
            
            # Reset reference if drift is too large
            if abs(actual_drift) > 50.0:  # 50ms threshold for reset
                self._reference_timestamp = capture_timestamp
                self._frame_counter = 0
                actual_drift = 0.0
        
        # Update drift compensation (simple low-pass filter)
        self._drift_compensation = 0.9 * self._drift_compensation + 0.1 * actual_drift
        
        # Create aligned frame
        aligned_timestamp = expected_timestamp + timedelta(
            milliseconds=self._drift_compensation
        )
        
        frame = AudioFrame(
            timestamp=aligned_timestamp,
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
            frame_size=self.config.frame_size,
            data=raw_data,
            metadata={
                'frame_number': self._frame_counter,
                'drift_ms': actual_drift,
                'drift_compensation_ms': self._drift_compensation
            }
        )
        
        self._frame_counter += 1
        return frame
    
    def reset_alignment(self) -> None:
        """Reset frame alignment state."""
        self._reference_timestamp = None
        self._frame_counter = 0
        self._drift_compensation = 0.0
        logger.debug("Frame alignment reset")


class CaptureService(BaseAudioProcessor):
    """
    Audio capture service with multi-channel synchronization.
    
    Provides synchronized audio capture from multiple channels with
    device management, buffering, and frame alignment capabilities.
    """
    
    def __init__(self, service_name: str, config: AudioConfig, 
                 metrics_collector: Optional[IMetricsCollector] = None):
        super().__init__(service_name, config, metrics_collector)
        
        self._device_manager = DeviceManager()
        self._frame_aligner = FrameAligner(config)
        self._capture_buffer = CaptureBuffer(
            data=None,
            sample_rate=config.sample_rate,
            channels=config.channels
        )
        
        self._current_device: Optional[AudioDevice] = None
        self._capture_task: Optional[asyncio.Task] = None
        self._frame_queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        
        # Capture statistics
        self._frames_captured = 0
        self._buffer_overruns = 0
        self._buffer_underruns = 0
        self._last_capture_time = 0.0
        
        # Mock audio generation for testing
        self._mock_audio_enabled = True
        self._mock_frequency = 1000.0  # 1kHz test tone
        self._mock_phase = 0.0
    
    async def _initialize(self) -> None:
        """Initialize capture service."""
        logger.info("Initializing capture service", service=self.service_name)
        
        # Scan for available devices
        devices = await self._device_manager.scan_devices()
        if not devices:
            raise DeviceError("No audio input devices found")
        
        # Select appropriate device
        target_device = None
        
        # If we have a current device set (from device switching), use it
        if hasattr(self, '_current_device') and self._current_device:
            target_device = self._current_device
        else:
            # Find suitable device based on requirements
            for device in devices:
                if (device.channels >= self._audio_config.channels and 
                    device.sample_rate >= self._audio_config.sample_rate):
                    target_device = device
                    break
            
            if not target_device:
                # Fall back to default device
                target_device = await self._device_manager.get_device()
        
        if not target_device:
            raise DeviceError("No suitable audio input device found")
        
        # Test device
        if not await self._device_manager.test_device(target_device.device_id):
            raise DeviceError(f"Device {target_device.name} is not working")
        
        self._current_device = target_device
        logger.info(
            "Audio device selected",
            device_name=target_device.name,
            channels=target_device.channels,
            sample_rate=target_device.sample_rate
        )
    
    async def _cleanup(self) -> None:
        """Cleanup capture service."""
        if self._capture_task and not self._capture_task.done():
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Capture service cleaned up")
    
    async def _start_background_tasks(self) -> None:
        """Start background capture task."""
        self._capture_task = self.add_background_task(self._capture_loop())
    
    async def _process_frame(self, frame: AudioFrame) -> AudioFrame:
        """
        Process captured audio frame.
        
        For the capture service, this just passes through the frame
        as it's already been processed during capture.
        """
        return frame
    
    async def _capture_loop(self) -> None:
        """Main capture loop running in background."""
        logger.info("Starting audio capture loop")
        
        frame_duration = self._audio_config.get_frame_duration_ms() / 1000.0  # seconds
        
        while self._is_running:
            try:
                capture_start = time.time()
                
                # Generate mock audio data
                audio_data = self._generate_mock_audio()
                
                # Write to buffer
                if not self._capture_buffer.write(audio_data):
                    self._buffer_overruns += 1
                    logger.warning("Capture buffer overrun", count=self._buffer_overruns)
                
                # Try to read a complete frame
                frame_data = self._capture_buffer.read(self._audio_config.frame_size)
                if frame_data is not None:
                    # Create aligned frame
                    capture_timestamp = datetime.now()
                    frame = self._frame_aligner.align_frame(frame_data, capture_timestamp)
                    
                    # Add to frame queue
                    try:
                        self._frame_queue.put_nowait(frame)
                        self._frames_captured += 1
                    except asyncio.QueueFull:
                        logger.warning("Frame queue full, dropping frame")
                        self._frames_dropped += 1
                
                # Maintain capture timing
                capture_time = time.time() - capture_start
                sleep_time = max(0, frame_duration - capture_time)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                
                self._last_capture_time = capture_time
                
            except Exception as e:
                logger.error("Capture loop error", error=str(e))
                await asyncio.sleep(0.001)  # Brief pause before retry
    
    def _generate_mock_audio(self) -> np.ndarray:
        """
        Generate mock audio data for testing.
        
        Returns:
            Mock audio data (channels, samples)
        """
        samples_per_frame = self._audio_config.frame_size
        
        if not self._mock_audio_enabled:
            return np.zeros((self._audio_config.channels, samples_per_frame), dtype=np.float32)
        
        # Generate test tone with slight variations per channel
        sample_rate = self._audio_config.sample_rate
        
        # Time array for this frame
        t = np.arange(samples_per_frame) / sample_rate
        
        # Generate multi-channel audio with different frequencies per channel
        audio_data = np.zeros((self._audio_config.channels, samples_per_frame), dtype=np.float32)
        
        for ch in range(self._audio_config.channels):
            # Each channel gets a slightly different frequency
            freq = self._mock_frequency + (ch * 100)  # 100Hz spacing
            
            # Generate sine wave with some amplitude variation
            amplitude = 0.1 * (1.0 + 0.2 * np.sin(2 * np.pi * 0.5 * time.time()))
            audio_data[ch] = amplitude * np.sin(2 * np.pi * freq * t + self._mock_phase)
        
        # Update phase for continuity
        self._mock_phase += 2 * np.pi * self._mock_frequency * samples_per_frame / sample_rate
        self._mock_phase = self._mock_phase % (2 * np.pi)
        
        return audio_data
    
    async def get_next_frame(self) -> Optional[AudioFrame]:
        """
        Get the next captured audio frame.
        
        Returns:
            Next AudioFrame or None if no frame available
        """
        try:
            frame = self._frame_queue.get_nowait()
            return frame
        except asyncio.QueueEmpty:
            return None
    
    async def get_frame_stream(self) -> AsyncGenerator[AudioFrame, None]:
        """
        Get continuous stream of captured audio frames.
        
        Yields:
            AudioFrame objects as they become available
        """
        while self._is_running:
            try:
                # Wait for frame with timeout
                frame = await asyncio.wait_for(
                    self._frame_queue.get(), 
                    timeout=0.1
                )
                yield frame
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Frame stream error", error=str(e))
                break
    
    def get_capture_metrics(self) -> Dict[str, Any]:
        """
        Get capture-specific metrics.
        
        Returns:
            Dictionary with capture metrics
        """
        return {
            'frames_captured': self._frames_captured,
            'buffer_overruns': self._buffer_overruns,
            'buffer_underruns': self._buffer_underruns,
            'buffer_usage_percent': self._capture_buffer.get_buffer_usage(),
            'last_capture_time_ms': self._last_capture_time * 1000,
            'queue_size': self._frame_queue.qsize(),
            'current_device': self._current_device.name if self._current_device else None
        }
    
    def get_device_info(self) -> Optional[AudioDevice]:
        """Get current audio device information."""
        return self._current_device
    
    async def get_available_devices(self) -> List[AudioDevice]:
        """Get list of available audio devices."""
        return await self._device_manager.get_all_devices()
    
    async def switch_device(self, device_id: int) -> bool:
        """
        Switch to a different audio device.
        
        Args:
            device_id: ID of device to switch to
            
        Returns:
            True if switch successful
        """
        new_device = await self._device_manager.get_device(device_id)
        if not new_device:
            logger.error("Device not found", device_id=device_id)
            return False
        
        if not await self._device_manager.test_device(device_id):
            logger.error("Device test failed", device_id=device_id)
            return False
        
        # Stop current capture
        was_running = self._is_running
        if was_running:
            await self.stop()
        
        # Switch device
        self._current_device
        self._current_device = new_device
        logger.info("Switched to device", device_name=new_device.name)
        
        # Restart if was running
        if was_running:
            await self.start()
            
        # Verify the switch actually happened
        if self._current_device.device_id != new_device.device_id:
            # Device selection logic might have chosen a different device
            # This can happen if the new device doesn't meet requirements
            logger.warning(
                "Device switch resulted in different device",
                requested=new_device.device_id,
                actual=self._current_device.device_id
            )
        
        return True
    
    def set_mock_audio_enabled(self, enabled: bool) -> None:
        """Enable or disable mock audio generation."""
        self._mock_audio_enabled = enabled
        if not enabled:
            # Reset phase when disabling to ensure clean silence
            self._mock_phase = 0.0
            # Clear the capture buffer to remove any existing audio data
            self._capture_buffer = CaptureBuffer(
                data=None,
                sample_rate=self._audio_config.sample_rate,
                channels=self._audio_config.channels
            )
            # Clear the frame queue to remove any buffered frames with audio
            while not self._frame_queue.empty():
                try:
                    self._frame_queue.get_nowait()
                except:
                    break
        logger.debug("Mock audio generation", enabled=enabled)
    
    def set_mock_frequency(self, frequency: float) -> None:
        """Set mock audio test tone frequency."""
        self._mock_frequency = frequency
        logger.debug("Mock audio frequency set", frequency=frequency)
    
    def _update_current_metrics(self, processing_time_ms: float) -> None:
        """Update current metrics with capture-specific data."""
        super()._update_current_metrics(processing_time_ms)
        
        # Add capture-specific metrics
        self._current_metrics.frames_processed = self._frames_captured
        self._current_metrics.frames_dropped = self._buffer_overruns + self._frames_dropped