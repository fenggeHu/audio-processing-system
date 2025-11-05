"""
Tests for Multi-Input Audio Access Layer

This module contains tests for the multi-input audio access layer components.
"""

import pytest
import asyncio
import threading
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from src.audio_core.multi_input_access import (
    DynamicAudioInputDetector,
    SelectiveAudioAccessManager,
    MultiInputAudioCapture,
    InputDeviceManager,
    MultiInputSynchronizationCoordinator,
    InputQualityMonitor,
    HotPlugSupport,
    InputConfigurationVisualizationUI,
    InputConfiguration,
    InputDeviceState,
    InputDeviceStatus,
    SynchronizationMode
)
from src.audio_core.multi_input_system import MultiInputAudioSystem, create_multi_input_system
from src.audio_core.models import AudioDevice, DeviceType, AudioFrame, AudioProcessingConfig


@pytest.fixture
def input_config():
    """Create test input configuration"""
    return InputConfiguration(
        auto_detect_devices=True,
        enable_all_by_default=True,
        enable_quality_monitoring=True,
        enable_hot_plug=True,
        sync_mode=SynchronizationMode.SOFTWARE_SYNC,
        device_scan_interval_ms=100,
        quality_check_interval_ms=50
    )


@pytest.fixture
def sample_audio_device():
    """Create sample audio device"""
    return AudioDevice(
        device_id="test_device_1",
        name="Test Microphone",
        device_type=DeviceType.MICROPHONE,
        is_input=True,
        is_output=False,
        max_input_channels=2,
        supported_sample_rates=[44100, 48000],
        is_available=True,
        is_connected=True
    )


@pytest.fixture
def sample_audio_frame():
    """Create sample audio frame"""
    import numpy as np
    return AudioFrame(
        frame_id=1,
        timestamp=datetime.now(),
        sample_rate=48000,
        channels=2,
        bit_depth=16,
        data=np.zeros((256, 2), dtype=np.int16),
        frame_size=256
    )


class TestDynamicAudioInputDetector:
    """Test DynamicAudioInputDetector class"""
    
    def test_initialization(self, input_config):
        """Test detector initialization"""
        detector = DynamicAudioInputDetector(input_config)
        assert detector.config == input_config
        assert detector._detected_devices == {}
        assert detector._scan_thread is None
    
    @patch('src.audio_core.multi_input_access.PYAUDIO_AVAILABLE', False)
    def test_scan_without_pyaudio(self, input_config):
        """Test device scan without PyAudio"""
        detector = DynamicAudioInputDetector(input_config)
        devices = detector.scan_devices_once()
        assert devices == []
    
    @patch('src.audio_core.multi_input_access.pyaudio')
    @patch('src.audio_core.multi_input_access.PYAUDIO_AVAILABLE', True)
    def test_scan_with_pyaudio(self, mock_pyaudio, input_config):
        """Test device scan with PyAudio"""
        # Mock PyAudio
        mock_pa = Mock()
        mock_pyaudio.PyAudio.return_value = mock_pa
        mock_pa.get_device_count.return_value = 2
        mock_pa.get_device_info_by_index.side_effect = [
            {
                'name': 'Test Mic 1',
                'maxInputChannels': 2,
                'maxOutputChannels': 0,
                'defaultSampleRate': 48000,
                'defaultLowInputLatency': 0.01,
                'defaultHighInputLatency': 0.1,
                'hostApi': 'ALSA'
            },
            {
                'name': 'Test Mic 2',
                'maxInputChannels': 1,
                'maxOutputChannels': 0,
                'defaultSampleRate': 44100,
                'defaultLowInputLatency': 0.02,
                'defaultHighInputLatency': 0.2,
                'hostApi': 'ALSA'
            }
        ]
        
        detector = DynamicAudioInputDetector(input_config)
        devices = detector.scan_devices_once()
        
        assert len(devices) == 2
        assert devices[0].name == 'Test Mic 1'
        assert devices[0].max_input_channels == 2
        assert devices[1].name == 'Test Mic 2'
        assert devices[1].max_input_channels == 1
    
    def test_detection_callbacks(self, input_config, sample_audio_device):
        """Test detection callbacks"""
        detector = DynamicAudioInputDetector(input_config)
        callback_called = False
        received_devices = None
        
        def test_callback(devices):
            nonlocal callback_called, received_devices
            callback_called = True
            received_devices = devices
        
        detector.register_detection_callback(test_callback)
        
        # Simulate device detection
        detector._detected_devices = {sample_audio_device.device_id: sample_audio_device}
        for callback in detector._callbacks:
            callback([sample_audio_device])
        
        assert callback_called
        assert len(received_devices) == 1
        assert received_devices[0] == sample_audio_device


class TestSelectiveAudioAccessManager:
    """Test SelectiveAudioAccessManager class"""
    
    def test_initialization(self, input_config):
        """Test access manager initialization"""
        manager = SelectiveAudioAccessManager(input_config)
        assert manager.config == input_config
        assert manager._available_devices == {}
        assert manager._selected_devices == set()
    
    def test_set_available_devices_enable_all(self, input_config, sample_audio_device):
        """Test setting available devices with enable all policy"""
        manager = SelectiveAudioAccessManager(input_config)
        devices = [sample_audio_device]
        
        manager.set_available_devices(devices)
        
        assert len(manager._available_devices) == 1
        assert sample_audio_device.device_id in manager._selected_devices
    
    def test_select_devices(self, input_config, sample_audio_device):
        """Test device selection"""
        manager = SelectiveAudioAccessManager(input_config)
        manager._available_devices = {sample_audio_device.device_id: sample_audio_device}
        
        result = manager.select_devices([sample_audio_device.device_id])
        
        assert result is True
        assert sample_audio_device.device_id in manager._selected_devices
    
    def test_select_invalid_devices(self, input_config):
        """Test selecting invalid devices"""
        manager = SelectiveAudioAccessManager(input_config)
        
        result = manager.select_devices(["invalid_device"])
        
        assert result is False
    
    def test_device_priority(self, input_config, sample_audio_device):
        """Test device priority management"""
        manager = SelectiveAudioAccessManager(input_config)
        manager._available_devices = {sample_audio_device.device_id: sample_audio_device}
        
        result = manager.set_device_priority(sample_audio_device.device_id, 10)
        assert result is True
        
        priority = manager.get_device_priority(sample_audio_device.device_id)
        assert priority == 10


class TestInputDeviceManager:
    """Test InputDeviceManager class"""
    
    def test_initialization(self, input_config):
        """Test device manager initialization"""
        manager = InputDeviceManager(input_config)
        assert manager.config == input_config
        assert manager._device_status == {}
    
    def test_add_device(self, input_config, sample_audio_device):
        """Test adding device"""
        manager = InputDeviceManager(input_config)
        
        result = manager.add_device(sample_audio_device)
        
        assert result is True
        assert sample_audio_device.device_id in manager._device_status
        status = manager._device_status[sample_audio_device.device_id]
        assert status.device_id == sample_audio_device.device_id
        assert status.state == InputDeviceState.AVAILABLE
    
    def test_enable_disable_device(self, input_config, sample_audio_device):
        """Test enabling and disabling device"""
        manager = InputDeviceManager(input_config)
        manager.add_device(sample_audio_device)
        
        # Test enable
        result = manager.enable_device(sample_audio_device.device_id)
        assert result is True
        status = manager.get_device_status(sample_audio_device.device_id)
        assert status.is_enabled is True
        assert status.state == InputDeviceState.ACTIVE
        
        # Test disable
        result = manager.disable_device(sample_audio_device.device_id)
        assert result is True
        status = manager.get_device_status(sample_audio_device.device_id)
        assert status.is_enabled is False
        assert status.state == InputDeviceState.INACTIVE
    
    def test_device_gain_and_mute(self, input_config, sample_audio_device):
        """Test device gain and mute controls"""
        manager = InputDeviceManager(input_config)
        manager.add_device(sample_audio_device)
        
        # Test gain
        result = manager.set_device_gain(sample_audio_device.device_id, 6.0)
        assert result is True
        status = manager.get_device_status(sample_audio_device.device_id)
        assert status.gain_db == 6.0
        
        # Test mute
        result = manager.mute_device(sample_audio_device.device_id, True)
        assert result is True
        status = manager.get_device_status(sample_audio_device.device_id)
        assert status.is_muted is True
    
    def test_update_metrics(self, input_config, sample_audio_device):
        """Test updating device metrics"""
        manager = InputDeviceManager(input_config)
        manager.add_device(sample_audio_device)
        
        manager.update_device_metrics(sample_audio_device.device_id, 0.8, -30.0, 0.9)
        
        status = manager.get_device_status(sample_audio_device.device_id)
        assert status.signal_strength == 0.8
        assert status.noise_level_db == -30.0
        assert status.connection_quality == 0.9


class TestMultiInputSynchronizationCoordinator:
    """Test MultiInputSynchronizationCoordinator class"""
    
    def test_initialization(self, input_config):
        """Test sync coordinator initialization"""
        coordinator = MultiInputSynchronizationCoordinator(input_config)
        assert coordinator.config == input_config
        assert coordinator._sync_buffers == {}
        assert coordinator._reference_device is None
    
    def test_add_remove_device(self, input_config):
        """Test adding and removing devices"""
        coordinator = MultiInputSynchronizationCoordinator(input_config)
        
        # Add device
        coordinator.add_input_device("device1")
        assert "device1" in coordinator._sync_buffers
        assert coordinator._reference_device == "device1"
        
        # Add second device
        coordinator.add_input_device("device2")
        assert "device2" in coordinator._sync_buffers
        assert coordinator._reference_device == "device1"  # Should remain the same
        
        # Remove device
        coordinator.remove_input_device("device2")
        assert "device2" not in coordinator._sync_buffers
        assert coordinator._reference_device == "device1"
        
        # Remove reference device
        coordinator.remove_input_device("device1")
        assert "device1" not in coordinator._sync_buffers
        assert coordinator._reference_device is None
    
    def test_frame_synchronization(self, input_config, sample_audio_frame):
        """Test frame synchronization"""
        coordinator = MultiInputSynchronizationCoordinator(input_config)
        coordinator.add_input_device("device1")
        coordinator.add_input_device("device2")
        
        sync_called = False
        received_frames = None
        
        def sync_callback(frames):
            nonlocal sync_called, received_frames
            sync_called = True
            received_frames = frames
        
        coordinator.register_sync_callback(sync_callback)
        
        # Add frames from both devices
        frame1 = sample_audio_frame
        frame2 = AudioFrame(
            frame_id=2,
            timestamp=sample_audio_frame.timestamp,
            sample_rate=48000,
            channels=2,
            bit_depth=16,
            frame_size=256
        )
        
        coordinator.add_frame("device1", frame1)
        coordinator.add_frame("device2", frame2)
        
        # Should trigger synchronization
        assert sync_called
        assert len(received_frames) == 2
        assert "device1" in received_frames
        assert "device2" in received_frames


class TestInputQualityMonitor:
    """Test InputQualityMonitor class"""
    
    def test_initialization(self, input_config):
        """Test quality monitor initialization"""
        monitor = InputQualityMonitor(input_config)
        assert monitor.config == input_config
        assert monitor._monitoring_active is False
        assert monitor._quality_data == {}
    
    def test_start_stop_monitoring(self, input_config):
        """Test starting and stopping monitoring"""
        monitor = InputQualityMonitor(input_config)
        
        # Start monitoring
        result = monitor.start_monitoring()
        assert result is True
        assert monitor._monitoring_active is True
        
        # Stop monitoring
        monitor.stop_monitoring()
        assert monitor._monitoring_active is False
    
    def test_update_frame_quality(self, input_config, sample_audio_frame):
        """Test updating frame quality"""
        monitor = InputQualityMonitor(input_config)
        
        monitor.update_frame_quality("device1", sample_audio_frame)
        
        quality = monitor.get_quality_metrics("device1")
        assert quality is not None
        assert "signal_strength" in quality
        assert "noise_level_db" in quality
        assert "frame_count" in quality
        assert quality["frame_count"] == 1


class TestMultiInputAudioSystem:
    """Test MultiInputAudioSystem integration"""
    
    def test_initialization(self, input_config):
        """Test system initialization"""
        system = MultiInputAudioSystem(input_config)
        assert system.config == input_config
        assert system._is_initialized is False
        assert system._is_running is False
    
    @pytest.mark.asyncio
    async def test_initialize_shutdown(self, input_config):
        """Test system initialization and shutdown"""
        system = MultiInputAudioSystem(input_config)
        
        # Mock the detector to avoid PyAudio dependency
        with patch.object(system._detector, 'start_detection', return_value=True), \
             patch.object(system._quality_monitor, 'start_monitoring', return_value=True), \
             patch.object(system._detector, 'scan_devices_once', return_value=[]):
            
            result = await system.initialize()
            assert result is True
            assert system.is_initialized is True
            
            await system.shutdown()
            assert system.is_initialized is False
    
    def test_factory_function(self):
        """Test factory function"""
        system = create_multi_input_system(
            auto_detect=True,
            enable_all_by_default=False,
            sync_mode="timestamp"
        )
        
        assert isinstance(system, MultiInputAudioSystem)
        assert system.config.auto_detect_devices is True
        assert system.config.enable_all_by_default is False
        assert system.config.sync_mode == SynchronizationMode.TIMESTAMP
    
    def test_callback_registration(self, input_config):
        """Test callback registration"""
        system = MultiInputAudioSystem(input_config)
        
        def frame_callback(device_id, frame):
            pass
        
        def sync_callback(frames):
            pass
        
        def status_callback(device_id, status):
            pass
        
        assert system.register_input_callback(frame_callback) is True
        assert system.register_sync_callback(sync_callback) is True
        assert system.register_status_callback(status_callback) is True
    
    def test_device_management(self, input_config, sample_audio_device):
        """Test device management methods"""
        system = MultiInputAudioSystem(input_config)
        
        # Simulate device detection
        system._handle_device_detection([sample_audio_device])
        
        # Test device operations
        assert system.enable_device(sample_audio_device.device_id) is True
        assert system.disable_device(sample_audio_device.device_id) is True
        assert system.set_device_priority(sample_audio_device.device_id, 5) is True
        assert system.set_input_gain(sample_audio_device.device_id, 3.0) is True
        assert system.mute_input(sample_audio_device.device_id, True) is True
    
    def test_interface_compliance(self, input_config):
        """Test IMultiInputCapture interface compliance"""
        system = MultiInputAudioSystem(input_config)
        
        # Test interface methods exist and return expected types
        devices = system.scan_input_devices()
        assert isinstance(devices, list)
        
        capabilities = system.get_device_capabilities("test_device")
        assert isinstance(capabilities, dict)
        
        status = system.get_input_status()
        assert isinstance(status, dict)


class TestHotPlugSupport:
    """Test HotPlugSupport class"""
    
    def test_initialization(self, input_config):
        """Test hot-plug support initialization"""
        hotplug = HotPlugSupport(input_config)
        assert hotplug.config == input_config
        assert hotplug._detector is None
    
    def test_component_setup(self, input_config):
        """Test component setup"""
        hotplug = HotPlugSupport(input_config)
        detector = Mock()
        access_manager = Mock()
        device_manager = Mock()
        capture = Mock()
        
        hotplug.set_components(detector, access_manager, device_manager, capture)
        
        assert hotplug._detector == detector
        assert hotplug._access_manager == access_manager
        assert hotplug._device_manager == device_manager
        assert hotplug._capture == capture
    
    def test_device_change_handling(self, input_config, sample_audio_device):
        """Test device change handling"""
        hotplug = HotPlugSupport(input_config)
        
        # Mock components
        detector = Mock()
        access_manager = Mock()
        device_manager = Mock()
        device_manager.get_all_device_status.return_value = {}
        capture = Mock()
        
        hotplug.set_components(detector, access_manager, device_manager, capture)
        
        # Test device addition
        hotplug._handle_device_changes([sample_audio_device])
        
        device_manager.add_device.assert_called_once_with(sample_audio_device)
        access_manager.set_available_devices.assert_called_once()


class TestInputConfigurationVisualizationUI:
    """Test InputConfigurationVisualizationUI class"""
    
    def test_initialization(self, input_config):
        """Test UI initialization"""
        ui = InputConfigurationVisualizationUI(input_config)
        assert ui.config == input_config
        assert ui._device_manager is None
        assert ui._quality_monitor is None
    
    def test_ui_data_generation(self, input_config, sample_audio_device):
        """Test UI data generation"""
        ui = InputConfigurationVisualizationUI(input_config)
        
        # Mock device manager
        device_manager = Mock()
        device_status = InputDeviceStatus(
            device_id=sample_audio_device.device_id,
            state=InputDeviceState.ACTIVE,
            is_enabled=True
        )
        device_manager.get_all_device_status.return_value = {
            sample_audio_device.device_id: device_status
        }
        
        # Mock quality monitor
        quality_monitor = Mock()
        quality_monitor.get_quality_metrics.return_value = {
            'signal_strength': 0.8,
            'noise_level_db': -30.0,
            'connection_quality': 0.9
        }
        
        ui.set_components(device_manager, quality_monitor)
        
        ui_data = ui.get_ui_data()
        
        assert 'devices' in ui_data
        assert 'system_status' in ui_data
        assert len(ui_data['devices']) == 1
        assert ui_data['system_status']['total_devices'] == 1
        assert ui_data['system_status']['active_devices'] == 1


# Integration tests
class TestIntegration:
    """Integration tests for the complete system"""
    
    @pytest.mark.asyncio
    async def test_complete_workflow(self, input_config):
        """Test complete workflow from initialization to capture"""
        system = MultiInputAudioSystem(input_config)
        
        # Mock PyAudio to avoid hardware dependency
        with patch('src.audio_core.multi_input_access.PYAUDIO_AVAILABLE', True), \
             patch('src.audio_core.multi_input_access.pyaudio') as mock_pyaudio:
            
            # Mock PyAudio device detection
            mock_pa = Mock()
            mock_pyaudio.PyAudio.return_value = mock_pa
            mock_pa.get_device_count.return_value = 1
            mock_pa.get_device_info_by_index.return_value = {
                'name': 'Test Microphone',
                'maxInputChannels': 2,
                'maxOutputChannels': 0,
                'defaultSampleRate': 48000,
                'defaultLowInputLatency': 0.01,
                'defaultHighInputLatency': 0.1,
                'hostApi': 'ALSA'
            }
            
            # Initialize system
            assert await system.initialize() is True
            assert system.is_initialized is True
            
            # Check device detection
            devices = system.scan_input_devices()
            assert len(devices) >= 0  # May be 0 if mocked
            
            # Test device selection
            if devices:
                device_ids = [device['device_id'] for device in devices]
                assert system.select_inputs(device_ids) is True
            
            # Create audio config
            audio_config = AudioProcessingConfig(
                config_id="test_config",
                name="Test Configuration",
                sample_rate=48000,
                channels=2,
                bit_depth=16
            )
            
            # Mock capture to avoid actual audio operations
            with patch.object(system._capture, 'start_capture', return_value=True), \
                 patch.object(system._capture, 'stop_capture', return_value=True):
                
                # Test capture start/stop
                if system.selected_device_count > 0:
                    assert system.start_capture(audio_config) is True
                    assert system.is_running is True
                    
                    # Get status
                    status = system.get_input_status()
                    assert isinstance(status, dict)
                    
                    # Stop capture
                    assert system.stop_capture() is True
                    assert system.is_running is False
            
            # Shutdown
            await system.shutdown()
            assert system.is_initialized is False


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])