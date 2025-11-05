"""
Tests for Device Manager implementation

Tests the core functionality of the device manager including discovery,
configuration, health monitoring, and hot-plug detection.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

from src.audio_core.device_manager import (
    DeviceManager, AudioDeviceDiscovery, DeviceHealthMonitor,
    HotPlugDetector, DeviceConfigurationManager, DeviceConfiguration,
    DeviceStatus, HealthStatus, create_device_manager
)
from src.audio_core.models import AudioDevice, DeviceType
from src.audio_core.interfaces import ComponentState


class TestDeviceManager:
    """Test cases for DeviceManager"""
    
    def setup_method(self):
        """Setup test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.device_manager = DeviceManager(config_dir=self.temp_dir)
    
    def teardown_method(self):
        """Cleanup test environment"""
        if hasattr(self, 'device_manager'):
            self.device_manager.cleanup()
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_device_manager_initialization(self):
        """Test device manager initialization"""
        # Test initial state
        assert self.device_manager.get_state() == ComponentState.UNINITIALIZED
        
        # Test initialization
        result = self.device_manager.init({})
        assert result is True
        assert self.device_manager.get_state() == ComponentState.READY
    
    def test_device_discovery(self):
        """Test device discovery functionality"""
        # Initialize device manager
        self.device_manager.init({})
        
        # Test device scanning
        devices = self.device_manager.scan_devices()
        assert isinstance(devices, list)
        assert len(devices) > 0
        
        # Verify devices are stored
        all_devices = self.device_manager.get_all_devices()
        assert len(all_devices) == len(devices)
        
        # Test input/output device filtering
        input_devices = self.device_manager.get_input_devices()
        output_devices = self.device_manager.get_output_devices()
        
        assert all(device.is_input for device in input_devices)
        assert all(device.is_output for device in output_devices)
    
    def test_default_device_management(self):
        """Test default device management"""
        # Initialize and scan devices
        self.device_manager.init({})
        self.device_manager.scan_devices()
        
        # Test default devices are set
        default_input = self.device_manager.get_default_input_device()
        default_output = self.device_manager.get_default_output_device()
        
        input_devices = self.device_manager.get_input_devices()
        output_devices = self.device_manager.get_output_devices()
        
        if input_devices:
            assert default_input is not None
            assert default_input.is_input
        
        if output_devices:
            assert default_output is not None
            assert default_output.is_output
    
    def test_device_configuration(self):
        """Test device configuration management"""
        # Initialize and scan devices
        self.device_manager.init({})
        devices = self.device_manager.scan_devices()
        
        if devices:
            device = devices[0]
            device_id = device.device_id
            
            # Test getting configuration
            config = self.device_manager.get_device_configuration(device_id)
            assert config is not None
            assert config.device_id == device_id
            
            # Test updating configuration
            config.sample_rate = 96000
            config.gain_db = 6.0
            
            result = self.device_manager.set_device_configuration(device_id, config)
            assert result is True
            
            # Verify configuration was updated
            updated_config = self.device_manager.get_device_configuration(device_id)
            assert updated_config.sample_rate == 96000
            assert updated_config.gain_db == 6.0
    
    def test_device_enable_disable(self):
        """Test device enable/disable functionality"""
        # Initialize and scan devices
        self.device_manager.init({})
        devices = self.device_manager.scan_devices()
        
        if devices:
            device_id = devices[0].device_id
            
            # Test disabling device
            result = self.device_manager.disable_device(device_id)
            assert result is True
            
            config = self.device_manager.get_device_configuration(device_id)
            assert config.enabled is False
            
            # Test enabling device
            result = self.device_manager.enable_device(device_id)
            assert result is True
            
            config = self.device_manager.get_device_configuration(device_id)
            assert config.enabled is True
    
    def test_device_manager_lifecycle(self):
        """Test device manager lifecycle operations"""
        # Test initialization
        assert self.device_manager.init({}) is True
        assert self.device_manager.get_state() == ComponentState.READY
        
        # Test starting
        assert self.device_manager.start() is True
        assert self.device_manager.get_state() == ComponentState.RUNNING
        
        # Test pausing
        assert self.device_manager.pause() is True
        assert self.device_manager.get_state() == ComponentState.PAUSED
        
        # Test resuming
        assert self.device_manager.resume() is True
        assert self.device_manager.get_state() == ComponentState.RUNNING
        
        # Test stopping
        assert self.device_manager.stop() is True
        assert self.device_manager.get_state() == ComponentState.STOPPED
    
    def test_device_summary(self):
        """Test device summary functionality"""
        # Initialize and scan devices
        self.device_manager.init({})
        self.device_manager.scan_devices()
        
        # Get device summary
        summary = self.device_manager.get_device_summary()
        
        # Verify summary structure
        assert "total_devices" in summary
        assert "input_devices" in summary
        assert "output_devices" in summary
        assert "available_devices" in summary
        assert "devices" in summary
        
        assert isinstance(summary["devices"], list)
        assert summary["total_devices"] >= 0
    
    def test_health_status(self):
        """Test device manager health status"""
        # Initialize device manager
        self.device_manager.init({})
        
        # Get health status
        health = self.device_manager.get_health_status()
        
        # Verify health status structure
        assert "status" in health
        assert "state" in health
        assert "device_count" in health
        assert "last_check" in health


class TestAudioDeviceDiscovery:
    """Test cases for AudioDeviceDiscovery"""
    
    def setup_method(self):
        """Setup test environment"""
        self.discovery = AudioDeviceDiscovery()
    
    def test_device_discovery(self):
        """Test basic device discovery"""
        devices = self.discovery.discover_devices()
        
        assert isinstance(devices, list)
        assert len(devices) > 0
        
        # Verify device properties
        for device in devices:
            assert isinstance(device, AudioDevice)
            assert device.device_id
            assert device.name
            assert device.device_type in DeviceType
    
    def test_discovery_callbacks(self):
        """Test discovery callback registration"""
        callback_called = False
        discovered_devices = []
        
        def test_callback(devices):
            nonlocal callback_called, discovered_devices
            callback_called = True
            discovered_devices = devices
        
        # Register callback
        self.discovery.register_discovery_callback(test_callback)
        
        # Trigger discovery
        devices = self.discovery.discover_devices()
        
        # Verify callback was called
        assert callback_called is True
        assert len(discovered_devices) == len(devices)


class TestDeviceConfigurationManager:
    """Test cases for DeviceConfigurationManager"""
    
    def setup_method(self):
        """Setup test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_manager = DeviceConfigurationManager(self.temp_dir)
    
    def teardown_method(self):
        """Cleanup test environment"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_configuration_persistence(self):
        """Test configuration save/load functionality"""
        # Create test device
        device = AudioDevice(
            device_id="test_device",
            name="Test Device",
            device_type=DeviceType.MICROPHONE,
            is_input=True,
            is_output=False
        )
        
        # Create configuration
        config = self.config_manager.create_default_configuration(device)
        config.sample_rate = 96000
        config.gain_db = 3.0
        
        # Save configuration
        result = self.config_manager.set_device_configuration(device.device_id, config)
        assert result is True
        
        # Create new manager instance to test persistence
        new_manager = DeviceConfigurationManager(self.temp_dir)
        loaded_configs = new_manager.load_configurations()
        
        # Verify configuration was persisted
        assert device.device_id in loaded_configs
        loaded_config = loaded_configs[device.device_id]
        assert loaded_config.sample_rate == 96000
        assert loaded_config.gain_db == 3.0


def test_create_device_manager():
    """Test device manager factory function"""
    manager = create_device_manager()
    
    assert isinstance(manager, DeviceManager)
    assert manager.get_state() == ComponentState.UNINITIALIZED
    
    # Cleanup
    manager.cleanup()


if __name__ == "__main__":
    pytest.main([__file__])