# Linux Production Deployment Guide

This directory contains all the necessary files and scripts for deploying the Production Audio System on Linux environments.

## Supported Distributions

- Ubuntu 20.04 LTS or later
- CentOS 8 or later
- Red Hat Enterprise Linux 8 or later

## Quick Installation

1. **Run the installation script as root:**
   ```bash
   sudo ./install.sh
   ```

2. **Optimize the system for real-time audio:**
   ```bash
   sudo ./optimize_system.sh
   ```

3. **Reboot the system:**
   ```bash
   sudo reboot
   ```

4. **Start the service:**
   ```bash
   sudo systemctl start production-audio-system
   ```

## Files Overview

### Installation Scripts
- `install.sh` - Main installation script that sets up the entire system
- `optimize_system.sh` - System optimization for real-time audio processing

### System Configuration
- `production-audio-system.service` - Systemd service definition
- `asound.conf` - ALSA audio system configuration
- `production-audio-system.logrotate` - Log rotation configuration

### Application Configuration
- `../config/production_linux.yaml` - Main application configuration for Linux

## Manual Installation Steps

If you prefer to install manually or need to customize the installation:

### 1. Install System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y portaudio19-dev libasound2-dev python3-dev python3-pip python3-venv build-essential pkg-config libjack-jackd2-dev jackd2 alsa-utils pulseaudio-utils git curl systemd
```

**CentOS/RHEL:**
```bash
sudo yum update -y
sudo yum groupinstall -y "Development Tools"
sudo yum install -y portaudio-devel alsa-lib-devel python3-devel python3-pip jack-audio-connection-kit-devel jack-audio-connection-kit alsa-utils pulseaudio-utils git curl systemd
```

### 2. Create Service User
```bash
sudo groupadd audio-user
sudo useradd -r -g audio-user -d /opt/production-audio-system -s /bin/bash audio-user
sudo usermod -a -G audio audio-user
```

### 3. Install Application
```bash
sudo mkdir -p /opt/production-audio-system
sudo cp -r src/ /opt/production-audio-system/
sudo cp -r config/ /opt/production-audio-system/
sudo cp requirements-linux.txt /opt/production-audio-system/
sudo chown -R audio-user:audio-user /opt/production-audio-system
```

### 4. Create Python Environment
```bash
sudo -u audio-user python3 -m venv /opt/production-audio-system/venv
sudo -u audio-user /opt/production-audio-system/venv/bin/pip install --upgrade pip
sudo -u audio-user /opt/production-audio-system/venv/bin/pip install -r /opt/production-audio-system/requirements-linux.txt
```

### 5. Configure System
```bash
# Copy ALSA configuration
sudo cp asound.conf /etc/asound.conf

# Set real-time permissions
echo "@audio - rtprio 95" | sudo tee -a /etc/security/limits.conf
echo "@audio - memlock unlimited" | sudo tee -a /etc/security/limits.conf
echo "@audio - nice -10" | sudo tee -a /etc/security/limits.conf

# Install systemd service
sudo cp production-audio-system.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable production-audio-system.service
```

## Configuration

### Audio Configuration
Edit `/opt/production-audio-system/config/production_linux.yaml` to configure:
- Audio devices and parameters
- Processing components
- Real-time settings
- Monitoring thresholds

### ALSA Configuration
The `asound.conf` file provides optimized ALSA configuration with:
- Low-latency PCM devices
- Multi-channel support
- Professional audio interface support
- Rate conversion and mixing

## Service Management

### Start/Stop Service
```bash
sudo systemctl start production-audio-system
sudo systemctl stop production-audio-system
sudo systemctl restart production-audio-system
```

### Check Status
```bash
sudo systemctl status production-audio-system
```

### View Logs
```bash
# Real-time logs
sudo journalctl -u production-audio-system -f

# Application logs
sudo tail -f /opt/production-audio-system/logs/main.log

# Performance logs
sudo tail -f /opt/production-audio-system/logs/performance.log
```

## Performance Optimization

The `optimize_system.sh` script applies the following optimizations:

### Kernel Parameters
- Real-time scheduling configuration
- Memory management optimization
- Network and file system tuning

### CPU Configuration
- Performance governor
- Disabled CPU idle states
- CPU isolation for audio processing

### IRQ Optimization
- Audio device IRQ affinity
- Disabled IRQ balancing

### System Services
- Disabled unnecessary services
- Real-time limits configuration

## Troubleshooting

### Common Issues

1. **Permission Denied Errors**
   ```bash
   # Check user is in audio group
   groups audio-user
   
   # Add user to audio group if missing
   sudo usermod -a -G audio audio-user
   ```

2. **Audio Device Not Found**
   ```bash
   # List available audio devices
   aplay -l
   arecord -l
   
   # Test ALSA configuration
   speaker-test -c 2 -t wav
   ```

3. **High Latency Issues**
   ```bash
   # Check real-time limits
   ulimit -r
   
   # Verify CPU governor
   cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
   
   # Run system optimization
   sudo ./optimize_system.sh
   ```

4. **Service Won't Start**
   ```bash
   # Check service logs
   sudo journalctl -u production-audio-system -n 50
   
   # Verify Python environment
   sudo -u audio-user /opt/production-audio-system/venv/bin/python -c "import pyaudio; print('PyAudio OK')"
   ```

### Log Files
- Main application: `/opt/production-audio-system/logs/main.log`
- Performance metrics: `/opt/production-audio-system/logs/performance.log`
- Debug information: `/opt/production-audio-system/logs/debug.log`
- System logs: `journalctl -u production-audio-system`

### Performance Monitoring
Access the web interface at `http://localhost:8080` to monitor:
- Real-time audio processing status
- System performance metrics
- Audio quality indicators
- Component status and configuration

## Security Considerations

The systemd service includes security hardening:
- Restricted file system access
- Private temporary directory
- No new privileges
- Protected kernel interfaces
- Limited resource access

For production deployment, consider:
- Firewall configuration
- Network access restrictions
- Regular security updates
- Monitoring and alerting setup