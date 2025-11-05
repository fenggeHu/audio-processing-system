"""
Concrete Hardware Device Implementations

Concrete implementations of hardware devices for the abstraction layer.
"""

import time
import threading
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import numpy as np

from .hardware_interface import (
    IHardwareDevice, TimingInfo, PerformanceMetrics, ClockSyncStatus
)
from .models import AudioDevice, AudioFrame, DeviceType


class MockAudioDevice(IHardwareDevice):
    """Mock audio device implementation for testing and development"""
    
    def __init__(self, device_info: AudioDevice):
        self.logger = logging.getLogger(__name__)
        self._device_info = device_info
        self._config: Dict[str, Any] = {}
        self._active = False
        self._timing_info: Optional[TimingInfo] = None
        self._performance_metrics: Optional[PerformanceMetrics] = None
        
        # Mock audio generation
        self._sample_rate = 48000
        self._channels = 2
        self._buffer_size = 256
        self._frame_counter = 0
        
        # Threading for continuous operation
        self._capture_thread: Optional[threading.Thread] = None
        self._capture_active = False
        self._frame_queue = []
        self._queue_lock = threading.Lock()
    
    def get_device_info(self) -> AudioDevice:
        """Get device information"""
        return self._device_info
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize device with configuration"""
        try:
            self._config = config.copy()
            self._sample_rate = config.get('sample_rate', 48000)
            self._channels = config.get('channels', 2)
            self._buffer_size = config.get('buffer_size', 256)
            
            # Initialize timing info
            self._timing_info = TimingInfo(
                device_id=self._device_info.device_id,
                sample_rate=self._sample_rate,
                buffer_size=self._buffer_size,
                input_latency_ms=5.0,  # Mock latency
                output_latency_ms=5.0,
                round_trip_latency_ms=10.0,
                sync_status=ClockSyncStatus.SYNCING
            )
            
            # Initialize performance metrics
            self._performance_metrics = PerformanceMetrics(
                device_id=self._device_info.device_id
            )
            
            self.logger.info(f"Initialized mock device: {self._device_info.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize device: {e}")
            return False
    
    def start(self) -> bool:
        """Start device operation"""
        if self._active:
            return True
        
        try:
            self._active = True
            
            # Start capture thread for input devices
            if self._device_info.is_input:
                self._capture_active = True
                self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
                self._capture_thread.start()
            
            self.logger.info(f"Started device: {self._device_info.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start device: {e}")
            return False
    
    def stop(self) -> bool:
        """Stop device operation"""
        try:
            self._active = False
            
            # Stop capture thread
            if self._capture_active:
                self._capture_active = False
                if self._capture_thread and self._capture_thread.is_alive():
                    self._capture_thread.join(timeout=1.0)
            
            # Clear frame queue
            with self._queue_lock:
                self._frame_queue.clear()
            
            self.logger.info(f"Stopped device: {self._device_info.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop device: {e}")
            return False
    
    def read_frame(self) -> Optional[AudioFrame]:
        """Read audio frame from input device"""
        if not self._active or not self._device_info.is_input:
            return None
        
        with self._queue_lock:
            if self._frame_queue:
                return self._frame_queue.pop(0)
        
        return None
    
    def write_frame(self, frame: AudioFrame) -> bool:
        """Write audio frame to output device"""
        if not self._active or not self._device_info.is_output:
            return False
        
        try:
            # Mock frame processing
            time.sleep(0.001)  # Simulate processing time
            
            # Update performance metrics
            if self._performance_metrics:
                self._performance_metrics.frames_per_second += 1
                self._performance_metrics.bytes_per_second += len(frame.data) if frame.data is not None else 0
                self._performance_metrics.last_update = datetime.now()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to write frame: {e}")
            return False
    
    def get_timing_info(self) -> TimingInfo:
        """Get device timing information"""
        if self._timing_info:
            # Update timing info with current values
            self._timing_info.last_sync_time = datetime.now()
            
            # Mock jitter calculation
            import random
            self._timing_info.jitter_ms = random.uniform(0.1, 2.0)
            self._timing_info.avg_processing_time_ms = random.uniform(1.0, 5.0)
        
        return self._timing_info
    
    def get_performance_metrics(self) -> PerformanceMetrics:
        """Get device performance metrics"""
        if self._performance_metrics:
            # Update performance metrics with mock values
            import random
            self._performance_metrics.cpu_usage_percent = random.uniform(5.0, 25.0)
            self._performance_metrics.memory_usage_mb = random.uniform(10.0, 50.0)
            self._performance_metrics.signal_level_db = random.uniform(-20.0, -5.0)
            self._performance_metrics.noise_floor_db = random.uniform(-80.0, -60.0)
            self._performance_metrics.snr_db = self._performance_metrics.signal_level_db - self._performance_metrics.noise_floor_db
            self._performance_metrics.thd_percent = random.uniform(0.01, 0.1)
            self._performance_metrics.last_update = datetime.now()
        
        return self._performance_metrics
    
    def calibrate_timing(self) -> bool:
        """Calibrate device timing"""
        try:
            if self._timing_info:
                # Mock calibration process
                time.sleep(0.1)  # Simulate calibration time
                
                # Reset timing statistics
                self._timing_info.jitter_ms = 0.0
                self._timing_info.max_jitter_ms = 0.0
                self._timing_info.buffer_underruns = 0
                self._timing_info.buffer_overruns = 0
                self._timing_info.dropped_frames = 0
                self._timing_info.sync_status = ClockSyncStatus.SYNCED
                
                self.logger.info(f"Calibrated timing for device: {self._device_info.name}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to calibrate timing: {e}")
            return False
    
    def reset_buffers(self) -> bool:
        """Reset device buffers"""
        try:
            # Clear frame queue
            with self._queue_lock:
                self._frame_queue.clear()
            
            # Reset buffer statistics
            if self._timing_info:
                self._timing_info.buffer_underruns = 0
                self._timing_info.buffer_overruns = 0
                self._timing_info.dropped_frames = 0
            
            self.logger.info(f"Reset buffers for device: {self._device_info.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to reset buffers: {e}")
            return False
    
    def _capture_loop(self):
        """Capture loop for input devices"""
        frame_duration = self._buffer_size / self._sample_rate  # Duration in seconds
        
        while self._capture_active:
            try:
                # Generate mock audio data
                audio_data = self._generate_mock_audio()
                
                # Create audio frame
                frame = AudioFrame(
                    frame_id=self._frame_counter,
                    timestamp=datetime.now(),
                    sample_rate=self._sample_rate,
                    channels=self._channels,
                    bit_depth=24,
                    data=audio_data,
                    frame_size=len(audio_data) if audio_data is not None else 0
                )
                
                # Add to queue
                with self._queue_lock:
                    self._frame_queue.append(frame)
                    
                    # Limit queue size to prevent memory issues
                    if len(self._frame_queue) > 10:
                        self._frame_queue.pop(0)
                        if self._timing_info:
                            self._timing_info.buffer_overruns += 1
                
                self._frame_counter += 1
                
                # Update performance metrics
                if self._performance_metrics:
                    self._performance_metrics.frames_per_second += 1
                    self._performance_metrics.last_update = datetime.now()
                
                # Sleep for frame duration
                time.sleep(frame_duration)
                
            except Exception as e:
                self.logger.error(f"Error in capture loop: {e}")
                time.sleep(0.01)
    
    def _generate_mock_audio(self) -> Optional[np.ndarray]:
        """Generate mock audio data"""
        try:
            # Generate sine wave test signal
            t = np.linspace(0, self._buffer_size / self._sample_rate, self._buffer_size, False)
            frequency = 440.0  # A4 note
            amplitude = 0.1
            
            # Generate mono signal
            signal = amplitude * np.sin(2 * np.pi * frequency * t)
            
            # Convert to multi-channel if needed
            if self._channels > 1:
                audio_data = np.column_stack([signal] * self._channels)
            else:
                audio_data = signal.reshape(-1, 1)
            
            return audio_data.astype(np.float32)
            
        except Exception as e:
            self.logger.error(f"Failed to generate mock audio: {e}")
            return None


class USBAudioDevice(MockAudioDevice):
    """USB Audio device implementation"""
    
    def __init__(self, device_info: AudioDevice):
        super().__init__(device_info)
        self._usb_specific_config = {}
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize USB audio device"""
        if not super().initialize(config):
            return False
        
        try:
            # USB-specific initialization
            self._usb_specific_config = config.get('usb_config', {})
            
            # USB devices typically have higher latency
            if self._timing_info:
                self._timing_info.input_latency_ms = 8.0
                self._timing_info.output_latency_ms = 8.0
                self._timing_info.round_trip_latency_ms = 16.0
            
            self.logger.info(f"Initialized USB audio device: {self._device_info.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize USB device: {e}")
            return False


class BuiltInAudioDevice(MockAudioDevice):
    """Built-in audio device implementation"""
    
    def __init__(self, device_info: AudioDevice):
        super().__init__(device_info)
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize built-in audio device"""
        if not super().initialize(config):
            return False
        
        try:
            # Built-in devices typically have lower latency
            if self._timing_info:
                self._timing_info.input_latency_ms = 3.0
                self._timing_info.output_latency_ms = 3.0
                self._timing_info.round_trip_latency_ms = 6.0
            
            self.logger.info(f"Initialized built-in audio device: {self._device_info.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize built-in device: {e}")
            return False


# Factory functions for creating device instances
def create_hardware_device(device_info: AudioDevice) -> IHardwareDevice:
    """Create appropriate hardware device implementation based on device type"""
    
    if device_info.device_type == DeviceType.USB_AUDIO:
        return USBAudioDevice(device_info)
    elif device_info.device_type in [DeviceType.MICROPHONE, DeviceType.SPEAKER]:
        # Assume built-in for microphones and speakers
        return BuiltInAudioDevice(device_info)
    else:
        # Default to mock device
        return MockAudioDevice(device_info)


def create_mock_devices() -> Dict[str, IHardwareDevice]:
    """Create a set of mock devices for testing"""
    devices = {}
    
    # Create mock input device
    input_device_info = AudioDevice(
        device_id="mock_input_0",
        name="Mock Microphone",
        device_type=DeviceType.MICROPHONE,
        is_input=True,
        is_output=False,
        max_input_channels=2,
        supported_sample_rates=[44100, 48000, 96000],
        supported_bit_depths=[16, 24, 32]
    )
    devices["mock_input_0"] = MockAudioDevice(input_device_info)
    
    # Create mock output device
    output_device_info = AudioDevice(
        device_id="mock_output_0",
        name="Mock Speakers",
        device_type=DeviceType.SPEAKER,
        is_input=False,
        is_output=True,
        max_output_channels=2,
        supported_sample_rates=[44100, 48000, 96000],
        supported_bit_depths=[16, 24, 32]
    )
    devices["mock_output_0"] = MockAudioDevice(output_device_info)
    
    # Create mock USB device
    usb_device_info = AudioDevice(
        device_id="mock_usb_0",
        name="Mock USB Audio Interface",
        device_type=DeviceType.USB_AUDIO,
        is_input=True,
        is_output=True,
        max_input_channels=8,
        max_output_channels=8,
        supported_sample_rates=[44100, 48000, 88200, 96000, 192000],
        supported_bit_depths=[16, 24, 32]
    )
    devices["mock_usb_0"] = USBAudioDevice(usb_device_info)
    
    return devices