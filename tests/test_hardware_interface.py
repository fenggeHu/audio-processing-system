"""
Tests for Hardware Abstraction Layer

Test suite for the hardware interface and abstraction layer components.
"""

import pytest
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.audio_core.hardware_interface import (
    HardwareAbstractionLayer,
    DelayCompensator,
    ClockSynchronizer,
    ErrorRecoverySystem,
    PerformanceMonitor,
    TimingInfo,
    PerformanceMetrics,
    ErrorInfo,
    ClockSyncStatus,
    RecoveryAction
)
from src.audio_core.hardware_devices import (
    MockAudioDevice,
    create_mock_devices,
    create_hardware_device
)
from src.audio_core.models import AudioDevice, DeviceType, AudioFrame
from src.audio_core.interfaces import ComponentState


class TestDelayCompensator:
    """Test delay compensation system"""
    
    def test_delay_compensator_initialization(self):
        """Test delay compensator initialization"""
        compensator = DelayCompensator()
        assert compensator._compensation_enabled == True
        assert compensator._reference_device is None
        assert len(compensator._device_delays) == 0
    
    def test_set_reference_device(self):
        """Test setting reference device"""
        compensator = DelayCompensator()
        compensator.set_reference_device("device_1")
        assert compensator._reference_device == "device_1"
    
    def test_measure_device_delay(self):
        """Test device delay measurement"""
        compensator = DelayCompensator()
        timing_info = TimingInfo(
            device_id="device_1",
            sample_rate=48000,
            buffer_size=256,
            input_latency_ms=5.0,
            output_latency_ms=3.0
        )
        
        delay = compensator.measure_device_delay("device_1", timing_info)
        assert delay == 8.0  # 5.0 + 3.0
        assert compensator._device_delays["device_1"] == 8.0
    
    def test_calculate_compensation_delay(self):
        """Test compensation delay calculation"""
        compensator = DelayCompensator()
        compensator.set_reference_device("device_1")
        
        # Set up device delays
        compensator._device_delays["device_1"] = 10.0  # Reference device
        compensator._device_delays["device_2"] = 5.0   # Faster device
        compensator._device_delays["device_3"] = 15.0  # Slower device
        
        # Device 2 should get compensation (reference - device = 10 - 5 = 5)
        assert compensator.calculate_compensation_delay("device_2") == 5.0
        
        # Device 3 should get no compensation (reference - device = 10 - 15 = -5, but min is 0)
        assert compensator.calculate_compensation_delay("device_3") == 0.0
        
        # Reference device should get no compensation
        assert compensator.calculate_compensation_delay("device_1") == 0.0


class TestClockSynchronizer:
    """Test clock synchronization system"""
    
    def test_clock_synchronizer_initialization(self):
        """Test clock synchronizer initialization"""
        synchronizer = ClockSynchronizer()
        assert synchronizer._master_clock is None
        assert synchronizer._sync_active == False
        assert len(synchronizer._device_clocks) == 0
    
    def test_set_master_clock(self):
        """Test setting master clock"""
        synchronizer = ClockSynchronizer()
        synchronizer.set_master_clock("device_1")
        assert synchronizer._master_clock == "device_1"
    
    def test_register_device_clock(self):
        """Test registering device clock"""
        synchronizer = ClockSynchronizer()
        timing_info = TimingInfo(
            device_id="device_1",
            sample_rate=48000,
            buffer_size=256
        )
        
        synchronizer.register_device_clock("device_1", timing_info)
        assert "device_1" in synchronizer._device_clocks
        assert synchronizer._master_clock == "device_1"  # First device becomes master
    
    def test_start_stop_synchronization(self):
        """Test starting and stopping synchronization"""
        synchronizer = ClockSynchronizer(sync_interval=0.1)
        
        # Start synchronization
        synchronizer.start_synchronization()
        assert synchronizer._sync_active == True
        assert synchronizer._sync_thread is not None
        
        # Wait a bit for thread to start
        time.sleep(0.05)
        
        # Stop synchronization
        synchronizer.stop_synchronization()
        assert synchronizer._sync_active == False


class TestErrorRecoverySystem:
    """Test error recovery system"""
    
    def test_error_recovery_initialization(self):
        """Test error recovery system initialization"""
        recovery = ErrorRecoverySystem()
        assert len(recovery._error_history) == 0
        assert len(recovery._recovery_strategies) > 0
        assert recovery._max_recovery_attempts == 3
    
    def test_report_error(self):
        """Test error reporting"""
        recovery = ErrorRecoverySystem()
        
        # Mock recovery callback
        recovery_callback = Mock(return_value=True)
        recovery.register_recovery_callback(recovery_callback)
        
        # Report error
        result = recovery.report_error("buffer_underrun", "Buffer underrun detected", "device_1", "medium")
        
        # Check error was recorded
        assert len(recovery._error_history) == 1
        error = recovery._error_history[0]
        assert error.error_type == "buffer_underrun"
        assert error.device_id == "device_1"
        assert error.severity == "medium"
        
        # Check recovery was attempted
        assert recovery_callback.called
    
    def test_critical_error_no_recovery(self):
        """Test that critical errors don't trigger recovery"""
        recovery = ErrorRecoverySystem()
        
        # Mock recovery callback
        recovery_callback = Mock(return_value=True)
        recovery.register_recovery_callback(recovery_callback)
        
        # Report critical error
        result = recovery.report_error("critical_error", "Critical system failure", "device_1", "critical")
        
        # Check error was recorded but no recovery attempted
        assert len(recovery._error_history) == 1
        assert not recovery_callback.called


class TestPerformanceMonitor:
    """Test performance monitoring system"""
    
    def test_performance_monitor_initialization(self):
        """Test performance monitor initialization"""
        monitor = PerformanceMonitor(monitor_interval=0.1)
        assert monitor.monitor_interval == 0.1
        assert monitor._monitoring_active == False
        assert len(monitor._metrics) == 0
        assert len(monitor._devices) == 0
    
    def test_register_device(self):
        """Test device registration"""
        monitor = PerformanceMonitor()
        
        # Create mock device
        device_info = AudioDevice(
            device_id="test_device",
            name="Test Device",
            device_type=DeviceType.MICROPHONE,
            is_input=True,
            is_output=False
        )
        mock_device = MockAudioDevice(device_info)
        
        # Register device
        monitor.register_device("test_device", mock_device)
        
        assert "test_device" in monitor._devices
        assert "test_device" in monitor._metrics
        assert monitor._metrics["test_device"].device_id == "test_device"
    
    def test_start_stop_monitoring(self):
        """Test starting and stopping monitoring"""
        monitor = PerformanceMonitor(monitor_interval=0.1)
        
        # Start monitoring
        monitor.start_monitoring()
        assert monitor._monitoring_active == True
        assert monitor._monitor_thread is not None
        
        # Wait a bit for thread to start
        time.sleep(0.05)
        
        # Stop monitoring
        monitor.stop_monitoring()
        assert monitor._monitoring_active == False


class TestMockAudioDevice:
    """Test mock audio device implementation"""
    
    def test_mock_device_initialization(self):
        """Test mock device initialization"""
        device_info = AudioDevice(
            device_id="test_device",
            name="Test Device",
            device_type=DeviceType.MICROPHONE,
            is_input=True,
            is_output=False,
            max_input_channels=2
        )
        
        mock_device = MockAudioDevice(device_info)
        assert mock_device.get_device_info() == device_info
        assert mock_device._active == False
    
    def test_device_lifecycle(self):
        """Test device initialization, start, and stop"""
        device_info = AudioDevice(
            device_id="test_device",
            name="Test Device",
            device_type=DeviceType.MICROPHONE,
            is_input=True,
            is_output=False,
            max_input_channels=2
        )
        
        mock_device = MockAudioDevice(device_info)
        
        # Initialize
        config = {
            'sample_rate': 48000,
            'channels': 2,
            'buffer_size': 256
        }
        assert mock_device.initialize(config) == True
        assert mock_device._sample_rate == 48000
        
        # Start
        assert mock_device.start() == True
        assert mock_device._active == True
        
        # Stop
        assert mock_device.stop() == True
        assert mock_device._active == False
    
    def test_input_device_capture(self):
        """Test input device audio capture"""
        device_info = AudioDevice(
            device_id="input_device",
            name="Input Device",
            device_type=DeviceType.MICROPHONE,
            is_input=True,
            is_output=False,
            max_input_channels=2
        )
        
        mock_device = MockAudioDevice(device_info)
        config = {'sample_rate': 48000, 'channels': 2, 'buffer_size': 256}
        
        # Initialize and start
        assert mock_device.initialize(config) == True
        assert mock_device.start() == True
        
        # Wait for some frames to be captured
        time.sleep(0.1)
        
        # Read frame
        frame = mock_device.read_frame()
        assert frame is not None
        assert frame.sample_rate == 48000
        assert frame.channels == 2
        
        # Stop device
        mock_device.stop()
    
    def test_output_device_playback(self):
        """Test output device audio playback"""
        device_info = AudioDevice(
            device_id="output_device",
            name="Output Device",
            device_type=DeviceType.SPEAKER,
            is_input=False,
            is_output=True,
            max_output_channels=2
        )
        
        mock_device = MockAudioDevice(device_info)
        config = {'sample_rate': 48000, 'channels': 2, 'buffer_size': 256}
        
        # Initialize and start
        assert mock_device.initialize(config) == True
        assert mock_device.start() == True
        
        # Create test frame
        import numpy as np
        audio_data = np.random.random((256, 2)).astype(np.float32)
        frame = AudioFrame(
            frame_id=1,
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=2,
            bit_depth=24,
            data=audio_data
        )
        
        # Write frame
        assert mock_device.write_frame(frame) == True
        
        # Stop device
        mock_device.stop()
    
    def test_timing_calibration(self):
        """Test timing calibration"""
        device_info = AudioDevice(
            device_id="test_device",
            name="Test Device",
            device_type=DeviceType.MICROPHONE,
            is_input=True,
            is_output=False
        )
        
        mock_device = MockAudioDevice(device_info)
        config = {'sample_rate': 48000, 'channels': 2, 'buffer_size': 256}
        
        # Initialize
        assert mock_device.initialize(config) == True
        
        # Get initial timing info
        timing_info = mock_device.get_timing_info()
        assert timing_info is not None
        
        # Calibrate timing
        assert mock_device.calibrate_timing() == True
        
        # Check that timing was reset
        updated_timing = mock_device.get_timing_info()
        assert updated_timing.sync_status == ClockSyncStatus.SYNCED
    
    def test_buffer_reset(self):
        """Test buffer reset functionality"""
        device_info = AudioDevice(
            device_id="test_device",
            name="Test Device",
            device_type=DeviceType.MICROPHONE,
            is_input=True,
            is_output=False
        )
        
        mock_device = MockAudioDevice(device_info)
        config = {'sample_rate': 48000, 'channels': 2, 'buffer_size': 256}
        
        # Initialize and start
        assert mock_device.initialize(config) == True
        assert mock_device.start() == True
        
        # Wait for some frames
        time.sleep(0.1)
        
        # Reset buffers
        assert mock_device.reset_buffers() == True
        
        # Check that queue is empty
        assert len(mock_device._frame_queue) == 0
        
        mock_device.stop()


class TestHardwareAbstractionLayer:
    """Test hardware abstraction layer"""
    
    def test_hal_initialization(self):
        """Test HAL initialization"""
        hal = HardwareAbstractionLayer()
        assert hal.get_state() == ComponentState.UNINITIALIZED
        
        # Initialize
        config = {'enable_delay_compensation': True}
        assert hal.init(config) == True
        assert hal.get_state() == ComponentState.READY
    
    def test_hal_lifecycle(self):
        """Test HAL start/stop lifecycle"""
        hal = HardwareAbstractionLayer()
        
        # Initialize
        config = {'enable_delay_compensation': True}
        assert hal.init(config) == True
        
        # Start
        assert hal.start() == True
        assert hal.get_state() == ComponentState.RUNNING
        
        # Stop
        assert hal.stop() == True
        assert hal.get_state() == ComponentState.STOPPED
        
        # Cleanup
        assert hal.cleanup() == True
    
    def test_device_registration(self):
        """Test device registration with HAL"""
        hal = HardwareAbstractionLayer()
        
        # Initialize HAL
        config = {'enable_delay_compensation': True}
        assert hal.init(config) == True
        
        # Create mock device
        device_info = AudioDevice(
            device_id="test_device",
            name="Test Device",
            device_type=DeviceType.MICROPHONE,
            is_input=True,
            is_output=False
        )
        mock_device = MockAudioDevice(device_info)
        
        # Register device
        device_config = {'sample_rate': 48000, 'channels': 2, 'buffer_size': 256}
        assert hal.register_device("test_device", mock_device, device_config) == True
        
        # Check device is registered
        registered_device = hal.get_device("test_device")
        assert registered_device is not None
        assert registered_device == mock_device
        
        # Unregister device
        assert hal.unregister_device("test_device") == True
        assert hal.get_device("test_device") is None
    
    def test_master_clock_setting(self):
        """Test setting master clock device"""
        hal = HardwareAbstractionLayer()
        
        # Initialize HAL
        config = {'enable_delay_compensation': True}
        assert hal.init(config) == True
        
        # Create and register mock device
        device_info = AudioDevice(
            device_id="master_device",
            name="Master Device",
            device_type=DeviceType.MICROPHONE,
            is_input=True,
            is_output=False
        )
        mock_device = MockAudioDevice(device_info)
        device_config = {'sample_rate': 48000, 'channels': 2, 'buffer_size': 256}
        
        assert hal.register_device("master_device", mock_device, device_config) == True
        
        # Set as master clock
        assert hal.set_master_clock("master_device") == True
        
        # Try to set non-existent device as master
        assert hal.set_master_clock("non_existent") == False
    
    def test_error_reporting(self):
        """Test error reporting and recovery"""
        hal = HardwareAbstractionLayer()
        
        # Initialize HAL
        config = {'enable_delay_compensation': True}
        assert hal.init(config) == True
        
        # Report error
        result = hal.report_device_error("test_device", "buffer_underrun", "Test error", "medium")
        
        # Check error history
        error_history = hal.get_error_history("test_device")
        assert len(error_history) > 0
        assert error_history[0].error_type == "buffer_underrun"
        assert error_history[0].device_id == "test_device"
    
    def test_performance_monitoring(self):
        """Test performance monitoring integration"""
        hal = HardwareAbstractionLayer()
        
        # Initialize and start HAL
        config = {'enable_delay_compensation': True}
        assert hal.init(config) == True
        assert hal.start() == True
        
        # Create and register mock device
        device_info = AudioDevice(
            device_id="perf_device",
            name="Performance Device",
            device_type=DeviceType.MICROPHONE,
            is_input=True,
            is_output=False
        )
        mock_device = MockAudioDevice(device_info)
        device_config = {'sample_rate': 48000, 'channels': 2, 'buffer_size': 256}
        
        assert hal.register_device("perf_device", mock_device, device_config) == True
        
        # Wait for monitoring to collect some data
        time.sleep(0.1)
        
        # Get performance metrics
        metrics = hal.get_device_performance("perf_device")
        assert metrics is not None
        assert metrics.device_id == "perf_device"
        
        # Get all metrics
        all_metrics = hal.get_all_performance_metrics()
        assert "perf_device" in all_metrics
        
        hal.stop()


class TestDeviceFactory:
    """Test device factory functions"""
    
    def test_create_hardware_device(self):
        """Test hardware device creation"""
        # Test USB device creation
        usb_device_info = AudioDevice(
            device_id="usb_device",
            name="USB Device",
            device_type=DeviceType.USB_AUDIO,
            is_input=True,
            is_output=True
        )
        
        usb_device = create_hardware_device(usb_device_info)
        assert usb_device is not None
        assert usb_device.get_device_info() == usb_device_info
        
        # Test microphone device creation
        mic_device_info = AudioDevice(
            device_id="mic_device",
            name="Microphone",
            device_type=DeviceType.MICROPHONE,
            is_input=True,
            is_output=False
        )
        
        mic_device = create_hardware_device(mic_device_info)
        assert mic_device is not None
        assert mic_device.get_device_info() == mic_device_info
    
    def test_create_mock_devices(self):
        """Test mock device creation"""
        mock_devices = create_mock_devices()
        
        assert len(mock_devices) == 3
        assert "mock_input_0" in mock_devices
        assert "mock_output_0" in mock_devices
        assert "mock_usb_0" in mock_devices
        
        # Test input device
        input_device = mock_devices["mock_input_0"]
        device_info = input_device.get_device_info()
        assert device_info.is_input == True
        assert device_info.is_output == False
        
        # Test output device
        output_device = mock_devices["mock_output_0"]
        device_info = output_device.get_device_info()
        assert device_info.is_input == False
        assert device_info.is_output == True
        
        # Test USB device
        usb_device = mock_devices["mock_usb_0"]
        device_info = usb_device.get_device_info()
        assert device_info.is_input == True
        assert device_info.is_output == True


if __name__ == "__main__":
    pytest.main([__file__])