#!/bin/bash
# Production Audio System - Linux Installation Script
# Supports Ubuntu 20.04+ and CentOS 8+

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/production-audio-system"
SERVICE_USER="audio-user"
SERVICE_GROUP="audio"
PYTHON_VERSION="3.10"

echo -e "${GREEN}Production Audio System - Linux Installation${NC}"
echo "=============================================="

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
    VER=$VERSION_ID
else
    echo -e "${RED}Cannot detect OS version${NC}"
    exit 1
fi

echo "Detected OS: $OS $VER"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

# Install system dependencies
install_ubuntu_deps() {
    echo -e "${YELLOW}Installing Ubuntu dependencies...${NC}"
    apt-get update
    apt-get install -y \
        portaudio19-dev \
        libasound2-dev \
        python3-dev \
        python3-pip \
        python3-venv \
        build-essential \
        pkg-config \
        libjack-jackd2-dev \
        jackd2 \
        alsa-utils \
        pulseaudio-utils \
        git \
        curl \
        systemd
}

install_centos_deps() {
    echo -e "${YELLOW}Installing CentOS dependencies...${NC}"
    yum update -y
    yum groupinstall -y "Development Tools"
    yum install -y \
        portaudio-devel \
        alsa-lib-devel \
        python3-devel \
        python3-pip \
        jack-audio-connection-kit-devel \
        jack-audio-connection-kit \
        alsa-utils \
        pulseaudio-utils \
        git \
        curl \
        systemd
}

# Install dependencies based on OS
case "$OS" in
    "Ubuntu")
        install_ubuntu_deps
        ;;
    "CentOS Linux"|"Red Hat Enterprise Linux")
        install_centos_deps
        ;;
    *)
        echo -e "${RED}Unsupported OS: $OS${NC}"
        exit 1
        ;;
esac

# Create service user and group
echo -e "${YELLOW}Creating service user and group...${NC}"
if ! getent group $SERVICE_GROUP > /dev/null 2>&1; then
    groupadd $SERVICE_GROUP
fi

if ! getent passwd $SERVICE_USER > /dev/null 2>&1; then
    useradd -r -g $SERVICE_GROUP -d $INSTALL_DIR -s /bin/bash $SERVICE_USER
fi

# Add user to audio group
usermod -a -G audio $SERVICE_USER

# Create installation directory
echo -e "${YELLOW}Creating installation directory...${NC}"
mkdir -p $INSTALL_DIR
mkdir -p $INSTALL_DIR/logs
mkdir -p $INSTALL_DIR/config
mkdir -p $INSTALL_DIR/data

# Copy application files
echo -e "${YELLOW}Installing application files...${NC}"
cp -r src/ $INSTALL_DIR/
cp -r config/ $INSTALL_DIR/
cp requirements-linux.txt $INSTALL_DIR/
cp pyproject.toml $INSTALL_DIR/

# Set ownership
chown -R $SERVICE_USER:$SERVICE_GROUP $INSTALL_DIR

# Create Python virtual environment
echo -e "${YELLOW}Creating Python virtual environment...${NC}"
sudo -u $SERVICE_USER python3 -m venv $INSTALL_DIR/venv
sudo -u $SERVICE_USER $INSTALL_DIR/venv/bin/pip install --upgrade pip
sudo -u $SERVICE_USER $INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/requirements-linux.txt

# Configure ALSA
echo -e "${YELLOW}Configuring ALSA...${NC}"
cp deploy/linux/asound.conf /etc/asound.conf

# Configure real-time permissions
echo -e "${YELLOW}Configuring real-time permissions...${NC}"
echo "@audio - rtprio 95" >> /etc/security/limits.conf
echo "@audio - memlock unlimited" >> /etc/security/limits.conf
echo "@audio - nice -10" >> /etc/security/limits.conf

# Install systemd service
echo -e "${YELLOW}Installing systemd service...${NC}"
cp deploy/linux/production-audio-system.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable production-audio-system.service

# Configure firewall (if ufw is available)
if command -v ufw &> /dev/null; then
    echo -e "${YELLOW}Configuring firewall...${NC}"
    ufw allow 8080/tcp  # Web interface
    ufw allow 8081/tcp  # WebSocket
fi

# Create log rotation
echo -e "${YELLOW}Configuring log rotation...${NC}"
cp deploy/linux/production-audio-system.logrotate /etc/logrotate.d/production-audio-system

echo -e "${GREEN}Installation completed successfully!${NC}"
echo ""
echo "Next steps:"
echo "1. Configure audio devices in $INSTALL_DIR/config/audio_config.yaml"
echo "2. Start the service: systemctl start production-audio-system"
echo "3. Check status: systemctl status production-audio-system"
echo "4. View logs: journalctl -u production-audio-system -f"
echo "5. Access web interface: http://localhost:8080"