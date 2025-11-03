# Plugin Development Guide

This guide explains how to develop plugins for the Audio Processing System.

## Overview

The Audio Processing System supports a plugin architecture that allows developers to create custom audio processing modules without modifying the core system. Plugins are executed in a secure sandbox environment and can be loaded/unloaded at runtime.

## Plugin Interface

All plugins must implement the `IPluginInterface` interface:

```python
from audio_processing.interfaces import IPluginInterface
from audio_processing.models import AudioConfig, AudioFrame
from typing import Dict, Any, List

class MyPlugin(IPluginInterface):
    def get_plugin_info(self) -> Dict[str, Any]:
        """Return plugin metadata."""
        pass
    
    def get_required_dependencies(self) -> List[str]:
        """Return list of required dependencies."""
        pass
    
    async def initialize(self, config: AudioConfig) -> None:
        """Initialize plugin with system configuration."""
        pass
    
    async def cleanup(self) -> None:
        """Clean up plugin resources."""
        pass
    
    def process_frame(self, frame: AudioFrame) -> AudioFrame:
        """Process audio frame (main processing method)."""
        pass
```

## Plugin Metadata

The `get_plugin_info()` method must return a dictionary with the following fields:

```python
def get_plugin_info(self) -> Dict[str, Any]:
    return {
        'name': 'MyPlugin',                    # Required: Plugin name
        'version': '1.0.0',                    # Required: Version string
        'description': 'My audio plugin',      # Required: Description
        'author': 'Your Name',                 # Required: Author name
        'license': 'MIT',                      # Required: License
        'homepage': 'https://example.com',     # Optional: Homepage URL
        'repository': 'https://github.com/..', # Optional: Repository URL
        'keywords': ['effect', 'filter'],      # Optional: Keywords for search
        'categories': ['effects'],             # Optional: Categories
        'entry_point': 'MyPlugin',            # Optional: Main class name
        'min_system_version': '1.0.0'         # Optional: Minimum system version
    }
```

## Audio Processing

The main processing happens in the `process_frame()` method:

```python
def process_frame(self, frame: AudioFrame) -> AudioFrame:
    # Get input data (shape: channels x frame_size)
    input_data = frame.data
    
    # Process audio (example: apply gain)
    output_data = input_data * 0.8
    
    # Create output frame
    output_frame = AudioFrame(
        timestamp=frame.timestamp,
        sample_rate=frame.sample_rate,
        channels=frame.channels,
        frame_size=frame.frame_size,
        data=output_data,
        metadata=frame.metadata.copy() if frame.metadata else {}
    )
    
    # Add plugin metadata
    if output_frame.metadata is None:
        output_frame.metadata = {}
    output_frame.metadata['processed_by'] = 'MyPlugin'
    
    return output_frame
```

## Configuration and Parameters

Plugins can support runtime configuration:

```python
class ConfigurablePlugin(IPluginInterface):
    def __init__(self):
        self.gain = 1.0
        self.enabled = True
    
    def get_parameters(self) -> Dict[str, Any]:
        """Get current plugin parameters."""
        return {
            'gain': self.gain,
            'enabled': self.enabled
        }
    
    def set_parameters(self, parameters: Dict[str, Any]) -> None:
        """Set plugin parameters."""
        if 'gain' in parameters:
            self.gain = max(0.0, min(2.0, parameters['gain']))
        
        if 'enabled' in parameters:
            self.enabled = bool(parameters['enabled'])
    
    def process_frame(self, frame: AudioFrame) -> AudioFrame:
        if not self.enabled:
            return frame
        
        output_data = frame.data * self.gain
        # ... rest of processing
```

## Dependencies

Plugins can declare dependencies on other plugins:

```python
def get_required_dependencies(self) -> List[str]:
    return ['BaseFilter', 'NoiseGate']  # This plugin requires these plugins
```

## Security Considerations

Plugins run in a sandboxed environment with the following restrictions:

### Allowed Modules
- `numpy`, `scipy` - Mathematical operations
- `librosa`, `soundfile` - Audio processing libraries
- `pydantic` - Data validation
- Standard library: `math`, `random`, `json`, `datetime`, etc.

### Restricted Modules
- `os`, `sys` - System access
- `subprocess` - Process execution
- `socket`, `urllib`, `http` - Network access
- `pickle`, `marshal` - Serialization (security risk)

### Resource Limits
- Maximum memory usage: 100MB (configurable)
- Maximum CPU time per frame: 1000ms (configurable)
- Execution timeout: 5 seconds (configurable)

## Example Plugin: Simple Reverb

```python
import numpy as np
from audio_processing.interfaces import IPluginInterface
from audio_processing.models import AudioConfig, AudioFrame
from typing import Dict, Any, List

class SimpleReverbPlugin(IPluginInterface):
    def __init__(self):
        self.delay_buffer = None
        self.delay_samples = 0
        self.feedback = 0.3
        self.wet_level = 0.2
        self.buffer_index = 0
    
    def get_plugin_info(self) -> Dict[str, Any]:
        return {
            'name': 'SimpleReverb',
            'version': '1.0.0',
            'description': 'Simple reverb effect with configurable delay and feedback',
            'author': 'Audio Processing Team',
            'license': 'MIT',
            'categories': ['effects', 'reverb'],
            'keywords': ['reverb', 'echo', 'delay']
        }
    
    def get_required_dependencies(self) -> List[str]:
        return []
    
    async def initialize(self, config: AudioConfig) -> None:
        # 100ms delay
        delay_ms = 100
        self.delay_samples = int((delay_ms / 1000.0) * config.sample_rate)
        self.delay_buffer = np.zeros((config.channels, self.delay_samples))
        self.buffer_index = 0
    
    async def cleanup(self) -> None:
        self.delay_buffer = None
    
    def process_frame(self, frame: AudioFrame) -> AudioFrame:
        output_data = frame.data.copy()
        
        for ch in range(frame.channels):
            for i in range(frame.frame_size):
                # Get delayed sample
                delayed_sample = self.delay_buffer[ch, self.buffer_index]
                
                # Mix dry and wet signals
                dry_sample = frame.data[ch, i]
                wet_sample = delayed_sample * self.wet_level
                output_data[ch, i] = dry_sample + wet_sample
                
                # Update delay buffer with feedback
                self.delay_buffer[ch, self.buffer_index] = (
                    dry_sample + delayed_sample * self.feedback
                )
                
                self.buffer_index = (self.buffer_index + 1) % self.delay_samples
        
        return AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            frame_size=frame.frame_size,
            data=output_data,
            metadata={'processed_by': 'SimpleReverb'}
        )
    
    def get_parameters(self) -> Dict[str, Any]:
        return {
            'feedback': self.feedback,
            'wet_level': self.wet_level
        }
    
    def set_parameters(self, parameters: Dict[str, Any]) -> None:
        if 'feedback' in parameters:
            self.feedback = max(0.0, min(0.9, parameters['feedback']))
        if 'wet_level' in parameters:
            self.wet_level = max(0.0, min(1.0, parameters['wet_level']))
```

## Plugin Installation

1. Place your plugin file in the `plugins/` directory
2. The plugin will be automatically discovered on system startup
3. Load the plugin using the Plugin Manager API or web interface

## Testing Your Plugin

Create unit tests for your plugin:

```python
import pytest
import numpy as np
from datetime import datetime
from your_plugin import YourPlugin
from audio_processing.models import AudioConfig, AudioFrame

@pytest.mark.asyncio
async def test_your_plugin():
    plugin = YourPlugin()
    
    config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
    await plugin.initialize(config)
    
    # Create test frame
    test_data = np.random.randn(2, 480) * 0.1
    frame = AudioFrame(
        timestamp=datetime.now(),
        sample_rate=48000,
        channels=2,
        frame_size=480,
        data=test_data
    )
    
    # Process frame
    output_frame = plugin.process_frame(frame)
    
    # Verify output
    assert output_frame.channels == 2
    assert output_frame.frame_size == 480
    assert output_frame.data.shape == (2, 480)
    
    await plugin.cleanup()
```

## Best Practices

1. **Error Handling**: Always handle errors gracefully
2. **Resource Management**: Clean up resources in the `cleanup()` method
3. **Performance**: Keep processing efficient (target <1ms per frame)
4. **Thread Safety**: Plugins may be called from multiple threads
5. **Documentation**: Document your plugin's parameters and behavior
6. **Testing**: Write comprehensive unit tests
7. **Versioning**: Use semantic versioning for your plugins

## API Reference

### AudioFrame Structure
```python
@dataclass
class AudioFrame:
    timestamp: datetime      # Frame timestamp
    sample_rate: int        # Sample rate (Hz)
    channels: int           # Number of channels
    frame_size: int         # Frame size in samples
    data: np.ndarray        # Audio data (channels x frame_size)
    metadata: Dict[str, Any] # Optional metadata
```

### AudioConfig Structure
```python
class AudioConfig:
    sample_rate: int = 48000    # Sample rate
    frame_size: int = 480       # Frame size (10ms at 48kHz)
    channels: int = 8           # Number of channels
    buffer_size: int = 4096     # Buffer size
    # ... other configuration options
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Check that your plugin only imports allowed modules
2. **Performance Issues**: Profile your code and optimize hot paths
3. **Memory Leaks**: Ensure proper cleanup in the `cleanup()` method
4. **Sandbox Violations**: Review security restrictions

### Debugging

Enable debug logging to see plugin execution details:

```python
import structlog
logger = structlog.get_logger(__name__)

def process_frame(self, frame: AudioFrame) -> AudioFrame:
    logger.debug("Processing frame", plugin=self.__class__.__name__)
    # ... processing code
```

## Advanced Plugin Development

### State Management

For plugins that need to maintain state across frames:

```python
class StatefulPlugin(IPluginInterface):
    def __init__(self):
        self.history_buffer = None
        self.state = {}
    
    async def initialize(self, config: AudioConfig):
        # Initialize state based on config
        buffer_size = int(config.sample_rate * 0.1)  # 100ms buffer
        self.history_buffer = np.zeros((config.channels, buffer_size))
        self.state = {
            'buffer_index': 0,
            'initialized': True
        }
    
    def process_frame(self, frame: AudioFrame) -> AudioFrame:
        # Use historical data for processing
        history_data = self.history_buffer
        
        # Process with state
        output_data = self._process_with_history(frame.data, history_data)
        
        # Update state
        self._update_history(frame.data)
        
        return AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            frame_size=frame.frame_size,
            data=output_data
        )
```

### Multi-threaded Processing

For CPU-intensive plugins:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class ThreadedPlugin(IPluginInterface):
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2)
    
    async def initialize(self, config: AudioConfig):
        self.config = config
    
    async def cleanup(self):
        if self.executor:
            self.executor.shutdown(wait=True)
    
    def process_frame(self, frame: AudioFrame) -> AudioFrame:
        # For synchronous interface, we can't use async
        # But we can use thread pool for heavy computation
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            self.executor, 
            self._heavy_processing, 
            frame.data
        )
        
        # This is a simplified example - in practice you'd need
        # to handle this differently for real-time processing
        processed_data = asyncio.run_coroutine_threadsafe(
            future, loop
        ).result(timeout=0.01)  # 10ms timeout
        
        return AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            frame_size=frame.frame_size,
            data=processed_data
        )
    
    def _heavy_processing(self, data):
        # CPU-intensive processing here
        return data * 0.8  # Simplified example
```

### Plugin Communication

Plugins can communicate through metadata:

```python
class CommunicatingPlugin(IPluginInterface):
    def process_frame(self, frame: AudioFrame) -> AudioFrame:
        # Read metadata from previous plugins
        if frame.metadata and 'detected_speech' in frame.metadata:
            speech_detected = frame.metadata['detected_speech']
            if speech_detected:
                # Apply speech-specific processing
                output_data = self._process_speech(frame.data)
            else:
                # Apply noise-specific processing
                output_data = self._process_noise(frame.data)
        else:
            # Default processing
            output_data = frame.data
        
        # Add metadata for next plugins
        metadata = frame.metadata.copy() if frame.metadata else {}
        metadata.update({
            'processed_by': self.__class__.__name__,
            'gain_applied': self.current_gain,
            'processing_mode': 'speech' if speech_detected else 'noise'
        })
        
        return AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            frame_size=frame.frame_size,
            data=output_data,
            metadata=metadata
        )
```

### Plugin Configuration UI

For plugins with web-based configuration:

```python
class ConfigurableWebPlugin(IPluginInterface):
    def get_plugin_info(self):
        return {
            'name': 'ConfigurableWebPlugin',
            'version': '1.0.0',
            'description': 'Plugin with web configuration',
            'author': 'Your Name',
            'license': 'MIT',
            'has_web_config': True,  # Indicates web config available
            'config_endpoint': '/api/plugins/configurable-web/config'
        }
    
    def get_web_config_schema(self):
        """Return JSON schema for web configuration."""
        return {
            "type": "object",
            "properties": {
                "frequency": {
                    "type": "number",
                    "minimum": 20,
                    "maximum": 20000,
                    "default": 1000,
                    "title": "Frequency (Hz)",
                    "description": "Center frequency for processing"
                },
                "q_factor": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 10.0,
                    "default": 1.0,
                    "title": "Q Factor",
                    "description": "Quality factor for filter"
                },
                "enabled": {
                    "type": "boolean",
                    "default": True,
                    "title": "Enable Processing"
                }
            }
        }
    
    def set_web_config(self, config: Dict[str, Any]):
        """Set configuration from web interface."""
        self.frequency = config.get('frequency', 1000)
        self.q_factor = config.get('q_factor', 1.0)
        self.enabled = config.get('enabled', True)
        
        # Recalculate filter coefficients
        self._update_filter_coefficients()
```

## Plugin Testing Framework

### Automated Testing

```python
import pytest
import numpy as np
from datetime import datetime
from audio_processing.models import AudioConfig, AudioFrame
from audio_processing.plugin_manager import PluginManager

class PluginTestFramework:
    """Framework for testing audio plugins."""
    
    @staticmethod
    def create_test_frame(sample_rate=48000, channels=2, frame_size=480, 
                         frequency=1000, amplitude=0.1):
        """Create a test audio frame with sine wave."""
        t = np.linspace(0, frame_size/sample_rate, frame_size)
        sine_wave = amplitude * np.sin(2 * np.pi * frequency * t)
        
        # Create multi-channel data
        data = np.tile(sine_wave, (channels, 1))
        
        return AudioFrame(
            timestamp=datetime.now(),
            sample_rate=sample_rate,
            channels=channels,
            frame_size=frame_size,
            data=data
        )
    
    @staticmethod
    def measure_latency(plugin, frame, iterations=100):
        """Measure plugin processing latency."""
        import time
        
        # Warmup
        for _ in range(10):
            plugin.process_frame(frame)
        
        # Measure
        start_time = time.perf_counter()
        for _ in range(iterations):
            plugin.process_frame(frame)
        end_time = time.perf_counter()
        
        avg_latency_ms = ((end_time - start_time) / iterations) * 1000
        return avg_latency_ms
    
    @staticmethod
    def test_plugin_stability(plugin, frame, iterations=1000):
        """Test plugin stability over many iterations."""
        errors = []
        
        for i in range(iterations):
            try:
                result = plugin.process_frame(frame)
                
                # Check for NaN or infinite values
                if np.any(np.isnan(result.data)) or np.any(np.isinf(result.data)):
                    errors.append(f"Invalid values at iteration {i}")
                
                # Check output bounds
                if np.max(np.abs(result.data)) > 10.0:  # Reasonable bound
                    errors.append(f"Output too large at iteration {i}")
                    
            except Exception as e:
                errors.append(f"Exception at iteration {i}: {e}")
        
        return errors

# Example test using the framework
@pytest.mark.asyncio
async def test_my_plugin():
    from my_plugin import MyPlugin
    
    plugin = MyPlugin()
    config = AudioConfig()
    await plugin.initialize(config)
    
    # Test basic functionality
    frame = PluginTestFramework.create_test_frame()
    result = plugin.process_frame(frame)
    
    assert result.channels == frame.channels
    assert result.frame_size == frame.frame_size
    
    # Test performance
    latency = PluginTestFramework.measure_latency(plugin, frame)
    assert latency < 1.0  # Less than 1ms
    
    # Test stability
    errors = PluginTestFramework.test_plugin_stability(plugin, frame)
    assert len(errors) == 0, f"Stability issues: {errors}"
    
    await plugin.cleanup()
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_plugin_integration():
    """Test plugin integration with plugin manager."""
    config = AudioConfig()
    plugin_manager = PluginManager(config, plugin_dirs=["test_plugins"])
    
    await plugin_manager.start()
    
    # Load plugin
    await plugin_manager.load_plugin("MyPlugin")
    
    # Test plugin is loaded
    plugin = plugin_manager.get_plugin("MyPlugin")
    assert plugin is not None
    
    # Test processing
    frame = PluginTestFramework.create_test_frame()
    result = plugin.process_frame(frame)
    assert result is not None
    
    # Test hot reload
    await plugin_manager.reload_plugin("MyPlugin")
    reloaded_plugin = plugin_manager.get_plugin("MyPlugin")
    assert reloaded_plugin is not None
    
    await plugin_manager.stop()
```

## Plugin Distribution

### Plugin Packaging

Create a `plugin_info.json` file for your plugin:

```json
{
  "name": "MyAwesomePlugin",
  "version": "1.2.0",
  "description": "An awesome audio processing plugin",
  "author": "Your Name",
  "email": "your.email@example.com",
  "license": "MIT",
  "homepage": "https://github.com/yourname/my-awesome-plugin",
  "keywords": ["audio", "effects", "reverb"],
  "categories": ["effects", "spatial"],
  "main": "my_awesome_plugin.py",
  "dependencies": {
    "numpy": ">=1.20.0",
    "scipy": ">=1.7.0"
  },
  "system_requirements": {
    "min_python_version": "3.8",
    "min_system_version": "1.0.0"
  },
  "configuration_schema": {
    "type": "object",
    "properties": {
      "room_size": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "default": 0.5
      }
    }
  }
}
```

### Plugin Installation

```python
# Plugin installer utility
import json
import shutil
from pathlib import Path

class PluginInstaller:
    def __init__(self, plugin_dir: str = "plugins"):
        self.plugin_dir = Path(plugin_dir)
        self.plugin_dir.mkdir(exist_ok=True)
    
    def install_plugin(self, plugin_path: str):
        """Install plugin from file or directory."""
        source_path = Path(plugin_path)
        
        if source_path.is_file() and source_path.suffix == '.py':
            # Single file plugin
            plugin_name = source_path.stem
            dest_path = self.plugin_dir / source_path.name
            shutil.copy2(source_path, dest_path)
            
        elif source_path.is_dir():
            # Plugin package
            info_file = source_path / "plugin_info.json"
            if info_file.exists():
                with open(info_file) as f:
                    info = json.load(f)
                plugin_name = info['name']
            else:
                plugin_name = source_path.name
            
            dest_path = self.plugin_dir / plugin_name
            shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
        
        print(f"Plugin {plugin_name} installed successfully")
        return plugin_name
    
    def uninstall_plugin(self, plugin_name: str):
        """Uninstall plugin."""
        plugin_file = self.plugin_dir / f"{plugin_name}.py"
        plugin_dir = self.plugin_dir / plugin_name
        
        if plugin_file.exists():
            plugin_file.unlink()
        elif plugin_dir.exists():
            shutil.rmtree(plugin_dir)
        else:
            raise FileNotFoundError(f"Plugin {plugin_name} not found")
        
        print(f"Plugin {plugin_name} uninstalled successfully")
```

## Support

For questions and support:
- Check the API documentation
- Review example plugins in the `plugins/` directory
- Submit issues on the project repository
- Join our developer community forum
- Read the developer guide for advanced topics