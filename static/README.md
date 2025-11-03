# Web Control Interface Static Assets

This directory contains static assets for the Audio Processing System web control interface.

## Structure

- `css/` - Stylesheets for the web interface
- `js/` - JavaScript files for client-side functionality
- `images/` - Images and icons used in the interface

## Usage

The static files are automatically served by the ControlService at `/static/` when the web server is running.

## Development

To modify the web interface:

1. Edit the HTML template in `src/audio_processing/services/control.py`
2. Add custom CSS files to the `css/` directory
3. Add custom JavaScript files to the `js/` directory
4. Reference new assets in the HTML template

## Features

The web interface provides:

- **Real-time System Monitoring**: Live updates of system status, service health, and performance metrics
- **Service Management**: Start, stop, and restart individual audio processing services
- **Configuration Management**: Update system configuration parameters with validation
- **Performance Metrics**: Detailed view of CPU usage, memory consumption, latency, and audio quality metrics
- **System Logs**: Real-time log viewing with filtering capabilities

## WebSocket API

The interface uses WebSocket connections for real-time updates:

- **Connection**: `ws://localhost:8080/ws`
- **Message Format**: JSON with `type` and `data` fields
- **Supported Message Types**:
  - `initial_status` - Initial system status on connection
  - `metrics_update` - Real-time metrics updates
  - `service_status_changed` - Service status changes
  - `config_updated` - Configuration change notifications
  - `log_entry` - New log entries

## REST API Endpoints

- `GET /api/status` - Get system status
- `GET /api/config` - Get current configuration
- `POST /api/config` - Update configuration
- `GET /api/services` - Get service status
- `POST /api/services/control` - Control services (start/stop/restart)
- `GET /api/metrics` - Get system metrics
- `GET /api/metrics/{service_name}` - Get service-specific metrics