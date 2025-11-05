#!/bin/bash
# System optimization script for production audio processing
# Configures kernel parameters and system settings for low-latency audio

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Optimizing system for production audio processing...${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

# Kernel parameters for real-time audio
echo -e "${YELLOW}Configuring kernel parameters...${NC}"
cat > /etc/sysctl.d/99-audio-production.conf << EOF
# Real-time audio optimization
kernel.sched_rt_runtime_us = -1
kernel.sched_rt_period_us = 1000000

# Memory management
vm.swappiness = 10
vm.dirty_ratio = 5
vm.dirty_background_ratio = 2

# Network optimization
net.core.rmem_default = 262144
net.core.rmem_max = 16777216
net.core.wmem_default = 262144
net.core.wmem_max = 16777216

# File system optimization
fs.file-max = 2097152

# Process limits
kernel.pid_max = 4194304
EOF

# Apply kernel parameters
sysctl -p /etc/sysctl.d/99-audio-production.conf

# CPU frequency scaling
echo -e "${YELLOW}Configuring CPU frequency scaling...${NC}"
if [ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]; then
    echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
    
    # Set performance governor for all CPUs
    for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
        if [ -f "$cpu" ]; then
            echo performance > "$cpu"
        fi
    done
    
    # Make it persistent
    cat > /etc/systemd/system/cpu-performance.service << EOF
[Unit]
Description=Set CPU Performance Governor
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do [ -f "\$cpu" ] && echo performance > "\$cpu"; done'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl enable cpu-performance.service
fi

# Disable CPU idle states for better latency
echo -e "${YELLOW}Configuring CPU idle states...${NC}"
if [ -d /sys/devices/system/cpu/cpu0/cpuidle ]; then
    # Disable deep sleep states
    for state in /sys/devices/system/cpu/cpu*/cpuidle/state*/disable; do
        if [ -f "$state" ] && [[ "$state" =~ state[2-9] ]]; then
            echo 1 > "$state"
        fi
    done
fi

# IRQ affinity optimization
echo -e "${YELLOW}Optimizing IRQ affinity...${NC}"
# Find audio device IRQs and bind them to specific CPUs
if command -v irqbalance &> /dev/null; then
    systemctl stop irqbalance
    systemctl disable irqbalance
fi

# Create IRQ optimization script
cat > /usr/local/bin/optimize-audio-irq.sh << 'EOF'
#!/bin/bash
# Optimize IRQ affinity for audio devices

# Find audio-related IRQs
AUDIO_IRQS=$(grep -E "(snd|audio|usb.*audio)" /proc/interrupts | cut -d: -f1 | tr -d ' ')

# Get number of CPUs
NUM_CPUS=$(nproc)

# Bind audio IRQs to the last CPU
LAST_CPU=$((NUM_CPUS - 1))
LAST_CPU_MASK=$((1 << LAST_CPU))

for irq in $AUDIO_IRQS; do
    if [ -f "/proc/irq/$irq/smp_affinity" ]; then
        printf "%x" $LAST_CPU_MASK > /proc/irq/$irq/smp_affinity
        echo "IRQ $irq bound to CPU $LAST_CPU"
    fi
done
EOF

chmod +x /usr/local/bin/optimize-audio-irq.sh

# Create systemd service for IRQ optimization
cat > /etc/systemd/system/audio-irq-optimize.service << EOF
[Unit]
Description=Optimize Audio IRQ Affinity
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/optimize-audio-irq.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl enable audio-irq-optimize.service

# Configure GRUB for real-time kernel
echo -e "${YELLOW}Configuring GRUB for real-time performance...${NC}"
if [ -f /etc/default/grub ]; then
    # Backup original GRUB config
    cp /etc/default/grub /etc/default/grub.backup
    
    # Add real-time kernel parameters
    sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT="[^"]*/& isolcpus=3 nohz_full=3 rcu_nocbs=3 processor.max_cstate=1 intel_idle.max_cstate=0/' /etc/default/grub
    
    # Update GRUB
    if command -v update-grub &> /dev/null; then
        update-grub
    elif command -v grub2-mkconfig &> /dev/null; then
        grub2-mkconfig -o /boot/grub2/grub.cfg
    fi
fi

# Configure systemd for real-time
echo -e "${YELLOW}Configuring systemd for real-time...${NC}"
mkdir -p /etc/systemd/system.conf.d
cat > /etc/systemd/system.conf.d/audio-realtime.conf << EOF
[Manager]
DefaultLimitRTPRIO=95
DefaultLimitMEMLOCK=infinity
EOF

# Disable unnecessary services
echo -e "${YELLOW}Disabling unnecessary services...${NC}"
SERVICES_TO_DISABLE=(
    "bluetooth.service"
    "cups.service"
    "avahi-daemon.service"
    "ModemManager.service"
    "NetworkManager-wait-online.service"
)

for service in "${SERVICES_TO_DISABLE[@]}"; do
    if systemctl is-enabled "$service" &> /dev/null; then
        systemctl disable "$service"
        echo "Disabled $service"
    fi
done

# Configure audio group permissions
echo -e "${YELLOW}Configuring audio group permissions...${NC}"
cat >> /etc/security/limits.conf << EOF

# Audio production limits
@audio - rtprio 95
@audio - memlock unlimited
@audio - nice -10
@audio soft nofile 65536
@audio hard nofile 65536
EOF

# Create udev rules for audio devices
echo -e "${YELLOW}Creating udev rules for audio devices...${NC}"
cat > /etc/udev/rules.d/99-audio-production.rules << EOF
# Audio device permissions and optimization
SUBSYSTEM=="sound", GROUP="audio", MODE="0664"
KERNEL=="controlC[0-9]*", GROUP="audio", MODE="0664"

# USB audio devices
SUBSYSTEM=="usb", ATTR{bInterfaceClass}=="01", GROUP="audio", MODE="0664"

# Set scheduler for audio devices
ACTION=="add", SUBSYSTEM=="sound", KERNEL=="card*", ATTR{power/control}="on"
ACTION=="add", SUBSYSTEM=="usb", ATTR{bInterfaceClass}=="01", ATTR{power/control}="on"
EOF

udevadm control --reload-rules

echo -e "${GREEN}System optimization completed!${NC}"
echo ""
echo "Optimizations applied:"
echo "- Kernel parameters for real-time audio"
echo "- CPU frequency scaling set to performance"
echo "- CPU idle states optimized"
echo "- IRQ affinity optimization"
echo "- GRUB configured for real-time kernel"
echo "- Unnecessary services disabled"
echo "- Audio group permissions configured"
echo "- Udev rules for audio devices"
echo ""
echo -e "${YELLOW}Please reboot the system to apply all changes.${NC}"