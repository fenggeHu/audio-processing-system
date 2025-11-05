# Production Audio System - Deployment Guide

This directory contains deployment configurations and scripts for different platforms and environments.

## Directory Structure

```
deploy/
├── linux/          # Linux production deployment
│   ├── install.sh           # Automated installation script
│   ├── optimize_system.sh   # System optimization for real-time audio
│   ├── production-audio-system.service  # Systemd service
│   ├── asound.conf          # ALSA configuration
│   ├── production-audio-system.logrotate  # Log rotation
│   └── README.md            # Linux deployment guide
├── macos/          # macOS development environment
│   ├── setup_dev.sh         # Development environment setup
│   └── README.md            # macOS setup guide
├── windows/        # Windows development environment
│   ├── setup_dev.bat        # Development environment setup
│   └── README.md            # Windows setup guide
└── README.md       # This file
```

## Platform Support

### Linux (Production)
- **Target**: Ubuntu 20.04+, CentOS 8+, RHEL 8+
- **Purpose**: Production deployment with real-time audio processing
- **Features**: 
  - Systemd service integration
  - ALSA optimization
  - Real-time kernel configuration
  - Security hardening
  - Performance monitoring

### macOS (Development)
- **Target**: macOS 11+ (Big Sur and later)
- **Purpose**: Development and testing environment
- **Features**:
  - CoreAudio integration
  - Homebrew dependency management
  - Xcode development tools
  - VS Code/PyCharm integration

### Windows (Development)
- **Target**: Windows 10/11
- **Purpose**: Development and testing environment
- **Features**:
  - WASAPI/DirectSound support
  - Visual Studio integration
  - PowerShell scripts
  - Windows-specific optimizations

## Quick Start

### Linux Production Deployment
```bash
cd deploy/linux
sudo ./install.sh
sudo ./optimize_system.sh
sudo reboot
sudo systemctl start production-audio-system
```

### macOS Development Setup
```bash
cd deploy/macos
./setup_dev.sh
```

### Windows Development Setup
```cmd
cd deploy\windows
setup_dev.bat
```

## Cross-Platform Development

Use the cross-platform build script for unified development workflow:

```bash
# Setup environment for current platform
python scripts/cross_platform_build.py setup

# Run tests
python scripts/cross_platform_build.py test

# Start development server
python scripts/cross_platform_build.py dev

# Build package
python scripts/cross_platform_build.py build
```

## Configuration Management

Each platform has its own configuration template:
- `config/production_linux.yaml` - Linux production settings
- `config/development_macos.yaml` - macOS development settings  
- `config/development_windows.yaml` - Windows development settings

## Development Tools

Use the development tools script for IDE integration and utilities:

```bash
# Generate VS Code configuration
python scripts/dev_tools.py vscode

# Generate PyCharm configuration
python scripts/dev_tools.py pycharm

# Validate configuration
python scripts/dev_tools.py validate --config development_linux.yaml

# Check dependencies
python scripts/dev_tools.py deps
```

## Environment-Specific Features

### Linux Production Features
- **Real-time Audio**: Optimized kernel parameters and scheduling
- **System Integration**: Systemd service with proper permissions
- **Security**: Hardened service configuration with minimal privileges
- **Monitoring**: Comprehensive logging and performance metrics
- **Deployment**: Automated installation and configuration scripts

### macOS Development Features
- **Native Integration**: CoreAudio framework integration
- **Development Tools**: Homebrew package management
- **IDE Support**: Xcode, VS Code, and PyCharm configurations
- **Testing**: Comprehensive test suite with audio device mocking

### Windows Development Features
- **Audio APIs**: WASAPI, DirectSound, and MME support
- **Development Environment**: Visual Studio integration
- **Package Management**: pip and conda compatibility
- **Testing**: Windows-specific audio device testing

## Deployment Strategies

### Production Deployment (Linux)
1. **Automated Installation**: Use `install.sh` for complete setup
2. **System Optimization**: Apply real-time optimizations with `optimize_system.sh`
3. **Service Management**: Systemd integration with automatic startup
4. **Monitoring**: Built-in performance monitoring and alerting
5. **Updates**: Rolling updates with service restart

### Development Deployment (macOS/Windows)
1. **Environment Setup**: Platform-specific setup scripts
2. **IDE Integration**: Automatic configuration for popular IDEs
3. **Testing**: Comprehensive test suite with mocking
4. **Hot Reload**: Development server with automatic reloading
5. **Debugging**: Integrated debugging and profiling tools

## Security Considerations

### Linux Production Security
- Service runs with minimal privileges
- Restricted file system access
- Network access controls
- Security-hardened systemd configuration
- Regular security updates

### Development Security
- Local-only web interface binding
- Development-only features disabled in production
- Secure configuration templates
- Dependency vulnerability scanning

## Performance Optimization

### Linux Production Performance
- Real-time kernel scheduling
- CPU isolation and affinity
- Memory locking and huge pages
- IRQ optimization
- Audio device exclusive access

### Development Performance
- Relaxed latency requirements
- Debug-friendly buffer sizes
- Comprehensive profiling tools
- Performance regression testing

## Monitoring and Logging

### Production Monitoring
- System resource monitoring
- Audio quality metrics
- Performance benchmarking
- Error tracking and alerting
- Log aggregation and rotation

### Development Monitoring
- Real-time debugging information
- Performance profiling
- Test coverage reporting
- Code quality metrics
- Development server logs

## Troubleshooting

### Common Issues
1. **Audio Device Access**: Permission and driver issues
2. **Real-time Performance**: Kernel and system configuration
3. **Dependencies**: Platform-specific package installation
4. **Configuration**: YAML syntax and validation errors
5. **Network**: Firewall and port configuration

### Platform-Specific Issues
- **Linux**: ALSA configuration, real-time permissions
- **macOS**: CoreAudio permissions, Homebrew issues
- **Windows**: Audio driver compatibility, Visual Studio tools

## Support and Documentation

- **Linux Deployment**: See `deploy/linux/README.md`
- **macOS Development**: See `deploy/macos/README.md`  
- **Windows Development**: See `deploy/windows/README.md`
- **API Documentation**: Generated from source code
- **Configuration Reference**: YAML schema documentation

## Contributing

When adding new deployment features:
1. Update platform-specific scripts
2. Add configuration templates
3. Update documentation
4. Test on target platforms
5. Update CI/CD pipelines