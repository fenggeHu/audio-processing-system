"""
Basic tests for the production audio system.

These tests verify the basic project structure and imports.
"""

import pytest
import sys
from pathlib import Path

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_imports():
    """Test that basic imports work."""
    # Test configuration imports
    from src.config.audio_config import AudioConfig
    from src.config.system_config import SystemConfig
    from src.config.embedded_config import EmbeddedConfigManager
    from src.config.platform_config import PlatformConfigManager
    from src.config.logging_config import AudioSystemLogger
    
    # Test core imports
    from src.audio_core.audio_frame import AudioFrame
    from src.audio_core.device_manager import DeviceManager
    from src.audio_core.hardware_interface import HardwareAbstractionLayer
    
    # Test processing imports
    from src.processing.processing_chain import ProcessingChain
    from src.processing.components import ComponentRegistry
    from src.processing.pipeline import AudioPipeline
    
    # Test visualization imports
    from src.visualization.dashboard import Dashboard
    from src.visualization.monitors import AudioMonitor
    from src.visualization.web_interface import WebInterface
    
    # Test tools imports
    from src.tools.benchmark import AudioBenchmarkSuite


def test_audio_config():
    """Test audio configuration."""
    from src.config.audio_config import AudioConfig
    config = AudioConfig()
    
    assert config.sample_rate == 48000
    assert config.buffer_size == 256
    assert config.channels == 2
    assert config.bit_depth == 24
    
    # Test validation
    errors = config.validate()
    assert len(errors) == 0


def test_system_config():
    """Test system configuration."""
    from src.config.system_config import SystemConfig
    config = SystemConfig()
    
    assert config.system_name == "ProductionAudioSystem"
    assert config.log_level == "INFO"
    assert config.web_port == 8080
    
    # Test validation
    errors = config.validate()
    assert len(errors) == 0


def test_embedded_config():
    """Test embedded configuration."""
    from src.config.embedded_config import EmbeddedConfigManager
    manager = EmbeddedConfigManager()
    
    assert manager.config is not None
    assert hasattr(manager.config, 'memory_mode')
    assert hasattr(manager.config, 'cpu_architecture')


def test_platform_config():
    """Test platform configuration."""
    from src.config.platform_config import PlatformConfigManager
    manager = PlatformConfigManager()
    
    assert manager.platform in ['linux', 'macos', 'windows', 'unknown']
    assert manager.config is not None


def test_audio_frame():
    """Test audio frame functionality."""
    import numpy as np
    from src.audio_core.audio_frame import AudioFrame
    
    # Create test audio data
    sample_rate = 48000
    duration = 0.1  # 100ms
    samples = int(sample_rate * duration)
    data = np.random.randn(samples).astype(np.float32)
    
    # Create audio frame
    frame = AudioFrame(data, sample_rate)
    
    assert frame.sample_rate == sample_rate
    assert frame.frame_size == samples
    assert frame.channels == 1
    assert frame.get_duration_ms() == pytest.approx(100.0, rel=1e-2)
    
    # Test RMS and peak levels
    rms = frame.get_rms_level()
    peak = frame.get_peak_level()
    
    assert rms > 0
    assert peak > 0
    assert peak >= rms


def test_benchmark_suite():
    """Test benchmark suite initialization."""
    from src.tools.benchmark import AudioBenchmarkSuite
    
    suite = AudioBenchmarkSuite()
    
    assert suite.system_info is not None
    assert hasattr(suite.system_info, 'platform')
    assert hasattr(suite.system_info, 'architecture')
    assert len(suite.results) == 0


def test_device_manager():
    """Test device manager initialization."""
    from src.audio_core.device_manager import DeviceManager
    manager = DeviceManager()
    
    assert hasattr(manager, '_devices')
    assert len(manager._devices) == 0


def test_processing_chain():
    """Test processing chain initialization."""
    from src.processing.processing_chain import ProcessingChain
    chain = ProcessingChain()
    
    assert isinstance(chain.components, list)
    assert len(chain.components) == 0
    assert chain.enabled is True


def test_component_registry():
    """Test component registry initialization."""
    from src.processing.components import ComponentRegistry
    registry = ComponentRegistry()
    
    assert isinstance(registry.components, dict)
    assert isinstance(registry.instances, dict)
    assert len(registry.list_components()) == 0


if __name__ == "__main__":
    pytest.main([__file__])