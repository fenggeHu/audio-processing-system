# Developer Guide

## Getting Started

This guide helps developers integrate with and extend the Audio Processing System. It covers system architecture, development workflows, and best practices.

## System Architecture

### Core Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Control   │    │  Service Manager │    │ Plugin Manager  │
│   Interface     │◄──►│                 │◄──►│                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       ▼                       ▼
         │              ┌─────────────────┐    ┌─────────────────┐
         │              │ Audio Services  │    │    Plugins      │
         │              │ - Beamformer    │    │ - Reverb        │
         │              │ - AGC           │    │ - EQ            │
         │              │ - AEC           │    │ - Custom        │
         │              └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Audio Processing Pipeline                     │
│  Input → Frame Buffer → Services → Plugins → Output             │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Audio Input**: Raw audio frames enter the system
2. **Frame Processing**: Each service processes frames sequentially
3. **Plugin Processing**: Loaded plugins apply additional effects
4. **Output**: Processed audio is delivered to output streams
5. **Monitoring**: Metrics are collected and exposed via APIs

## Development Environment Setup

### Prerequisites

```bash
# Python 3.10+
python --version

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt
```

### Project Structure

```
audio-processing-system/
├── src/
│   └── audio_processing/
│       ├── __init__.py
│       ├── models.py              # Data models
│       ├── interfaces.py          # Core interfaces
│       ├── base.py               # Base classes
│       ├── service_manager.py    # Service coordination
│       ├── plugin_manager.py     # Plugin management
│       ├── config_manager.py     # Configuration management
│       ├── container.py          # Dependency injection
│       ├── error_handler.py      # Error handling
│       ├── fault_tolerance.py    # Fault tolerance
│       ├── quality_assessment.py # Quality assessment
│       ├── communication/        # Communication framework
│       │   ├── event_bus.py      # Event system
│       │   ├── message_router.py # Message routing
│       │   └── audio_pipeline.py # Processing pipeline
│       └── services/
│           ├── control.py        # Web control service
│           ├── beamformer.py     # Beamforming service
│           ├── agc.py           # AGC service
│           ├── aec.py           # AEC service
│           ├── denoise.py       # Noise reduction
│           ├── ssl.py           # Sound source localization
│           ├── capture.py       # Audio capture
│           ├── mixer.py         # Audio mixing
│           ├── recorder.py      # Audio recording
│           └── telemetry.py     # Monitoring
├── plugins/                      # Plugin directory
├── docs/                        # Documentation
├── tests/                       # Consolidated test suite
├── examples/                    # Example code
├── tools/                       # Development and deployment tools
├── config/                      # Configuration files
└── deploy/                      # Deployment configs
```

## Creating Audio Services

### Basic Service Implementation

```python
from audio_processing.base import BaseAudioProcessor
from audio_processing.models import AudioConfig, AudioFrame
import numpy as np

class MyAudioService(BaseAudioProcessor):
    def __init__(self, config: AudioConfig):
        super().__init__("MyAudioService", config)
        self.gain = 1.0
    
    async def _initialize(self) -> None:
        """Initialize service resources."""
        self.logger.info("MyAudioService initializing")
        # Setup any required resources
    
    async def _cleanup(self) -> None:
        """Cleanup service resources."""
        self.logger.info("MyAudioService cleaning up")
        # Clean up resources
    
    async def _process_frame(self, frame: AudioFrame) -> AudioFrame:
        """Process a single audio frame."""
        # Apply gain to all channels
        output_data = frame.data * self.gain
        
        # Create output frame
        return AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            frame_size=frame.frame_size,
            data=output_data,
            metadata=frame.metadata
        )
    
    def set_gain(self, gain: float) -> None:
        """Set the gain value."""
        self.gain = max(0.0, min(2.0, gain))
        self.logger.info("Gain updated", gain=self.gain)
```

### Service Registration

```python
from audio_processing.service_manager import ServiceManager
from audio_processing.models import AudioConfig

# Create service manager
config = AudioConfig()
service_manager = ServiceManager(config)

# Register your service
service_manager.register_service(
    service_type=BaseAudioProcessor,
    implementation=MyAudioService,
    name="MyAudioService",
    singleton=True
)

# Start services
await service_manager.start()
```

### Advanced Service Features

#### Configuration Management

```python
class ConfigurableService(BaseAudioProcessor):
    def get_config_schema(self) -> Dict[str, Any]:
        """Define configuration schema."""
        return {
            "type": "object",
            "properties": {
                "gain": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 2.0,
                    "default": 1.0
                },
                "enabled": {
                    "type": "boolean",
                    "default": True
                }
            },
            "required": ["gain", "enabled"]
        }
    
    async def _on_config_changed(self, old_config: Dict[str, Any], 
                               new_config: Dict[str, Any]) -> None:
        """Handle configuration changes."""
        if old_config.get('gain') != new_config.get('gain'):
            self.gain = new_config['gain']
            self.logger.info("Gain updated via config", gain=self.gain)
```

#### Event Handling

```python
from audio_processing.interfaces import IEventHandler

class EventAwareService(BaseAudioProcessor, IEventHandler):
    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Handle system events."""
        if event_type == 'config_updated':
            await self._handle_config_update(event_data)
        elif event_type == 'service_health_changed':
            await self._handle_health_change(event_data)
    
    def get_supported_events(self) -> List[str]:
        """Get supported event types."""
        return ['config_updated', 'service_health_changed']
```

## Plugin Development

### Plugin Structure

```python
from audio_processing.interfaces import IPluginInterface
from audio_processing.models import AudioConfig, AudioFrame
import numpy as np

class MyPlugin(IPluginInterface):
    def __init__(self):
        self.parameters = {
            'intensity': 0.5,
            'enabled': True
        }
    
    def get_plugin_info(self) -> Dict[str, Any]:
        return {
            'name': 'MyPlugin',
            'version': '1.0.0',
            'description': 'Example audio processing plugin',
            'author': 'Your Name',
            'license': 'MIT',
            'categories': ['effects'],
            'keywords': ['audio', 'processing']
        }
    
    def get_required_dependencies(self) -> List[str]:
        return []  # No dependencies
    
    async def initialize(self, config: AudioConfig) -> None:
        """Initialize plugin with system config."""
        self.sample_rate = config.sample_rate
        self.channels = config.channels
    
    async def cleanup(self) -> None:
        """Cleanup plugin resources."""
        pass
    
    def process_frame(self, frame: AudioFrame) -> AudioFrame:
        """Main processing method."""
        if not self.parameters['enabled']:
            return frame
        
        # Apply processing
        output_data = self._apply_effect(frame.data)
        
        return AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            frame_size=frame.frame_size,
            data=output_data,
            metadata={'processed_by': 'MyPlugin'}
        )
    
    def _apply_effect(self, data: np.ndarray) -> np.ndarray:
        """Apply the audio effect."""
        intensity = self.parameters['intensity']
        # Your processing logic here
        return data * (1.0 + intensity * 0.1)
    
    # Optional: Parameter control
    def get_parameters(self) -> Dict[str, Any]:
        """Get current parameters."""
        return self.parameters.copy()
    
    def set_parameters(self, params: Dict[str, Any]) -> None:
        """Set parameters."""
        for key, value in params.items():
            if key in self.parameters:
                self.parameters[key] = value
```

### Plugin Testing

```python
import pytest
import numpy as np
from datetime import datetime
from your_plugin import MyPlugin
from audio_processing.models import AudioConfig, AudioFrame

@pytest.mark.asyncio
async def test_plugin_processing():
    plugin = MyPlugin()
    
    # Initialize
    config = AudioConfig(sample_rate=48000, channels=2, frame_size=480)
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
    
    # Process
    output = plugin.process_frame(frame)
    
    # Verify
    assert output.channels == 2
    assert output.frame_size == 480
    assert output.data.shape == (2, 480)
    assert 'processed_by' in output.metadata
    
    await plugin.cleanup()

def test_plugin_parameters():
    plugin = MyPlugin()
    
    # Test parameter getting/setting
    params = plugin.get_parameters()
    assert 'intensity' in params
    
    plugin.set_parameters({'intensity': 0.8})
    assert plugin.get_parameters()['intensity'] == 0.8
```

## Web API Integration

### Custom Endpoints

```python
from fastapi import APIRouter, HTTPException
from audio_processing.services.control import ControlService

# Create custom router
router = APIRouter(prefix="/api/custom")

@router.get("/my-service/status")
async def get_my_service_status():
    """Get custom service status."""
    try:
        service = await service_manager.get_service_by_name("MyAudioService")
        return {
            "running": service.is_running,
            "gain": service.gain,
            "metrics": service.get_metrics().model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/my-service/gain")
async def set_gain(gain: float):
    """Set service gain."""
    try:
        service = await service_manager.get_service_by_name("MyAudioService")
        service.set_gain(gain)
        return {"success": True, "gain": gain}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Add router to control service
control_service.app.include_router(router)
```

### WebSocket Extensions

```python
async def handle_custom_websocket_message(self, message: Dict[str, Any], 
                                        websocket: WebSocket) -> None:
    """Handle custom WebSocket messages."""
    if message.get('type') == 'get_custom_data':
        # Get custom data
        data = await self._get_custom_data()
        
        # Send response
        await self.connection_manager.send_personal_message(
            WebSocketMessage(type="custom_data", data=data),
            websocket
        )

# Extend ControlService
class ExtendedControlService(ControlService):
    async def _handle_websocket_message(self, message: Dict[str, Any], 
                                      websocket: WebSocket) -> None:
        # Handle custom messages first
        await self.handle_custom_websocket_message(message, websocket)
        
        # Fall back to parent handler
        await super()._handle_websocket_message(message, websocket)
```

## Testing

### Unit Testing

```python
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from audio_processing.models import AudioConfig
from your_service import MyAudioService

@pytest.fixture
async def service():
    config = AudioConfig()
    service = MyAudioService(config)
    await service.start()
    yield service
    await service.stop()

@pytest.mark.asyncio
async def test_service_lifecycle(service):
    """Test service start/stop."""
    assert service.is_running
    
    await service.stop()
    assert not service.is_running

@pytest.mark.asyncio
async def test_frame_processing(service):
    """Test audio frame processing."""
    frame = create_test_frame()
    result = await service.process(frame)
    
    assert result.success
    assert result.data is not None
    assert result.processing_time_ms > 0
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_service_integration():
    """Test service integration with service manager."""
    config = AudioConfig()
    service_manager = ServiceManager(config)
    
    # Register service
    service_manager.register_service(
        BaseAudioProcessor,
        MyAudioService,
        "TestService"
    )
    
    # Start
    await service_manager.start()
    
    # Test
    service = await service_manager.get_service_by_name("TestService")
    assert service.is_running
    
    # Cleanup
    await service_manager.stop()
```

### Performance Testing

```python
import time
import numpy as np

def test_processing_performance():
    """Test processing performance."""
    service = MyAudioService(AudioConfig())
    frame = create_test_frame()
    
    # Warmup
    for _ in range(10):
        service._process_frame(frame)
    
    # Measure
    start_time = time.time()
    iterations = 1000
    
    for _ in range(iterations):
        service._process_frame(frame)
    
    elapsed = time.time() - start_time
    avg_time_ms = (elapsed / iterations) * 1000
    
    # Assert performance requirements
    assert avg_time_ms < 1.0  # Less than 1ms per frame
```

## Deployment

### Docker Integration

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY src/ ./src/
COPY plugins/ ./plugins/
COPY docs/ ./docs/

# Expose ports
EXPOSE 8080

# Run application
CMD ["python", "-m", "audio_processing.main"]
```

### Configuration Management

```python
import os
from audio_processing.models import AudioConfig

def load_config() -> AudioConfig:
    """Load configuration from environment."""
    return AudioConfig(
        sample_rate=int(os.getenv('SAMPLE_RATE', '48000')),
        frame_size=int(os.getenv('FRAME_SIZE', '480')),
        channels=int(os.getenv('CHANNELS', '8')),
        enable_ssl=os.getenv('ENABLE_SSL', 'true').lower() == 'true',
        max_latency_ms=float(os.getenv('MAX_LATENCY_MS', '40.0'))
    )
```

## Best Practices

### Performance Optimization

1. **Minimize Memory Allocation**
   ```python
   # Pre-allocate buffers
   def __init__(self):
       self.buffer = np.zeros((channels, frame_size))
   
   def process_frame(self, frame):
       # Reuse buffer instead of creating new arrays
       np.copyto(self.buffer, frame.data)
       # Process in-place when possible
   ```

2. **Use Vectorized Operations**
   ```python
   # Good: Vectorized
   output = input_data * gain
   
   # Avoid: Element-wise loops
   for i in range(len(input_data)):
       output[i] = input_data[i] * gain
   ```

3. **Profile Critical Paths**
   ```python
   import cProfile
   
   def profile_processing():
       profiler = cProfile.Profile()
       profiler.enable()
       
       # Your processing code
       process_audio_frames()
       
       profiler.disable()
       profiler.print_stats(sort='cumulative')
   ```

### Error Handling

```python
from audio_processing.exceptions import ProcessingError

async def robust_processing(self, frame: AudioFrame) -> ProcessingResult:
    """Robust frame processing with error handling."""
    try:
        # Validate input
        if frame.data.shape[0] != self.expected_channels:
            raise ProcessingError("Channel count mismatch")
        
        # Process
        result = await self._process_frame(frame)
        
        # Validate output
        if result.data is None:
            raise ProcessingError("Processing returned no data")
        
        return ProcessingResult.success_result(result)
        
    except ProcessingError:
        # Re-raise processing errors
        raise
    except Exception as e:
        # Convert unexpected errors
        raise ProcessingError(f"Unexpected error: {e}")
```

### Logging

```python
import structlog

logger = structlog.get_logger(__name__)

class MyService(BaseAudioProcessor):
    async def _process_frame(self, frame: AudioFrame) -> AudioFrame:
        logger.debug(
            "Processing frame",
            service=self.service_name,
            channels=frame.channels,
            frame_size=frame.frame_size
        )
        
        try:
            result = self._do_processing(frame)
            
            logger.debug(
                "Frame processed successfully",
                processing_time_ms=self.last_processing_time
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "Frame processing failed",
                error=str(e),
                frame_timestamp=frame.timestamp
            )
            raise
```

### Resource Management

```python
class ResourceManagedService(BaseAudioProcessor):
    async def _initialize(self) -> None:
        """Initialize with proper resource management."""
        try:
            # Acquire resources
            self.buffer_pool = BufferPool(size=10)
            self.thread_pool = ThreadPoolExecutor(max_workers=2)
            
        except Exception as e:
            # Cleanup on failure
            await self._cleanup()
            raise ServiceError(f"Initialization failed: {e}")
    
    async def _cleanup(self) -> None:
        """Cleanup resources properly."""
        if hasattr(self, 'thread_pool'):
            self.thread_pool.shutdown(wait=True)
        
        if hasattr(self, 'buffer_pool'):
            self.buffer_pool.cleanup()
```

## Troubleshooting

### Common Issues

1. **High Latency**
   - Check frame size vs buffer size ratio
   - Profile processing functions
   - Verify no blocking I/O in processing path

2. **Memory Leaks**
   - Use memory profilers (memory_profiler, tracemalloc)
   - Check for circular references
   - Ensure proper cleanup in service lifecycle

3. **Service Startup Failures**
   - Check dependency order
   - Verify configuration validity
   - Review initialization logs

### Debug Tools

```python
# Memory usage tracking
import tracemalloc

tracemalloc.start()

# Your code here

current, peak = tracemalloc.get_traced_memory()
print(f"Current memory usage: {current / 1024 / 1024:.1f} MB")
print(f"Peak memory usage: {peak / 1024 / 1024:.1f} MB")

tracemalloc.stop()
```

```python
# Performance profiling
import time
from functools import wraps

def profile_time(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        print(f"{func.__name__} took {elapsed:.2f}ms")
        return result
    return wrapper

@profile_time
async def process_frame(self, frame):
    # Processing code
    pass
```

## Contributing

### Code Style

- Follow PEP 8
- Use type hints
- Write docstrings for public APIs
- Keep functions focused and small

### Pull Request Process

1. Fork the repository
2. Create feature branch
3. Write tests for new functionality
4. Ensure all tests pass
5. Update documentation
6. Submit pull request

### Development Workflow

```bash
# Setup development environment
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt

# Run tests
pytest tests/

# Run linting
flake8 src/
mypy src/

# Run integration tests
python run_integration_tests.py

# Build documentation
cd docs && make html
```
