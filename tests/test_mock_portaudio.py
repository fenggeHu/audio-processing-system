"""
Unit tests for MockPortAudio implementation
Tests hardware interface mocking, device enumeration, and error handling
"""

import pytest
import numpy as np
import time
import threading
from unittest.mock import patch

from tests.mocks.mock_portaudio import (
    MockPortAudio, MockPyAudio, MockDeviceInfo, MockAudioStream,
    AudioFormat, HostApiType, get_mock_portaudio
)


class TestMockPortAudio:
    """Test MockPortAudio functionality"""
    
    @pytest.fixture
    def mock_pa(self):
        """Create fresh MockPortAudio instance"""
        pa = MockPortAudio()
        pa.initialize()
        yield pa
        pa.terminate()
    
    def test_initialization(self, mock_pa):
        """Test PortAudio initialization and termination"""
        assert mock_pa.is_initialized
        assert mock_pa.get_version() == 1970
        assert "Mock PortAudio" in mock_pa.get_version_text()
        
        mock_pa.terminate()
        assert not mock_pa.is_initialized
    
    def test_initialization_error(self):
        """Test initialization error simulation"""
        pa = MockPortAudio()
        pa.set_error_simulation(init_error=True)
        
        with pytest.raises(RuntimeError, match="initialization failed"):
            pa.initialize()
    
    def test_device_enumeration(self, mock_pa):
        """Test device enumeration"""
        device_count = mock_pa.get_device_count()
        assert device_count > 0
        
        # Test each device
        for i in range(device_count):
            device_info = mock_pa.get_device_info_by_index(i)
            assert isinstance(device_info, MockDeviceInfo)
            assert device_info.index == i
            assert len(device_info.name) > 0
            assert device_info.defaultSampleRate > 0
    
    def test_device_info_validation(self, mock_pa):
        """Test device info validation"""
        # Valid device index
        device_info = mock_pa.get_device_info_by_index(0)
        assert device_info.index == 0
        
        # Invalid device indices
        with pytest.raises(ValueError, match="Invalid device index"):
            mock_pa.get_device_info_by_index(-1)
        
        with pytest.raises(ValueError, match="Invalid device index"):
            mock_pa.get_device_info_by_index(1000)
    
    def test_device_error_simulation(self, mock_pa):
        """Test device error simulation"""
        mock_pa.set_error_simulation(device_error=True)
        
        with pytest.raises(RuntimeError, match="Device error"):
            mock_pa.get_device_info_by_index(0)
    
    def test_default_devices(self, mock_pa):
        """Test default device selection"""
        default_input = mock_pa.get_default_input_device()
        default_output = mock_pa.get_default_output_device()
        
        assert isinstance(default_input, int)
        assert isinstance(default_output, int)
        assert 0 <= default_input < mock_pa.get_device_count()
        assert 0 <= default_output < mock_pa.get_device_count()
    
    def test_host_api_enumeration(self, mock_pa):
        """Test host API enumeration"""
        host_api_count = mock_pa.get_host_api_count()
        assert host_api_count > 0
        
        for i in range(host_api_count):
            host_api_info = mock_pa.get_host_api_info_by_index(i)
            assert host_api_info.index == i
            assert len(host_api_info.name) > 0
            assert host_api_info.deviceCount >= 0
    
    def test_format_support_checking(self, mock_pa):
        """Test audio format support checking"""
        # Supported formats
        assert mock_pa.is_format_supported(44100, input_channels=2, input_format=AudioFormat.INT16)
        assert mock_pa.is_format_supported(48000, output_channels=2, output_format=AudioFormat.FLOAT32)
        
        # Unsupported formats
        assert not mock_pa.is_format_supported(1000)  # Too low sample rate
        assert not mock_pa.is_format_supported(500000)  # Too high sample rate
        assert not mock_pa.is_format_supported(48000, input_channels=100)  # Too many channels
    
    def test_stream_opening(self, mock_pa):
        """Test audio stream opening"""
        # Input stream
        input_stream = mock_pa.open(
            rate=48000,
            channels=2,
            format=AudioFormat.FLOAT32,
            input=True,
            frames_per_buffer=1024
        )
        
        assert isinstance(input_stream, MockAudioStream)
        assert input_stream.rate == 48000
        assert input_stream.channels == 2
        assert input_stream.input is True
        assert input_stream.output is False
        
        # Output stream
        output_stream = mock_pa.open(
            rate=44100,
            channels=2,
            format=AudioFormat.INT16,
            output=True,
            frames_per_buffer=512
        )
        
        assert output_stream.rate == 44100
        assert output_stream.output is True
        assert output_stream.input is False
        
        # Cleanup
        input_stream.close()
        output_stream.close()
    
    def test_stream_validation(self, mock_pa):
        """Test stream parameter validation"""
        # Must specify input or output
        with pytest.raises(ValueError, match="Must specify input or output"):
            mock_pa.open(rate=48000, channels=2, format=AudioFormat.FLOAT32)
        
        # Invalid device index
        with pytest.raises(ValueError, match="Invalid input device index"):
            mock_pa.open(
                rate=48000, channels=2, format=AudioFormat.FLOAT32,
                input=True, input_device_index=1000
            )
    
    def test_dynamic_device_management(self, mock_pa):
        """Test dynamic device addition and removal"""
        initial_count = mock_pa.get_device_count()
        
        # Add device
        new_device = MockDeviceInfo(
            index=0,  # Will be updated
            name="Test Device",
            hostApi=0,
            maxInputChannels=2,
            maxOutputChannels=2,
            defaultSampleRate=48000.0,
            defaultLowInputLatency=0.01,
            defaultLowOutputLatency=0.01,
            defaultHighInputLatency=0.1,
            defaultHighOutputLatency=0.1
        )
        
        mock_pa.add_mock_device(new_device)
        assert mock_pa.get_device_count() == initial_count + 1
        
        # Remove device
        mock_pa.remove_mock_device(0)
        assert mock_pa.get_device_count() == initial_count


class TestMockAudioStream:
    """Test MockAudioStream functionality"""
    
    @pytest.fixture
    def mock_stream(self):
        """Create mock audio stream"""
        pa = MockPortAudio()
        pa.initialize()
        
        stream = pa.open(
            rate=48000,
            channels=2,
            format=AudioFormat.FLOAT32,
            input=True,
            frames_per_buffer=1024
        )
        
        yield stream
        
        stream.close()
        pa.terminate()
    
    def test_stream_lifecycle(self, mock_stream):
        """Test stream start/stop lifecycle"""
        assert not mock_stream.is_active
        assert mock_stream.is_stopped
        
        # Start stream
        mock_stream.start()
        assert mock_stream.is_active
        assert not mock_stream.is_stopped
        
        # Stop stream
        mock_stream.stop()
        assert not mock_stream.is_active
        
        # Close stream
        mock_stream.close()
        assert mock_stream.is_stopped
    
    def test_stream_double_start_error(self, mock_stream):
        """Test error when starting already active stream"""
        mock_stream.start()
        
        with pytest.raises(RuntimeError, match="Stream already active"):
            mock_stream.start()
        
        mock_stream.stop()
    
    def test_stream_device_unavailable_error(self, mock_stream):
        """Test device unavailable error"""
        mock_stream.simulate_device_unavailable = True
        
        with pytest.raises(RuntimeError, match="Device unavailable"):
            mock_stream.start()
    
    def test_stream_read_operations(self, mock_stream):
        """Test stream read operations"""
        mock_stream.start()
        
        # Test read availability
        available = mock_stream.get_read_available()
        assert available > 0
        
        # Test reading data
        data = mock_stream.read(512)
        assert isinstance(data, bytes)
        assert len(data) > 0
        
        mock_stream.stop()
    
    def test_stream_read_inactive_error(self, mock_stream):
        """Test read error when stream inactive"""
        with pytest.raises(RuntimeError, match="Stream not active"):
            mock_stream.read(512)
    
    def test_stream_overflow_simulation(self, mock_stream):
        """Test input overflow simulation"""
        mock_stream.simulate_overflow = True
        mock_stream.start()
        
        with pytest.raises(RuntimeError, match="Input overflowed"):
            mock_stream.read(512, exception_on_overflow=True)
        
        # Should not raise exception when disabled
        data = mock_stream.read(512, exception_on_overflow=False)
        assert isinstance(data, bytes)
        
        mock_stream.stop()
    
    def test_stream_write_operations(self, mock_stream):
        """Test stream write operations"""
        # Create output stream
        pa = MockPortAudio()
        pa.initialize()
        
        output_stream = pa.open(
            rate=48000,
            channels=2,
            format=AudioFormat.FLOAT32,
            output=True,
            frames_per_buffer=1024
        )
        
        output_stream.start()
        
        # Test write availability
        available = output_stream.get_write_available()
        assert available > 0
        
        # Test writing data
        test_data = np.zeros((512, 2), dtype=np.float32)
        output_stream.write(test_data.tobytes(), 512)
        
        output_stream.close()
        pa.terminate()
    
    def test_stream_underrun_simulation(self, mock_stream):
        """Test output underrun simulation"""
        pa = MockPortAudio()
        pa.initialize()
        
        output_stream = pa.open(
            rate=48000,
            channels=2,
            format=AudioFormat.FLOAT32,
            output=True,
            frames_per_buffer=1024
        )
        
        output_stream.simulate_underrun = True
        output_stream.start()
        
        test_data = np.zeros((512, 2), dtype=np.float32)
        
        with pytest.raises(RuntimeError, match="Output underflowed"):
            output_stream.write(test_data.tobytes(), 512, exception_on_underrun=True)
        
        # Should not raise exception when disabled
        output_stream.write(test_data.tobytes(), 512, exception_on_underrun=False)
        
        output_stream.close()
        pa.terminate()
    
    def test_stream_callback_functionality(self):
        """Test stream callback functionality"""
        callback_called = threading.Event()
        callback_data = []
        
        def stream_callback(in_data, frame_count, time_info, status_flags):
            callback_called.set()
            callback_data.append((in_data, frame_count, status_flags))
            return (None, 0)  # paContinue
        
        pa = MockPortAudio()
        pa.initialize()
        
        stream = pa.open(
            rate=48000,
            channels=2,
            format=AudioFormat.FLOAT32,
            input=True,
            frames_per_buffer=1024,
            stream_callback=stream_callback
        )
        
        stream.start()
        
        # Wait for callback
        assert callback_called.wait(timeout=1.0)
        assert len(callback_data) > 0
        
        # Check callback parameters
        in_data, frame_count, status_flags = callback_data[0]
        assert in_data is not None
        assert frame_count == 1024
        assert isinstance(status_flags, int)
        
        stream.close()
        pa.terminate()
    
    def test_stream_callback_error_handling(self):
        """Test stream callback error handling"""
        def error_callback(in_data, frame_count, time_info, status_flags):
            raise ValueError("Test callback error")
        
        pa = MockPortAudio()
        pa.initialize()
        
        stream = pa.open(
            rate=48000,
            channels=2,
            format=AudioFormat.FLOAT32,
            input=True,
            frames_per_buffer=1024,
            stream_callback=error_callback
        )
        
        stream.start()
        time.sleep(0.1)  # Let callback run and handle error
        
        # Stream should handle callback errors gracefully
        assert stream.is_active  # Should still be active initially
        
        stream.close()
        pa.terminate()
    
    def test_audio_data_generation(self, mock_stream):
        """Test audio data generation quality"""
        mock_stream.start()
        
        # Read multiple frames
        frames_data = []
        for _ in range(5):
            data = mock_stream.read(1024)
            frames_data.append(data)
        
        mock_stream.stop()
        
        # Verify data consistency
        assert len(frames_data) == 5
        for data in frames_data:
            assert len(data) > 0
            
            # Convert to numpy array
            audio_array = np.frombuffer(data, dtype=np.float32)
            audio_array = audio_array.reshape(-1, mock_stream.channels)
            
            # Check audio properties
            assert audio_array.shape[1] == mock_stream.channels
            assert np.max(np.abs(audio_array)) <= 1.0  # No clipping
            assert np.std(audio_array) > 0.01  # Has signal content


class TestMockPyAudio:
    """Test MockPyAudio compatibility layer"""
    
    @pytest.fixture
    def mock_pyaudio(self):
        """Create MockPyAudio instance"""
        pa = MockPyAudio()
        yield pa
        pa.terminate()
    
    def test_pyaudio_compatibility(self, mock_pyaudio):
        """Test PyAudio API compatibility"""
        # Test constants
        assert hasattr(mock_pyaudio, 'paFloat32')
        assert hasattr(mock_pyaudio, 'paInt16')
        assert hasattr(mock_pyaudio, 'paContinue')
        
        # Test methods
        assert callable(mock_pyaudio.get_version_text)
        assert callable(mock_pyaudio.get_device_count)
        assert callable(mock_pyaudio.get_device_info_by_index)
    
    def test_device_info_dict_format(self, mock_pyaudio):
        """Test device info dictionary format"""
        device_count = mock_pyaudio.get_device_count()
        assert device_count > 0
        
        device_info = mock_pyaudio.get_device_info_by_index(0)
        
        # Check required keys
        required_keys = [
            'index', 'name', 'hostApi', 'maxInputChannels', 
            'maxOutputChannels', 'defaultSampleRate'
        ]
        
        for key in required_keys:
            assert key in device_info
        
        # Check data types
        assert isinstance(device_info['index'], int)
        assert isinstance(device_info['name'], str)
        assert isinstance(device_info['maxInputChannels'], int)
        assert isinstance(device_info['defaultSampleRate'], float)
    
    def test_default_device_info(self, mock_pyaudio):
        """Test default device info methods"""
        input_info = mock_pyaudio.get_default_input_device_info()
        output_info = mock_pyaudio.get_default_output_device_info()
        
        assert isinstance(input_info, dict)
        assert isinstance(output_info, dict)
        assert input_info['maxInputChannels'] > 0
        assert output_info['maxOutputChannels'] > 0
    
    def test_stream_opening_compatibility(self, mock_pyaudio):
        """Test stream opening with PyAudio-style parameters"""
        stream = mock_pyaudio.open(
            format=mock_pyaudio.paFloat32,
            channels=2,
            rate=48000,
            input=True,
            frames_per_buffer=1024
        )
        
        assert isinstance(stream, MockAudioStream)
        assert stream.format == AudioFormat.FLOAT32
        assert stream.channels == 2
        assert stream.rate == 48000
        
        stream.close()


class TestErrorSimulation:
    """Test error simulation capabilities"""
    
    def test_comprehensive_error_scenarios(self):
        """Test various error scenarios"""
        pa = MockPortAudio()
        
        # Test initialization errors
        pa.set_error_simulation(init_error=True)
        with pytest.raises(RuntimeError):
            pa.initialize()
        
        # Reset and initialize properly
        pa.set_error_simulation(init_error=False)
        pa.initialize()
        
        # Test device errors
        pa.set_error_simulation(device_error=True)
        with pytest.raises(RuntimeError):
            pa.get_device_info_by_index(0)
        
        pa.terminate()
    
    def test_stream_error_simulation(self):
        """Test stream-level error simulation"""
        pa = MockPortAudio()
        pa.initialize()
        
        stream = pa.open(
            rate=48000,
            channels=2,
            format=AudioFormat.FLOAT32,
            input=True,
            frames_per_buffer=1024
        )
        
        # Test various stream errors
        stream.simulate_device_unavailable = True
        with pytest.raises(RuntimeError):
            stream.start()
        
        # Reset and test overflow
        stream.simulate_device_unavailable = False
        stream.simulate_overflow = True
        stream.start()
        
        with pytest.raises(RuntimeError):
            stream.read(512)
        
        stream.close()
        pa.terminate()
    
    def test_random_error_injection(self):
        """Test random error injection"""
        pa = MockPortAudio()
        pa.initialize()
        
        stream = pa.open(
            rate=48000,
            channels=2,
            format=AudioFormat.FLOAT32,
            input=True,
            frames_per_buffer=1024
        )
        
        # Set high error probability
        stream.error_probability = 0.5
        stream.start()
        
        # Read multiple times - some should have errors in callback
        error_detected = False
        for _ in range(10):
            try:
                data = stream.read(512, exception_on_overflow=False)
                # Check if we can detect simulated errors indirectly
                if len(data) == 0:
                    error_detected = True
            except:
                error_detected = True
        
        stream.close()
        pa.terminate()


@pytest.mark.integration
class TestMockPortAudioIntegration:
    """Integration tests for MockPortAudio with real audio processing code"""
    
    def test_mock_integration_with_device_manager(self):
        """Test MockPortAudio integration with device manager"""
        # This would test integration with actual device manager code
        # using MockPortAudio instead of real PortAudio
        
        with patch('pyaudio.PyAudio', MockPyAudio):
            # Import and test device manager with mocked PyAudio
            from src.audio_core.device_manager import DeviceManager
            
            device_manager = DeviceManager()
            devices = device_manager.scan_devices()
            
            assert len(devices) > 0
            assert all(hasattr(device, 'name') for device in devices)
    
    def test_mock_integration_with_capture_service(self):
        """Test MockPortAudio integration with capture service"""
        with patch('pyaudio.PyAudio', MockPyAudio):
            # This would test the actual capture service
            # Implementation depends on the actual capture service code
            pass