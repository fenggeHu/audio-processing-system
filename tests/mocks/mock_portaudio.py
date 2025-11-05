"""
Mock PortAudio implementation for testing
Simulates hardware audio interfaces without requiring actual audio devices
"""

import time
import threading
import numpy as np
from typing import Dict, List, Optional, Callable, Any
from unittest.mock import Mock
from dataclasses import dataclass
from enum import Enum

class AudioFormat(Enum):
    """Audio format enumeration"""
    FLOAT32 = 1
    INT32 = 2
    INT24 = 3
    INT16 = 4
    INT8 = 5
    UINT8 = 6

class HostApiType(Enum):
    """Host API type enumeration"""
    ALSA = 8
    COREAUDIO = 5
    WASAPI = 13
    DIRECTSOUND = 1
    MME = 2

@dataclass
class MockDeviceInfo:
    """Mock audio device information"""
    index: int
    name: str
    hostApi: int
    maxInputChannels: int
    maxOutputChannels: int
    defaultSampleRate: float
    defaultLowInputLatency: float
    defaultLowOutputLatency: float
    defaultHighInputLatency: float
    defaultHighOutputLatency: float

@dataclass
class MockHostApiInfo:
    """Mock host API information"""
    index: int
    type: HostApiType
    name: str
    deviceCount: int
    defaultInputDevice: int
    defaultOutputDevice: int

class MockAudioStream:
    """Mock audio stream for testing"""
    
    def __init__(self, 
                 rate: int,
                 channels: int,
                 format: AudioFormat,
                 input: bool = True,
                 output: bool = False,
                 frames_per_buffer: int = 1024,
                 stream_callback: Optional[Callable] = None,
                 input_device_index: Optional[int] = None,
                 output_device_index: Optional[int] = None):
        
        self.rate = rate
        self.channels = channels
        self.format = format
        self.input = input
        self.output = output
        self.frames_per_buffer = frames_per_buffer
        self.stream_callback = stream_callback
        self.input_device_index = input_device_index
        self.output_device_index = output_device_index
        
        self.is_active = False
        self.is_stopped = True
        self._thread = None
        self._stop_event = threading.Event()
        
        # Simulate audio data generation
        self._time_offset = 0
        self._sample_count = 0
        
        # Error simulation
        self.simulate_underrun = False
        self.simulate_overflow = False
        self.simulate_device_unavailable = False
        self.error_probability = 0.0
        
    def start(self):
        """Start the mock audio stream"""
        if self.is_active:
            raise RuntimeError("Stream already active")
            
        if self.simulate_device_unavailable:
            raise RuntimeError("Device unavailable")
            
        self.is_active = True
        self.is_stopped = False
        self._stop_event.clear()
        
        if self.stream_callback:
            self._thread = threading.Thread(target=self._stream_thread)
            self._thread.daemon = True
            self._thread.start()
    
    def stop(self):
        """Stop the mock audio stream"""
        if not self.is_active:
            return
            
        self.is_active = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
    
    def close(self):
        """Close the mock audio stream"""
        self.stop()
        self.is_stopped = True
    
    def read(self, num_frames: int, exception_on_overflow: bool = True) -> bytes:
        """Read audio data from mock stream"""
        if not self.is_active:
            raise RuntimeError("Stream not active")
            
        if self.simulate_overflow and exception_on_overflow:
            raise RuntimeError("Input overflowed")
            
        # Generate mock audio data
        audio_data = self._generate_audio_data(num_frames)
        return audio_data.tobytes()
    
    def write(self, frames: bytes, num_frames: int, exception_on_underrun: bool = True):
        """Write audio data to mock stream"""
        if not self.is_active:
            raise RuntimeError("Stream not active")
            
        if self.simulate_underrun and exception_on_underrun:
            raise RuntimeError("Output underflowed")
    
    def get_read_available(self) -> int:
        """Get number of frames available for reading"""
        if not self.is_active:
            return 0
        return self.frames_per_buffer
    
    def get_write_available(self) -> int:
        """Get number of frames available for writing"""
        if not self.is_active:
            return 0
        return self.frames_per_buffer
    
    def _stream_thread(self):
        """Background thread for stream callback"""
        frame_duration = self.frames_per_buffer / self.rate
        
        while not self._stop_event.is_set():
            if self.stream_callback:
                # Generate input data
                input_data = None
                if self.input:
                    input_data = self._generate_audio_data(self.frames_per_buffer)
                
                # Prepare output buffer
                output_data = None
                if self.output:
                    output_data = np.zeros((self.frames_per_buffer, self.channels), dtype=np.float32)
                
                # Simulate errors
                if np.random.random() < self.error_probability:
                    status_flags = 1  # Input overflow or output underflow
                else:
                    status_flags = 0
                
                try:
                    # Call the callback
                    result = self.stream_callback(
                        input_data.tobytes() if input_data is not None else None,
                        self.frames_per_buffer,
                        None,  # time_info
                        status_flags
                    )
                    
                    if result and result[1] != 0:  # paContinue = 0
                        break
                        
                except Exception as e:
                    print(f"Stream callback error: {e}")
                    break
            
            # Sleep for frame duration
            time.sleep(frame_duration)
    
    def _generate_audio_data(self, num_frames: int) -> np.ndarray:
        """Generate mock audio data"""
        # Generate sine wave test signal
        t = np.arange(self._sample_count, self._sample_count + num_frames) / self.rate
        
        # Multi-channel sine waves with different frequencies
        audio_data = np.zeros((num_frames, self.channels), dtype=np.float32)
        
        for ch in range(self.channels):
            frequency = 440.0 * (2 ** (ch / 12))  # Musical intervals
            amplitude = 0.1  # Low amplitude to avoid clipping
            audio_data[:, ch] = amplitude * np.sin(2 * np.pi * frequency * t)
        
        self._sample_count += num_frames
        return audio_data

class MockPortAudio:
    """Mock PortAudio implementation for testing"""
    
    def __init__(self):
        self.is_initialized = False
        self.version_text = "Mock PortAudio v19.7.0"
        self.version = 1970
        
        # Mock devices
        self._devices = self._create_mock_devices()
        self._host_apis = self._create_mock_host_apis()
        
        # Active streams
        self._active_streams: List[MockAudioStream] = []
        
        # Error simulation
        self.simulate_init_error = False
        self.simulate_device_error = False
        
    def initialize(self):
        """Initialize mock PortAudio"""
        if self.simulate_init_error:
            raise RuntimeError("PortAudio initialization failed")
            
        self.is_initialized = True
    
    def terminate(self):
        """Terminate mock PortAudio"""
        # Close all active streams
        for stream in self._active_streams[:]:
            stream.close()
        self._active_streams.clear()
        
        self.is_initialized = False
    
    def get_version(self) -> int:
        """Get PortAudio version"""
        return self.version
    
    def get_version_text(self) -> str:
        """Get PortAudio version text"""
        return self.version_text
    
    def get_device_count(self) -> int:
        """Get number of audio devices"""
        return len(self._devices)
    
    def get_device_info_by_index(self, device_index: int) -> MockDeviceInfo:
        """Get device information by index"""
        if not self.is_initialized:
            raise RuntimeError("PortAudio not initialized")
            
        if device_index < 0 or device_index >= len(self._devices):
            raise ValueError("Invalid device index")
            
        if self.simulate_device_error:
            raise RuntimeError("Device error")
            
        return self._devices[device_index]
    
    def get_default_input_device(self) -> int:
        """Get default input device index"""
        return 0
    
    def get_default_output_device(self) -> int:
        """Get default output device index"""
        return 1
    
    def get_host_api_count(self) -> int:
        """Get number of host APIs"""
        return len(self._host_apis)
    
    def get_host_api_info_by_index(self, host_api_index: int) -> MockHostApiInfo:
        """Get host API information by index"""
        if host_api_index < 0 or host_api_index >= len(self._host_apis):
            raise ValueError("Invalid host API index")
        return self._host_apis[host_api_index]
    
    def is_format_supported(self, 
                          sample_rate: float,
                          input_device: Optional[int] = None,
                          input_channels: Optional[int] = None,
                          input_format: Optional[AudioFormat] = None,
                          output_device: Optional[int] = None,
                          output_channels: Optional[int] = None,
                          output_format: Optional[AudioFormat] = None) -> bool:
        """Check if audio format is supported"""
        # Mock implementation - most formats are supported
        if sample_rate < 8000 or sample_rate > 192000:
            return False
        
        if input_channels and input_channels > 32:
            return False
            
        if output_channels and output_channels > 32:
            return False
            
        return True
    
    def open(self,
             rate: int,
             channels: int,
             format: AudioFormat,
             input: bool = False,
             output: bool = False,
             input_device_index: Optional[int] = None,
             output_device_index: Optional[int] = None,
             frames_per_buffer: int = 1024,
             stream_callback: Optional[Callable] = None) -> MockAudioStream:
        """Open audio stream"""
        if not self.is_initialized:
            raise RuntimeError("PortAudio not initialized")
        
        # Validate parameters
        if not input and not output:
            raise ValueError("Must specify input or output")
        
        if input and input_device_index is not None:
            if input_device_index >= len(self._devices):
                raise ValueError("Invalid input device index")
        
        if output and output_device_index is not None:
            if output_device_index >= len(self._devices):
                raise ValueError("Invalid output device index")
        
        # Create mock stream
        stream = MockAudioStream(
            rate=rate,
            channels=channels,
            format=format,
            input=input,
            output=output,
            frames_per_buffer=frames_per_buffer,
            stream_callback=stream_callback,
            input_device_index=input_device_index,
            output_device_index=output_device_index
        )
        
        self._active_streams.append(stream)
        return stream
    
    def _create_mock_devices(self) -> List[MockDeviceInfo]:
        """Create mock audio devices"""
        devices = [
            # Built-in microphone
            MockDeviceInfo(
                index=0,
                name="Built-in Microphone",
                hostApi=0,
                maxInputChannels=2,
                maxOutputChannels=0,
                defaultSampleRate=44100.0,
                defaultLowInputLatency=0.01,
                defaultLowOutputLatency=0.0,
                defaultHighInputLatency=0.1,
                defaultHighOutputLatency=0.0
            ),
            # Built-in speakers
            MockDeviceInfo(
                index=1,
                name="Built-in Output",
                hostApi=0,
                maxInputChannels=0,
                maxOutputChannels=2,
                defaultSampleRate=44100.0,
                defaultLowInputLatency=0.0,
                defaultLowOutputLatency=0.01,
                defaultHighInputLatency=0.0,
                defaultHighOutputLatency=0.1
            ),
            # USB Audio Interface
            MockDeviceInfo(
                index=2,
                name="USB Audio CODEC",
                hostApi=0,
                maxInputChannels=8,
                maxOutputChannels=8,
                defaultSampleRate=48000.0,
                defaultLowInputLatency=0.005,
                defaultLowOutputLatency=0.005,
                defaultHighInputLatency=0.05,
                defaultHighOutputLatency=0.05
            ),
            # Professional Audio Interface
            MockDeviceInfo(
                index=3,
                name="Professional Audio Interface",
                hostApi=0,
                maxInputChannels=32,
                maxOutputChannels=32,
                defaultSampleRate=96000.0,
                defaultLowInputLatency=0.002,
                defaultLowOutputLatency=0.002,
                defaultHighInputLatency=0.02,
                defaultHighOutputLatency=0.02
            )
        ]
        return devices
    
    def _create_mock_host_apis(self) -> List[MockHostApiInfo]:
        """Create mock host APIs"""
        host_apis = [
            MockHostApiInfo(
                index=0,
                type=HostApiType.ALSA,
                name="ALSA",
                deviceCount=4,
                defaultInputDevice=0,
                defaultOutputDevice=1
            )
        ]
        return host_apis
    
    def set_error_simulation(self, 
                           init_error: bool = False,
                           device_error: bool = False):
        """Configure error simulation for testing"""
        self.simulate_init_error = init_error
        self.simulate_device_error = device_error
    
    def add_mock_device(self, device_info: MockDeviceInfo):
        """Add a mock device for testing"""
        device_info.index = len(self._devices)
        self._devices.append(device_info)
    
    def remove_mock_device(self, device_index: int):
        """Remove a mock device for testing hot-plug scenarios"""
        if 0 <= device_index < len(self._devices):
            self._devices.pop(device_index)
            # Update indices
            for i, device in enumerate(self._devices):
                device.index = i

# Global mock instance
_mock_portaudio = MockPortAudio()

# Mock PyAudio class
class MockPyAudio:
    """Mock PyAudio class that uses MockPortAudio"""
    
    # Format constants
    paFloat32 = AudioFormat.FLOAT32
    paInt32 = AudioFormat.INT32
    paInt24 = AudioFormat.INT24
    paInt16 = AudioFormat.INT16
    paInt8 = AudioFormat.INT8
    paUInt8 = AudioFormat.UINT8
    
    # Stream callback return codes
    paContinue = 0
    paComplete = 1
    paAbort = 2
    
    def __init__(self):
        self._pa = _mock_portaudio
        self._pa.initialize()
    
    def terminate(self):
        """Terminate PyAudio"""
        self._pa.terminate()
    
    def get_version_text(self) -> str:
        """Get version text"""
        return self._pa.get_version_text()
    
    def get_device_count(self) -> int:
        """Get device count"""
        return self._pa.get_device_count()
    
    def get_device_info_by_index(self, device_index: int) -> Dict[str, Any]:
        """Get device info as dictionary"""
        info = self._pa.get_device_info_by_index(device_index)
        return {
            'index': info.index,
            'name': info.name,
            'hostApi': info.hostApi,
            'maxInputChannels': info.maxInputChannels,
            'maxOutputChannels': info.maxOutputChannels,
            'defaultSampleRate': info.defaultSampleRate,
            'defaultLowInputLatency': info.defaultLowInputLatency,
            'defaultLowOutputLatency': info.defaultLowOutputLatency,
            'defaultHighInputLatency': info.defaultHighInputLatency,
            'defaultHighOutputLatency': info.defaultHighOutputLatency
        }
    
    def get_default_input_device_info(self) -> Dict[str, Any]:
        """Get default input device info"""
        index = self._pa.get_default_input_device()
        return self.get_device_info_by_index(index)
    
    def get_default_output_device_info(self) -> Dict[str, Any]:
        """Get default output device info"""
        index = self._pa.get_default_output_device()
        return self.get_device_info_by_index(index)
    
    def is_format_supported(self, *args, **kwargs) -> bool:
        """Check format support"""
        return self._pa.is_format_supported(*args, **kwargs)
    
    def open(self, *args, **kwargs) -> MockAudioStream:
        """Open audio stream"""
        return self._pa.open(*args, **kwargs)

def get_mock_portaudio() -> MockPortAudio:
    """Get the global mock PortAudio instance"""
    return _mock_portaudio