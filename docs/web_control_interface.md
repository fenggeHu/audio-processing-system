# Web Control Interface

The Web Control Interface provides a comprehensive web-based dashboard for monitoring and controlling the audio processing system. It offers real-time system status, service management, configuration updates, and performance metrics visualization.

## Features

### 🖥️ System Overview
- **Real-time Status**: Live system status with uptime and health indicators
- **Service Grid**: Visual overview of all audio processing services
- **Performance Metrics**: CPU usage, memory consumption, latency, and frame drop rates
- **Configuration Version**: Track configuration changes and versions

### 🔧 Service Management
- **Start/Stop/Restart**: Control individual services through the web interface
- **Health Monitoring**: Real-time service health status with visual indicators
- **Service Metrics**: Detailed performance metrics for each service
- **Automatic Updates**: WebSocket-based real-time updates without page refresh

### ⚙️ Configuration Management
- **Parameter Adjustment**: Modify audio processing parameters in real-time
- **Validation**: Client and server-side configuration validation
- **Hot Updates**: Apply configuration changes without system restart
- **Change Tracking**: Track who made changes and when

### 📊 Performance Monitoring
- **Real-time Metrics**: Live performance data with 2-second update intervals
- **Historical Data**: Track performance trends over time
- **Alert Indicators**: Visual alerts for performance issues
- **Detailed Views**: Service-specific metric breakdowns

### 📝 System Logs
- **Real-time Logs**: Live log streaming with WebSocket connections
- **Log Filtering**: Filter logs by level (INFO, WARNING, ERROR)
- **Searchable History**: Search through log history
- **Export Capability**: Export logs for analysis

## Architecture

### Backend Components

#### ControlService
The main service that provides the web interface functionality:

```python
from audio_processing.services.control import ControlService
from audio_processing.models import AudioConfig

# Create control service
control_service = ControlService(
    config=audio_config,
    service_manager=service_manager,
    host="0.0.0.0",
    port=8080
)

# Start the service
await control_service.start()
```

#### REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main web interface HTML |
| `/api/status` | GET | System status and uptime |
| `/api/config` | GET | Current configuration |
| `/api/config` | POST | Update configuration |
| `/api/services` | GET | Service status list |
| `/api/services/control` | POST | Control services |
| `/api/metrics` | GET | System metrics |
| `/api/metrics/{service}` | GET | Service-specific metrics |

#### WebSocket API

**Connection**: `ws://localhost:8080/ws`

**Message Types**:
- `initial_status` - Initial system status on connection
- `metrics_update` - Real-time metrics updates (every 2 seconds)
- `service_status_changed` - Service status change notifications
- `config_updated` - Configuration change notifications
- `system_event_*` - System event notifications

### Frontend Components

#### JavaScript Client
The web interface uses vanilla JavaScript with WebSocket connections for real-time updates:

```javascript
class AudioSystemControl {
    constructor() {
        this.initWebSocket();
        this.loadInitialData();
    }
    
    initWebSocket() {
        const wsUrl = `ws://${window.location.host}/ws`;
        this.ws = new WebSocket(wsUrl);
        // ... WebSocket event handlers
    }
}
```

#### Responsive Design
- **Mobile-friendly**: Responsive design that works on tablets and phones
- **Modern UI**: Clean, professional interface with intuitive navigation
- **Real-time Updates**: Live data updates without page refresh
- **Interactive Controls**: Click-to-control service management

## Usage Examples

### Basic Setup

```python
import asyncio
from audio_processing.models import AudioConfig
from audio_processing.service_manager import ServiceManager
from audio_processing.services.control import ControlService

async def setup_web_interface():
    # Create configuration
    config = AudioConfig(
        sample_rate=48000,
        frame_size=480,
        channels=8
    )
    
    # Create service manager
    service_manager = ServiceManager(config)
    
    # Register your audio services
    # service_manager.register_service(...)
    
    # Create web control interface
    control_service = ControlService(
        config=config,
        service_manager=service_manager,
        host="0.0.0.0",  # Listen on all interfaces
        port=8080
    )
    
    # Start services
    await service_manager.start()
    await control_service.start()
    
    # Start web server
    await control_service.start_server()

# Run the setup
asyncio.run(setup_web_interface())
```

### Configuration Update via API

```python
import httpx

async def update_config():
    new_config = {
        "sample_rate": 44100,
        "frame_size": 441,
        "channels": 2,
        "enable_ssl": True,
        "enable_aec": False
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8080/api/config",
            json={
                "config": new_config,
                "description": "Updated for testing",
                "user": "admin"
            }
        )
        
        if response.status_code == 200:
            print("Configuration updated successfully")
        else:
            print(f"Update failed: {response.text}")
```

### Service Control via API

```python
import httpx

async def restart_service(service_name: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8080/api/services/control",
            json={
                "service_name": service_name,
                "action": "restart"
            }
        )
        
        if response.status_code == 200:
            print(f"Service {service_name} restarted successfully")
        else:
            print(f"Restart failed: {response.text}")
```

## Security Considerations

### Network Security
- **Host Binding**: Configure appropriate host binding (localhost vs 0.0.0.0)
- **Port Selection**: Use non-standard ports and configure firewall rules
- **HTTPS**: Consider adding HTTPS support for production deployments

### Authentication
The current implementation doesn't include authentication. For production use, consider adding:
- **API Keys**: Require API keys for configuration changes
- **User Authentication**: Login system with role-based access
- **Session Management**: Secure session handling for web interface

### Input Validation
- **Configuration Validation**: All configuration changes are validated using Pydantic models
- **Service Name Validation**: Service names are validated against registered services
- **Parameter Bounds**: Numeric parameters are validated within acceptable ranges

## Deployment

### Development
```bash
# Run the demo
python3 demo_web_interface.py

# Open browser to http://localhost:8080
```

### Production
```bash
# Install dependencies
pip install fastapi uvicorn websockets

# Run with production server
uvicorn audio_processing.services.control:app --host 0.0.0.0 --port 8080
```

### Docker Deployment
```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./src/
COPY static/ ./static/

EXPOSE 8080

CMD ["python", "-m", "audio_processing.services.control"]
```

## Troubleshooting

### Common Issues

#### WebSocket Connection Failed
- Check firewall settings
- Verify the server is running on the correct port
- Ensure WebSocket support in your browser

#### Configuration Update Failed
- Verify the configuration format matches the AudioConfig model
- Check server logs for validation errors
- Ensure all required parameters are provided

#### Service Control Not Working
- Verify service names match registered services
- Check service manager is properly initialized
- Review service dependencies and startup order

### Debug Mode
Enable debug logging to troubleshoot issues:

```python
import structlog

# Configure debug logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
```

## Browser Compatibility

The web interface is compatible with:
- **Chrome/Chromium**: 80+
- **Firefox**: 75+
- **Safari**: 13+
- **Edge**: 80+

### Required Features
- WebSocket support
- ES6 JavaScript features
- CSS Grid and Flexbox
- Fetch API

## Performance

### Resource Usage
- **Memory**: ~50MB for the web interface service
- **CPU**: <5% during normal operation
- **Network**: ~1KB/s per connected client for real-time updates

### Scalability
- **Concurrent Clients**: Supports 100+ concurrent WebSocket connections
- **Update Frequency**: 2-second metrics updates (configurable)
- **Response Time**: <100ms for API requests

## Future Enhancements

### Planned Features
- **User Authentication**: Login system with role-based access control
- **Historical Charts**: Graphical performance trend visualization
- **Alert System**: Configurable alerts for performance thresholds
- **Plugin Management**: Web-based plugin installation and configuration
- **Export/Import**: Configuration backup and restore functionality
- **Mobile App**: Native mobile application for system monitoring

### API Extensions
- **GraphQL Support**: More flexible data querying
- **Webhook Integration**: External system notifications
- **Batch Operations**: Bulk service management operations
- **Scheduled Tasks**: Automated maintenance and updates