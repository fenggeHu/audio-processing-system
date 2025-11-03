# Audio Processing System API Reference

## Overview

This document provides comprehensive API reference for the Audio Processing System. The system provides REST APIs, WebSocket APIs, and Python APIs for controlling and monitoring audio processing services.

## REST API Endpoints

### Base URL
```
http://localhost:8080
```

### System Status

#### GET /api/status
Get current system status and uptime information.

**Response:**
```json
{
  "running": true,
  "uptime_seconds": 3600.5,
  "services": {
    "BeamformerService": {
      "running": true,
      "healthy": true,
      "metrics": {...}
    }
  },
  "system_metrics": {
    "cpu_usage_percent": 25.5,
    "memory_usage_mb": 512.0,
    "processing_latency_ms": 2.1,
    "frame_drop_rate": 0.01
  },
  "config_version": 1
}
```

### Configuration Management

#### GET /api/config
Get current system configuration.

**Response:**
```json
{
  "sample_rate": 48000,
  "frame_size": 480,
  "channels": 8,
  "buffer_size": 4096,
  "enable_ssl": true,
  "enable_beamforming": true,
  "enable_aec": true,
  "enable_denoise": true,
  "enable_agc": true,
  "max_latency_ms": 40.0,
  "cpu_limit_percent": 80.0
}
```

#### POST /api/config
Update system configuration.

**Request Body:**
```json
{
  "config": {
    "sample_rate": 44100,
    "frame_size": 441,
    "channels": 2,
    "enable_ssl": false
  },
  "description": "Updated for testing",
  "user": "admin"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Configuration updated successfully"
}
```

### Service Management

#### GET /api/services
Get status of all registered services.

**Response:**
```json
{
  "BeamformerService": {
    "running": true,
    "healthy": true,
    "metrics": {
      "processing_latency_ms": 1.5,
      "cpu_usage_percent": 15.2,
      "memory_usage_mb": 128.0
    }
  },
  "AGCService": {
    "running": false,
    "healthy": false,
    "metrics": {}
  }
}
```

#### POST /api/services/control
Control service lifecycle (start/stop/restart).

**Request Body:**
```json
{
  "service_name": "BeamformerService",
  "action": "restart"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Service restart completed"
}
```

### Metrics

#### GET /api/metrics
Get system-wide performance metrics.

**Response:**
```json
{
  "BeamformerService": {
    "processing_latency_ms": 1.5,
    "end_to_end_latency_ms": 12.3,
    "cpu_usage_percent": 15.2,
    "memory_usage_mb": 128.0,
    "input_level_dbfs": -18.5,
    "output_level_dbfs": -20.1,
    "frames_processed": 12000,
    "frames_dropped": 5
  }
}
```

#### GET /api/metrics/{service_name}
Get metrics for a specific service.

**Response:**
```json
{
  "processing_latency_ms": 1.5,
  "end_to_end_latency_ms": 12.3,
  "snr_db": 25.8,
  "cpu_usage_percent": 15.2,
  "memory_usage_mb": 128.0,
  "frames_processed": 12000,
  "frames_dropped": 5
}
```

## WebSocket API

### Connection
```javascript
const ws = new WebSocket('ws://localhost:8080/ws');
```

### Message Types

#### initial_status
Sent immediately after connection with current system status.

```json
{
  "type": "initial_status",
  "data": {
    "running": true,
    "uptime_seconds": 3600.5,
    "services": {...},
    "system_metrics": {...}
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### metrics_update
Real-time metrics updates (sent every 2 seconds).

```json
{
  "type": "metrics_update",
  "data": {
    "cpu_usage_percent": 25.5,
    "memory_usage_mb": 512.0,
    "processing_latency_ms": 2.1,
    "frame_drop_rate": 0.01
  },
  "timestamp": "2024-01-15T10:30:02Z"
}
```

#### service_status_changed
Notification when service status changes.

```json
{
  "type": "service_status_changed",
  "data": {
    "service_name": "BeamformerService",
    "running": false,
    "healthy": false,
    "previous_status": "running"
  },
  "timestamp": "2024-01-15T10:30:05Z"
}
```

#### config_updated
Notification when configuration is updated.

```json
{
  "type": "config_updated",
  "data": {
    "config": {...},
    "description": "Updated sample rate",
    "user": "admin"
  },
  "timestamp": "2024-01-15T10:30:10Z"
}
```

## Python API

### Core Interfaces

#### IAudioService
Base interface for all audio processing services.

```python
from audio_processing.interfaces import IAudioService
from audio_processing.models import AudioFrame, ProcessingResult, AudioConfig, AudioMetrics

class MyAudioService(IAudioService):
    async def start(self) -> None:
        """Start the service."""
        pass
    
    async def stop(self) -> None:
        """Stop the service."""
        pass
    
    async def process(self, frame: AudioFrame) -> ProcessingResult:
        """Process audio frame."""
        pass
    
    def get_metrics(self) -> AudioMetrics:
        """Get performance metrics."""
        pass
    
    def get_config(self) -> AudioConfig:
        """Get current configuration."""
        pass
    
    async def update_config(self, config: AudioConfig) -> None:
        """Update configuration."""
        pass
    
    @property
    def is_running(self) -> bool:
        """Check if service is running."""
        pass
    
    @property
    def service_name(self) -> str:
        """Get service name."""
        pass
```

#### IPluginInterface
Interface for audio processing plugins.

```python
from audio_processing.interfaces import IPluginInterface
from audio_processing.models import AudioConfig, AudioFrame
from typing import Dict, Any, List

class MyPlugin(IPluginInterface):
    def get_plugin_info(self) -> Dict[str, Any]:
        """Get plugin metadata."""
        return {
            'name': 'MyPlugin',
            'version': '1.0.0',
            'description': 'My audio plugin',
            'author': 'Your Name',
            'license': 'MIT'
        }
    
    def get_required_dependencies(self) -> List[str]:
        """Get required dependencies."""
        return []
    
    async def initialize(self, config: AudioConfig) -> None:
        """Initialize plugin."""
        pass
    
    async def cleanup(self) -> None:
        """Cleanup plugin resources."""
        pass
    
    def process_frame(self, frame: AudioFrame) -> AudioFrame:
        """Process audio frame."""
        return frame
```

### Data Models

#### AudioFrame
Represents a single frame of audio data.

```python
from dataclasses import dataclass
from datetime import datetime
import numpy as np

@dataclass
class AudioFrame:
    timestamp: datetime
    sample_rate: int
    channels: int
    frame_size: int
    data: np.ndarray  # shape: (channels, frame_size)
    metadata: Optional[Dict[str, Any]] = None
    
    def to_mono(self) -> 'AudioFrame':
        """Convert to mono."""
        pass
    
    def resample(self, target_rate: int) -> 'AudioFrame':
        """Resample to target rate."""
        pass
    
    def get_rms_level(self) -> float:
        """Get RMS level in dB."""
        pass
```

#### AudioConfig
System configuration model.

```python
from pydantic import BaseModel, Field

class AudioConfig(BaseModel):
    sample_rate: int = Field(48000, ge=8000, le=96000)
    frame_size: int = Field(480, ge=64, le=2048)
    channels: int = Field(8, ge=1, le=32)
    buffer_size: int = Field(4096, ge=512, le=16384)
    
    # Processing parameters
    enable_ssl: bool = True
    enable_beamforming: bool = True
    enable_aec: bool = True
    enable_denoise: bool = True
    enable_agc: bool = True
    
    # Performance settings
    max_latency_ms: float = Field(40.0, ge=10.0, le=200.0)
    cpu_limit_percent: float = Field(80.0, ge=10.0, le=100.0)
```

#### AudioMetrics
Performance metrics model.

```python
from pydantic import BaseModel, Field

class AudioMetrics(BaseModel):
    # Latency metrics
    processing_latency_ms: float = 0.0
    end_to_end_latency_ms: float = 0.0
    
    # Quality metrics
    snr_db: Optional[float] = None
    thd_percent: Optional[float] = None
    erle_db: Optional[float] = None
    
    # System metrics
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    
    # Audio levels
    input_level_dbfs: float = -60.0
    output_level_dbfs: float = -60.0
    
    # Processing statistics
    frames_processed: int = 0
    frames_dropped: int = 0
```

### Service Manager

#### ServiceManager
Manages service lifecycle and coordination.

```python
from audio_processing.service_manager import ServiceManager
from audio_processing.models import AudioConfig

# Create service manager
config = AudioConfig()
service_manager = ServiceManager(config)

# Register services
service_manager.register_service(
    service_type=IAudioService,
    implementation=MyAudioService,
    name="MyService"
)

# Start all services
await service_manager.start()

# Get service instance
service = await service_manager.get_service_by_name("MyService")

# Update configuration
new_config = AudioConfig(sample_rate=44100)
await service_manager.update_config(new_config)

# Stop all services
await service_manager.stop()
```

### Plugin Manager

#### PluginManager
Manages plugin loading and execution.

```python
from audio_processing.plugin_manager import PluginManager
from audio_processing.models import AudioConfig

# Create plugin manager
config = AudioConfig()
plugin_manager = PluginManager(config, plugin_dirs=["plugins"])

# Start plugin manager
await plugin_manager.start()

# Discover plugins
plugins = await plugin_manager.discover_plugins()

# Load plugin
await plugin_manager.load_plugin("MyPlugin")

# Get plugin instance
plugin = plugin_manager.get_plugin("MyPlugin")

# Unload plugin
await plugin_manager.unload_plugin("MyPlugin")
```

## Error Handling

### HTTP Status Codes

- `200 OK` - Request successful
- `400 Bad Request` - Invalid request data
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

### Error Response Format

```json
{
  "error": "Configuration validation failed",
  "detail": "Sample rate must be between 8000 and 96000 Hz",
  "code": "VALIDATION_ERROR"
}
```

### Python Exceptions

```python
from audio_processing.exceptions import (
    ServiceError,
    ConfigError,
    ProcessingError,
    PluginError
)

try:
    await service.start()
except ServiceError as e:
    print(f"Service failed to start: {e}")

try:
    await service.update_config(config)
except ConfigError as e:
    print(f"Invalid configuration: {e}")
```

## Rate Limits

- REST API: 100 requests per minute per client
- WebSocket: 1000 messages per minute per connection
- Configuration updates: 10 per minute per client

## Authentication

Currently, the system does not implement authentication. For production deployments, consider adding:

- API key authentication for REST endpoints
- JWT tokens for WebSocket connections
- Role-based access control for configuration changes

## Examples

### Basic Service Usage

```python
import asyncio
from audio_processing.models import AudioConfig
from audio_processing.service_manager import ServiceManager

async def main():
    # Create configuration
    config = AudioConfig(
        sample_rate=48000,
        frame_size=480,
        channels=8
    )
    
    # Create and start service manager
    service_manager = ServiceManager(config)
    await service_manager.start()
    
    # Get system status
    status = service_manager.get_service_status()
    print(f"Services running: {len(status)}")
    
    # Stop services
    await service_manager.stop()

asyncio.run(main())
```

### Plugin Development

```python
from audio_processing.interfaces import IPluginInterface
from audio_processing.models import AudioConfig, AudioFrame
import numpy as np

class GainPlugin(IPluginInterface):
    def __init__(self):
        self.gain = 1.0
    
    def get_plugin_info(self):
        return {
            'name': 'GainPlugin',
            'version': '1.0.0',
            'description': 'Simple gain control plugin',
            'author': 'Audio Team',
            'license': 'MIT'
        }
    
    def get_required_dependencies(self):
        return []
    
    async def initialize(self, config: AudioConfig):
        pass
    
    async def cleanup(self):
        pass
    
    def process_frame(self, frame: AudioFrame) -> AudioFrame:
        output_data = frame.data * self.gain
        
        return AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            frame_size=frame.frame_size,
            data=output_data,
            metadata={'processed_by': 'GainPlugin'}
        )
```

### Web Interface Integration

```javascript
class AudioSystemClient {
    constructor(baseUrl = 'http://localhost:8080') {
        this.baseUrl = baseUrl;
        this.ws = null;
    }
    
    async getStatus() {
        const response = await fetch(`${this.baseUrl}/api/status`);
        return response.json();
    }
    
    async updateConfig(config) {
        const response = await fetch(`${this.baseUrl}/api/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                config: config,
                user: 'web_client'
            })
        });
        return response.json();
    }
    
    connectWebSocket() {
        this.ws = new WebSocket(`ws://localhost:8080/ws`);
        
        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };
    }
    
    handleMessage(message) {
        switch (message.type) {
            case 'metrics_update':
                this.updateMetrics(message.data);
                break;
            case 'service_status_changed':
                this.updateServiceStatus(message.data);
                break;
        }
    }
}
```
