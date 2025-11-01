# Audio Processing System

A real-time audio processing system designed for multimedia classrooms, providing advanced audio enhancement capabilities including sound source localization, beamforming, echo cancellation, noise reduction, and automatic gain control.

## Features

- **Multi-channel Audio Capture**: Synchronized capture from multiple microphones
- **Sound Source Localization (SSL)**: Real-time direction estimation using SRP-PHAT
- **Beamforming**: Adaptive and fixed beamforming algorithms (DAS, MVDR)
- **Acoustic Echo Cancellation (AEC)**: Advanced echo suppression with double-talk detection
- **Noise Reduction**: RNNoise-based real-time denoising
- **Automatic Gain Control (AGC)**: Intelligent level management with anti-howling
- **Dual Output**: Separate optimization for PA system and recording
- **Plugin System**: Extensible architecture for custom processing modules
- **Web Interface**: Real-time monitoring and configuration

## Architecture

The system is built using Python 3.10+ with an async-first architecture:

- **Modular Design**: Each processing stage is a separate service
- **Dependency Injection**: Clean service management and testing
- **Event-Driven**: Loose coupling through event bus
- **Performance Monitoring**: Real-time metrics and health checks
- **Configuration Management**: Hot-reload configuration system

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd audio-processing-system

# Install dependencies
pip install -e .

# Install development dependencies
pip install -e ".[dev]"
```

### Basic Usage

```python
from audio_processing import AudioConfig, ServiceManager
from audio_processing.services import CaptureService, SSLService

# Create configuration
config = AudioConfig(
    sample_rate=48000,
    frame_size=480,  # 10ms frames
    channels=8
)

# Setup service manager
manager = ServiceManager(config)

# Register services
manager.register_service(CaptureService)
manager.register_service(SSLService)

# Start system
await manager.start()

# System is now processing audio...

# Stop system
await manager.stop()
```

## Development

### Project Structure

```
src/audio_processing/
├── __init__.py              # Main package exports
├── models.py                # Data models (AudioFrame, AudioConfig, etc.)
├── interfaces.py            # Service interfaces
├── base.py                  # Base classes
├── container.py             # Dependency injection container
├── service_manager.py       # Service lifecycle management
├── exceptions.py            # Custom exceptions
├── services/                # Audio processing services
│   ├── capture.py          # Audio capture service
│   ├── ssl.py              # Sound source localization
│   ├── beamformer.py       # Beamforming service
│   ├── aec.py              # Echo cancellation
│   ├── denoise.py          # Noise reduction
│   └── agc.py              # Automatic gain control
└── utils/                   # Utility functions
    ├── audio.py            # Audio processing utilities
    ├── math.py             # Mathematical functions
    └── config.py           # Configuration helpers
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/audio_processing

# Run specific test file
pytest tests/test_models.py
```

### Code Quality

```bash
# Format code
black src/ tests/

# Type checking
mypy src/

# Linting
ruff src/ tests/
```

## Configuration

The system uses a hierarchical configuration system:

```python
config = AudioConfig(
    # Basic audio parameters
    sample_rate=48000,
    frame_size=480,
    channels=8,
    
    # Processing enables
    enable_ssl=True,
    enable_beamforming=True,
    enable_aec=True,
    enable_denoise=True,
    enable_agc=True,
    
    # Performance limits
    max_latency_ms=40.0,
    cpu_limit_percent=80.0
)
```

## Performance

Target performance metrics for classroom deployment:

- **Latency**: < 40ms end-to-end (PA output)
- **Echo Suppression**: > 20dB ERLE
- **Speech Quality**: PESQ > 3.0 (recording output)
- **CPU Usage**: < 80% on typical hardware
- **Reliability**: > 99.9% uptime during 8-hour sessions

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## Support

For questions and support, please open an issue on the project repository.