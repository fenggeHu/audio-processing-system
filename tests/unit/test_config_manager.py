"""
Tests for the ConfigManager configuration management system.
"""

import pytest
import json
import tempfile
import asyncio
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.audio_processing.config_manager import ConfigManager, ConfigVersion
from src.audio_processing.models import AudioConfig
from src.audio_processing.exceptions import ConfigError


class TestConfigManager:
    """Test cases for ConfigManager functionality."""
    
    @pytest.fixture
    def temp_config_file(self):
        """Create temporary config file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                "sample_rate": 48000,
                "frame_size": 480,
                "channels": 8,
                "buffer_size": 4096,
                "enable_ssl": True,
                "enable_beamforming": True,
                "enable_aec": True,
                "enable_denoise": True,
                "enable_agc": True,
                "max_latency_ms": 40.0,
                "cpu_limit_percent": 80.0
            }
            json.dump(config_data, f, indent=2)
            temp_path = Path(f.name)
        
        yield temp_path
        
        # Cleanup
        if temp_path.exists():
            temp_path.unlink()
    
    @pytest.fixture
    def config_manager(self, temp_config_file):
        """Create ConfigManager instance for testing."""
        return ConfigManager(
            config_path=temp_config_file,
            schema_model=AudioConfig,
            auto_save=True,
            max_versions=10
        )
    
    def test_config_manager_initialization(self, config_manager):
        """Test ConfigManager initialization."""
        assert config_manager.get_current_version() == 1
        assert len(config_manager.get_version_history()) == 1
        assert config_manager.auto_save is True
        assert config_manager.max_versions == 10
    
    def test_load_existing_config(self, temp_config_file):
        """Test loading existing configuration file."""
        manager = ConfigManager(temp_config_file)
        config = manager.get_current_config()
        
        assert config["sample_rate"] == 48000
        assert config["channels"] == 8
        assert config["enable_ssl"] is True
    
    def test_create_default_config(self):
        """Test creating default configuration when file doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "new_config.json"
            manager = ConfigManager(config_path)
            
            assert config_path.exists()
            config = manager.get_current_config()
            assert "sample_rate" in config
            assert "channels" in config
    
    def test_config_validation_success(self, config_manager):
        """Test successful configuration validation."""
        valid_config = {
            "sample_rate": 44100,
            "frame_size": 512,
            "channels": 2,
            "buffer_size": 2048,
            "enable_ssl": False,
            "enable_beamforming": False,
            "enable_aec": False,
            "enable_denoise": False,
            "enable_agc": False,
            "max_latency_ms": 50.0,
            "cpu_limit_percent": 70.0
        }
        
        assert config_manager.validate_config(valid_config) is True
    
    def test_config_validation_failure(self, config_manager):
        """Test configuration validation failure."""
        invalid_config = {
            "sample_rate": -1,  # Invalid: negative sample rate
            "frame_size": 512,
            "channels": 2
        }
        
        assert config_manager.validate_config(invalid_config) is False
    
    @pytest.mark.asyncio
    async def test_apply_config_success(self, config_manager):
        """Test successful configuration application."""
        new_config = {
            "sample_rate": 44100,
            "frame_size": 512,
            "channels": 2,
            "buffer_size": 2048,
            "enable_ssl": False,
            "enable_beamforming": False,
            "enable_aec": False,
            "enable_denoise": False,
            "enable_agc": False,
            "max_latency_ms": 50.0,
            "cpu_limit_percent": 70.0
        }
        
        initial_version = config_manager.get_current_version()
        
        await config_manager.apply_config(
            new_config, 
            description="Test configuration update",
            user="test_user"
        )
        
        assert config_manager.get_current_version() == initial_version + 1
        assert config_manager.get_current_config()["sample_rate"] == 44100
        
        # Check version history
        versions = config_manager.get_version_history()
        assert len(versions) == 2
        assert versions[-1].description == "Test configuration update"
        assert versions[-1].user == "test_user"
    
    @pytest.mark.asyncio
    async def test_apply_invalid_config(self, config_manager):
        """Test applying invalid configuration."""
        invalid_config = {
            "sample_rate": -1,  # Invalid
            "channels": 0       # Invalid
        }
        
        with pytest.raises(ConfigError):
            await config_manager.apply_config(invalid_config)
    
    @pytest.mark.asyncio
    async def test_rollback_to_version(self, config_manager):
        """Test rollback to specific version."""
        # Apply first config change
        config1 = config_manager.get_current_config().copy()
        config1["sample_rate"] = 44100
        await config_manager.apply_config(config1, "Change 1")
        
        # Apply second config change
        config2 = config_manager.get_current_config().copy()
        config2["sample_rate"] = 32000
        await config_manager.apply_config(config2, "Change 2")
        
        # Rollback to version 2 (first change)
        await config_manager.rollback_to_version(2)
        
        assert config_manager.get_current_config()["sample_rate"] == 44100
    
    @pytest.mark.asyncio
    async def test_rollback_steps(self, config_manager):
        """Test rollback by number of steps."""
        original_config = config_manager.get_current_config().copy()
        
        # Apply two changes
        config1 = original_config.copy()
        config1["sample_rate"] = 44100
        await config_manager.apply_config(config1, "Change 1")
        
        config2 = config1.copy()
        config2["sample_rate"] = 32000
        await config_manager.apply_config(config2, "Change 2")
        
        # Rollback 2 steps (back to original)
        await config_manager.rollback_steps(2)
        
        assert config_manager.get_current_config()["sample_rate"] == original_config["sample_rate"]
    
    def test_change_handlers(self, config_manager):
        """Test configuration change handlers."""
        sync_handler_called = False
        async_handler_called = False
        
        def sync_handler(old_config, new_config):
            nonlocal sync_handler_called
            sync_handler_called = True
            assert old_config != new_config
        
        async def async_handler(old_config, new_config):
            nonlocal async_handler_called
            async_handler_called = True
            assert old_config != new_config
        
        config_manager.add_change_handler(sync_handler)
        config_manager.add_async_change_handler(async_handler)
        
        # Apply config change
        new_config = config_manager.get_current_config().copy()
        new_config["sample_rate"] = 44100
        
        # Run async apply_config
        asyncio.run(config_manager.apply_config(new_config))
        
        assert sync_handler_called
        assert async_handler_called
    
    def test_version_history_limit(self):
        """Test version history size limit."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_config.json"
            manager = ConfigManager(config_path, max_versions=3)
            
            # Apply multiple config changes
            for i in range(5):
                config = manager.get_current_config().copy()
                config["sample_rate"] = 48000 + i * 1000
                asyncio.run(manager.apply_config(config, f"Change {i}"))
            
            # Should only keep last 3 versions
            versions = manager.get_version_history()
            assert len(versions) <= 3
    
    def test_export_config(self, config_manager):
        """Test configuration export."""
        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "exported_config.json"
            
            config_manager.export_config(export_path)
            
            assert export_path.exists()
            
            # Verify exported content
            with open(export_path, 'r') as f:
                exported_config = json.load(f)
            
            assert exported_config == config_manager.get_current_config()
    
    def test_get_config_schema(self, config_manager):
        """Test getting configuration schema."""
        schema = config_manager.get_config_schema()
        
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "sample_rate" in schema["properties"]
    
    def test_config_diff(self, config_manager):
        """Test configuration difference calculation."""
        # Apply a config change
        new_config = config_manager.get_current_config().copy()
        new_config["sample_rate"] = 44100
        asyncio.run(config_manager.apply_config(new_config, "Test change"))
        
        # Get diff between versions
        diff = config_manager.get_config_diff(1, 2)
        
        assert "sample_rate" in diff
        assert diff["sample_rate"]["old"] == 48000
        assert diff["sample_rate"]["new"] == 44100
    
    @pytest.mark.asyncio
    async def test_hot_reload(self, config_manager, temp_config_file):
        """Test hot reload functionality."""
        # Modify the config file externally
        new_config_data = {
            "sample_rate": 44100,
            "frame_size": 512,
            "channels": 2,
            "buffer_size": 2048,
            "enable_ssl": False,
            "enable_beamforming": False,
            "enable_aec": False,
            "enable_denoise": False,
            "enable_agc": False,
            "max_latency_ms": 50.0,
            "cpu_limit_percent": 70.0
        }
        
        with open(temp_config_file, 'w') as f:
            json.dump(new_config_data, f, indent=2)
        
        # Hot reload
        await config_manager.hot_reload()
        
        assert config_manager.get_current_config()["sample_rate"] == 44100
        assert config_manager.get_current_config()["channels"] == 2


if __name__ == "__main__":
    pytest.main([__file__])