# Production Audio Processing System

A production-grade audio processing system designed for multimedia classroom environments with real-time audio processing capabilities.

## 📚 文档导航

- **[STARTUP_GUIDE.md](STARTUP_GUIDE.md)** - 系统启动指南，包含两种启动方式的详细说明
- **[WEB_INTERFACE_GUIDE.md](WEB_INTERFACE_GUIDE.md)** - Web界面完整指南，功能说明和使用方法
- **[README.md](README.md)** - 项目概述、安装和基本使用说明 (本文档)

## Features

- **Real Hardware Audio Processing**: Removes all mock/test code, uses actual hardware via PortAudio
- **Cross-Platform Support**: Linux (ALSA), macOS (CoreAudio), Windows (WASAPI)
- **Embedded System Optimization**: Low memory mode, CPU optimization, real-time scheduling
- **Modular Architecture**: Pluggable components for audio processing
- **Performance Monitoring**: Comprehensive benchmarking and optimization tools
- **Web-Based Visualization**: Real-time monitoring and control interface

## Architecture

The system is built with a modular architecture:

- **Audio Core** (`src/audio_core/`): Hardware interfaces and low-level audio operations
- **Processing** (`src/processing/`): High-level audio processing components and algorithms
- **Visualization** (`src/visualization/`): Real-time monitoring and web interfaces
- **Configuration** (`src/config/`): System settings and platform-specific configurations
- **Tools** (`src/tools/`): Performance benchmarking and optimization utilities

## Installation

### Prerequisites

#### Linux (Ubuntu/Debian)
```bash
sudo apt-get update
sudo apt-get install -y \
    portaudio19-dev \
    libasound2-dev \
    python3-dev \
    python3-pip
```

#### macOS
```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install PortAudio
brew install portaudio
```

#### Windows
```bash
# Install via conda (recommended)
conda install portaudio

# Or install via pip (may require Visual Studio Build Tools)
pip install pyaudio
```

### Install the Package

```bash
# Clone the repository
git clone <repository-url>
cd production-audio-system

# Install in development mode
pip install -e .

# Or install with all dependencies
pip install -e ".[dev,embedded,performance]"
```

### Platform-Specific Dependencies

Install platform-specific audio dependencies:

```bash
# Linux
pip install -r requirements-linux.txt

# macOS  
pip install -r requirements-macos.txt

# Windows
pip install -r requirements-windows.txt
```

## Quick Start

### Basic Usage

```bash
# Start the audio processing system
audio-system start

# Run performance benchmarks
audio-system benchmark

# Show system configuration
audio-system config-info

# Get help
audio-system --help
```

### Embedded System Setup

```bash
# Enable embedded optimizations
audio-system start --embedded

# Setup cross-compilation for ARM64
audio-system cross-compile --target linux-arm64

# List available cross-compilation targets
audio-system cross-compile --list-targets
```

## Configuration

### System Configuration

The system automatically detects and configures itself based on:

- **Platform**: Linux, macOS, or Windows
- **CPU Architecture**: x86_64, ARM64, ARM32
- **Available Memory**: Adjusts buffer sizes and thread counts
- **Audio Hardware**: Detects and configures audio devices

### Manual Configuration

Create configuration files in the project directory:

```yaml
# audio_config.yaml
audio:
  sample_rate: 48000
  buffer_size: 256
  channels: 2

embedded:
  memory_mode: "low"  # low, normal, high
  enable_realtime: true
  thread_count: 2

platform:
  backend: "alsa"  # alsa, pulse, coreaudio, wasapi
  device: "default"
```

## Performance Benchmarking

Run comprehensive performance benchmarks:

```bash
# Full benchmark suite
audio-system benchmark --output benchmark_results.json

# Quick benchmark
audio-system benchmark --quick

# Custom benchmark
python -m src.tools.benchmark
```

### Benchmark Categories

- **NumPy Operations**: FFT, IFFT, basic array operations
- **Audio Filtering**: Various filter orders and sample rates
- **WebRTC Components**: Voice Activity Detection, AEC, AGC
- **Memory Operations**: Allocation, copying, buffer management
- **Threading Performance**: Multi-threaded processing efficiency

## Cross-Compilation

Support for embedded targets:

```bash
# Install cross-compilation toolchains
python setup_cross_compile.py --install-toolchains

# Setup for Raspberry Pi 4
python setup_cross_compile.py --target raspberry-pi-4

# Setup for generic ARM64
python setup_cross_compile.py --target linux-arm64

# List all available targets
python setup_cross_compile.py --list-targets
```

### Supported Targets

- `linux-arm64`: Generic ARM64 Linux systems
- `linux-arm32`: Generic ARM32 Linux systems  
- `linux-x86_64`: Generic x86_64 Linux systems
- `raspberry-pi-4`: Raspberry Pi 4 optimized build

## Development

### Project Structure

```
production-audio-system/
├── src/
│   ├── audio_core/          # Hardware interfaces
│   ├── processing/          # Audio processing components
│   ├── visualization/       # Web interface and monitoring
│   ├── config/             # Configuration management
│   └── tools/              # Benchmarking and utilities
├── tests/                  # Test suite
├── docs/                   # Documentation
├── requirements-*.txt      # Platform-specific dependencies
├── pyproject.toml         # Project configuration
└── setup_cross_compile.py # Cross-compilation setup
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test category
pytest -m "not hardware"  # Skip hardware-dependent tests
pytest -m "embedded"       # Run embedded system tests
```

### Code Quality

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Type checking
mypy src/

# Linting
flake8 src/ tests/
```

## Logging

The system provides comprehensive logging:

- **System Log**: General system events and status
- **Audio Log**: Audio processing events and metrics
- **Performance Log**: Performance metrics and benchmarks
- **Error Log**: Error messages and exceptions
- **Debug Log**: Detailed debugging information

Logs are stored in the `logs/` directory with automatic rotation.

## Monitoring

### Web Interface

Access the web-based monitoring interface:

```bash
# Start with web interface
audio-system start --port 8080

# Open browser to http://localhost:8080
```

### Real-time Metrics

Monitor system performance in real-time:

- Audio input/output levels
- Processing latency
- CPU and memory usage
- Device status and health
- Processing chain visualization

## Troubleshooting

### Common Issues

1. **Audio Device Not Found**
   ```bash
   # List available audio devices
   python -c "import pyaudio; pa = pyaudio.PyAudio(); [print(f'{i}: {pa.get_device_info_by_index(i)}') for i in range(pa.get_device_count())]"
   ```

2. **Permission Denied (Linux)**
   ```bash
   # Add user to audio group
   sudo usermod -a -G audio $USER
   # Logout and login again
   ```

3. **High Latency**
   ```bash
   # Enable real-time scheduling
   audio-system start --embedded
   
   # Check system limits
   ulimit -r  # Should be > 0 for real-time priority
   ```

4. **Memory Issues**
   ```bash
   # Enable low memory mode
   export AUDIO_MEMORY_MODE=low
   audio-system start
   ```

### Debug Mode

Enable debug logging for troubleshooting:

```bash
# Enable debug logging
audio-system start --log-level DEBUG

# Check debug logs
tail -f logs/debug.log
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

### Development Setup

```bash
# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests before committing
pytest
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:

- Create an issue on GitHub
- Check the documentation in `docs/`
- Run `audio-system --help` for CLI help