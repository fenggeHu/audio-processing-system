"""
Tests for the plugin system implementation.

This module tests the plugin manager, sandbox, registry, and service
to ensure proper functionality and security.
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import numpy as np

from src.audio_processing.models import AudioConfig, AudioFrame
from src.audio_processing.plugin_manager import PluginManager
from src.audio_processing.plugin_sandbox import PluginSandbox, PluginSecurityManager
from src.audio_processing.plugin_registry import PluginRegistry, PluginMetadata, PluginVersion
from src.audio_processing.services.plugin_service import PluginService
from src.audio_processing.interfaces import IPluginInterface
from src.audio_processing.exceptions import PluginError


class TestPlugin(IPluginInterface):
    """Test plugin for unit testing."""
    
    def __init__(self):
        self.initialized = False
        self.config = None
    
    def get_plugin_info(self):
        return {
            'name': 'TestPlugin',
            'version': '1.0.0',
            'description': 'Test plugin for unit testing',
            'author': 'Test Author',
            'license': 'MIT',
            'categories': ['test'],
            'keywords': ['test', 'unit']
        }
    
    def get_required_dependencies(self):
        return []
    
    async def initialize(self, config):
        self.config = config
        self.initialized = True
    
    async def cleanup(self):
        self.initialized = False
        self.config = None
    
    def process_frame(self, frame):
        # Simple gain adjustment
        output_data = frame.data * 0.5
        return AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            frame_size=frame.frame_size,
            data=output_data,
            metadata={'processed_by': 'TestPlugin'}
        )


class MaliciousPlugin(IPluginInterface):
    """Malicious plugin for security testing."""
    
    def get_plugin_info(self):
        return {
            'name': 'MaliciousPlugin',
            'version': '1.0.0',
            'description': 'Malicious plugin for security testing',
            'author': 'Hacker',
            'license': 'Evil'
        }
    
    def get_required_dependencies(self):
        return []
    
    async def initialize(self, config):
        # Try to access restricted modules
        import os  # This should be blocked
        os.system("echo 'hacked'")  # This should never execute
    
    async def cleanup(self):
        pass
    
    def process_frame(self, frame):
        return frame


@pytest.fixture
def audio_config():
    """Create test audio configuration."""
    return AudioConfig(
        sample_rate=48000,
        frame_size=480,
        channels=2,
        buffer_size=4096
    )


@pytest.fixture
def test_frame(audio_config):
    """Create test audio frame."""
    data = np.random.randn(audio_config.channels, audio_config.frame_size) * 0.1
    return AudioFrame(
        timestamp=datetime.now(),
        sample_rate=audio_config.sample_rate,
        channels=audio_config.channels,
        frame_size=audio_config.frame_size,
        data=data
    )


@pytest.fixture
def temp_plugin_dir():
    """Create temporary plugin directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


class TestPluginRegistry:
    """Test plugin registry functionality."""
    
    def test_plugin_version_parsing(self):
        """Test plugin version parsing and comparison."""
        v1 = PluginVersion.from_string("1.2.3")
        assert v1.major == 1
        assert v1.minor == 2
        assert v1.patch == 3
        
        v2 = PluginVersion.from_string("1.2.4")
        assert v1 < v2
        
        v3 = PluginVersion.from_string("1.2.3-alpha")
        assert v3 < v1
    
    def test_plugin_metadata_creation(self):
        """Test plugin metadata creation and serialization."""
        version = PluginVersion(1, 0, 0)
        metadata = PluginMetadata(
            name="TestPlugin",
            version=version,
            description="Test plugin",
            author="Test Author",
            license="MIT"
        )
        
        assert metadata.name == "TestPlugin"
        assert metadata.version == version
        assert metadata.author == "Test Author"
    
    def test_registry_operations(self):
        """Test plugin registry operations."""
        registry = PluginRegistry(":memory:")  # In-memory registry
        
        version = PluginVersion(1, 0, 0)
        metadata = PluginMetadata(
            name="TestPlugin",
            version=version,
            description="Test plugin",
            author="Test Author",
            license="MIT"
        )
        
        # Register plugin
        registry.register_plugin(metadata)
        
        # Retrieve plugin
        retrieved = registry.get_plugin("TestPlugin")
        assert retrieved is not None
        assert retrieved.name == "TestPlugin"
        
        # List plugins
        plugins = registry.list_plugins()
        assert len(plugins) == 1
        assert plugins[0].name == "TestPlugin"
        
        # Unregister plugin
        registry.unregister_plugin("TestPlugin")
        assert registry.get_plugin("TestPlugin") is None


class TestPluginSandbox:
    """Test plugin sandbox security."""
    
    @pytest.mark.asyncio
    async def test_sandbox_basic_functionality(self):
        """Test basic sandbox functionality."""
        sandbox = PluginSandbox("TestPlugin")
        
        async with sandbox:
            # Test safe execution
            result = sandbox.execute_sync_safe(lambda x: x * 2, 5)
            assert result == 10
    
    @pytest.mark.asyncio
    async def test_sandbox_timeout(self):
        """Test sandbox execution timeout."""
        sandbox = PluginSandbox("TestPlugin", {'execution_timeout': 0.1})
        
        async with sandbox:
            with pytest.raises(PluginError):
                # This should timeout
                await sandbox.execute_safe(asyncio.sleep(1))
    
    def test_security_manager(self):
        """Test plugin security manager."""
        security_manager = PluginSecurityManager()
        
        # Set custom policy
        policy = {
            'max_memory_mb': 50,
            'execution_timeout': 2.0
        }
        security_manager.set_plugin_policy("TestPlugin", policy)
        
        # Get policy
        retrieved_policy = security_manager.get_plugin_policy("TestPlugin")
        assert retrieved_policy['max_memory_mb'] == 50
        assert retrieved_policy['execution_timeout'] == 2.0
        
        # Create sandbox with policy
        sandbox = security_manager.create_sandbox("TestPlugin")
        assert sandbox.max_memory_mb == 50
        assert sandbox.execution_timeout == 2.0


class TestPluginManager:
    """Test plugin manager functionality."""
    
    @pytest.mark.asyncio
    async def test_plugin_manager_initialization(self, audio_config, temp_plugin_dir):
        """Test plugin manager initialization."""
        manager = PluginManager(audio_config, [temp_plugin_dir])
        
        await manager.start()
        assert manager.is_running
        
        await manager.stop()
        assert not manager.is_running
    
    @pytest.mark.asyncio
    async def test_plugin_discovery_and_loading(self, audio_config, temp_plugin_dir):
        """Test plugin discovery and loading."""
        # Create test plugin file
        plugin_file = Path(temp_plugin_dir) / "test_plugin.py"
        plugin_code = '''
from src.audio_processing.interfaces import IPluginInterface

class TestDiscoveryPlugin(IPluginInterface):
    def get_plugin_info(self):
        return {
            'name': 'TestDiscoveryPlugin',
            'version': '1.0.0',
            'description': 'Test plugin for discovery',
            'author': 'Test',
            'license': 'MIT'
        }
    
    def get_required_dependencies(self):
        return []
    
    async def initialize(self, config):
        pass
    
    async def cleanup(self):
        pass
'''
        plugin_file.write_text(plugin_code)
        
        manager = PluginManager(audio_config, [temp_plugin_dir])
        await manager.start()
        
        # Discover plugins
        discovered = await manager.discover_plugins()
        assert "test_plugin" in discovered
        
        # Load plugin
        success = await manager.load_plugin("test_plugin")
        assert success
        
        # Check if loaded
        assert "test_plugin" in manager.list_loaded_plugins()
        
        # Unload plugin
        success = await manager.unload_plugin("test_plugin")
        assert success
        
        await manager.stop()


class TestPluginService:
    """Test plugin service integration."""
    
    @pytest.mark.asyncio
    async def test_plugin_service_initialization(self, audio_config, temp_plugin_dir):
        """Test plugin service initialization."""
        manager = PluginManager(audio_config, [temp_plugin_dir])
        service = PluginService(audio_config, manager)
        
        await service.start()
        assert service.is_running
        
        await service.stop()
        assert not service.is_running
    
    @pytest.mark.asyncio
    async def test_plugin_processing_chain(self, audio_config, test_frame, temp_plugin_dir):
        """Test plugin processing chain."""
        # Create test plugin file
        plugin_file = Path(temp_plugin_dir) / "gain_plugin.py"
        plugin_code = '''
import numpy as np
from src.audio_processing.interfaces import IPluginInterface
from src.audio_processing.models import AudioFrame

class GainPlugin(IPluginInterface):
    def __init__(self):
        self.gain = 0.5
    
    def get_plugin_info(self):
        return {
            'name': 'GainPlugin',
            'version': '1.0.0',
            'description': 'Simple gain plugin',
            'author': 'Test',
            'license': 'MIT'
        }
    
    def get_required_dependencies(self):
        return []
    
    async def initialize(self, config):
        pass
    
    async def cleanup(self):
        pass
    
    def process_frame(self, frame):
        output_data = frame.data * self.gain
        return AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            frame_size=frame.frame_size,
            data=output_data,
            metadata={'processed_by': 'GainPlugin', 'gain': self.gain}
        )
'''
        plugin_file.write_text(plugin_code)
        
        manager = PluginManager(audio_config, [temp_plugin_dir])
        service = PluginService(audio_config, manager)
        
        await service.start()
        
        # Load plugin into service
        success = await service.load_plugin("gain_plugin")
        assert success
        
        # Process frame
        result = await service.process(test_frame)
        assert result.success
        
        processed_frame = result.data
        assert processed_frame is not None
        assert 'processed_by' in processed_frame.metadata
        assert processed_frame.metadata['processed_by'] == 'GainPlugin'
        
        # Check that gain was applied
        expected_data = test_frame.data * 0.5
        np.testing.assert_array_almost_equal(processed_frame.data, expected_data)
        
        await service.stop()
    
    @pytest.mark.asyncio
    async def test_plugin_bypass_mode(self, audio_config, test_frame, temp_plugin_dir):
        """Test plugin bypass mode."""
        manager = PluginManager(audio_config, [temp_plugin_dir])
        service = PluginService(audio_config, manager)
        
        await service.start()
        
        # Enable bypass mode
        service.set_bypass_mode(True)
        
        # Process frame (should pass through unchanged)
        result = await service.process(test_frame)
        assert result.success
        
        processed_frame = result.data
        np.testing.assert_array_equal(processed_frame.data, test_frame.data)
        
        await service.stop()


class TestPluginSecurity:
    """Test plugin security features."""
    
    @pytest.mark.asyncio
    async def test_malicious_plugin_blocking(self):
        """Test that malicious plugins are properly sandboxed."""
        # This test would need to be more sophisticated in a real implementation
        # For now, we just test that the sandbox can catch import errors
        
        sandbox = PluginSandbox("MaliciousPlugin")
        
        async with sandbox:
            # Test that restricted imports are caught
            with pytest.raises(Exception):  # Should raise some kind of security exception
                sandbox.execute_sync_safe(lambda: __import__('os'))


if __name__ == "__main__":
    pytest.main([__file__])