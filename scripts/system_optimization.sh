#!/bin/bash
# 音频处理系统优化脚本
# Audio Processing System Optimization Script

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否为root用户
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "此脚本需要root权限运行"
        exit 1
    fi
}

# 备份配置文件
backup_config() {
    local config_file=$1
    local backup_dir="/etc/audio-processing/backups"
    
    mkdir -p "$backup_dir"
    
    if [[ -f "$config_file" ]]; then
        cp "$config_file" "$backup_dir/$(basename $config_file).backup.$(date +%Y%m%d_%H%M%S)"
        log_info "已备份配置文件: $config_file"
    fi
}

# 系统内核参数优化
optimize_kernel_parameters() {
    log_info "优化系统内核参数..."
    
    backup_config "/etc/sysctl.conf"
    
    # 音频实时处理优化
    cat >> /etc/sysctl.conf << EOF

# 音频处理系统优化参数
# Audio Processing System Optimization Parameters

# 实时调度优化
kernel.sched_rt_runtime_us = -1
kernel.sched_latency_ns = 1000000
kernel.sched_min_granularity_ns = 100000
kernel.sched_wakeup_granularity_ns = 50000

# 内存管理优化
vm.swappiness = 10
vm.dirty_ratio = 5
vm.dirty_background_ratio = 2
vm.vfs_cache_pressure = 50

# 网络优化
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.core.rmem_default = 262144
net.core.wmem_default = 262144
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.core.netdev_max_backlog = 5000

# 文件系统优化
fs.file-max = 65536
EOF

    # 应用内核参数
    sysctl -p
    log_success "内核参数优化完成"
}

# 音频系统权限配置
configure_audio_permissions() {
    log_info "配置音频系统权限..."
    
    backup_config "/etc/security/limits.conf"
    
    # 创建音频组
    groupadd -f audio
    
    # 配置实时权限
    cat >> /etc/security/limits.conf << EOF

# 音频处理系统权限配置
# Audio Processing System Permissions
@audio - rtprio 95
@audio - memlock unlimited
@audio - nice -19
@audio - nofile 65536
EOF

    log_success "音频系统权限配置完成"
}

# CPU频率和调度优化
optimize_cpu_performance() {
    log_info "优化CPU性能设置..."
    
    # 设置CPU调度器为性能模式
    if [[ -d "/sys/devices/system/cpu/cpu0/cpufreq" ]]; then
        for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
            echo "performance" > "$cpu" 2>/dev/null || true
        done
        log_success "CPU调度器设置为性能模式"
    else
        log_warning "未找到CPU频率控制接口"
    fi
    
    # 禁用CPU节能功能
    if [[ -f "/sys/devices/system/cpu/intel_pstate/no_turbo" ]]; then
        echo 0 > /sys/devices/system/cpu/intel_pstate/no_turbo
        log_success "启用Intel Turbo Boost"
    fi
    
    # 设置CPU亲和性
    if command -v taskset >/dev/null 2>&1; then
        # 为音频处理预留CPU核心
        echo "isolated_cores=0,1" >> /etc/default/grub
        log_info "已配置CPU核心隔离，重启后生效"
    fi
}

# 音频服务优化
optimize_audio_services() {
    log_info "优化音频服务配置..."
    
    # PulseAudio优化配置
    if command -v pulseaudio >/dev/null 2>&1; then
        mkdir -p /etc/pulse
        cat > /etc/pulse/daemon.conf << EOF
# PulseAudio优化配置
high-priority = yes
nice-level = -11
realtime-scheduling = yes
realtime-priority = 5
resample-method = speex-float-10
default-sample-format = float32le
default-sample-rate = 48000
alternate-sample-rate = 44100
default-sample-channels = 2
default-fragments = 2
default-fragment-size-msec = 5
EOF
        log_success "PulseAudio配置优化完成"
    fi
    
    # JACK优化配置
    if command -v jackd >/dev/null 2>&1; then
        mkdir -p /etc/jack
        cat > /etc/jack/jack.conf << EOF
# JACK优化配置
realtime=true
priority=70
frames=256
rate=48000
periods=2
EOF
        log_success "JACK配置优化完成"
    fi
}

# 网络优化
optimize_network() {
    log_info "优化网络配置..."
    
    # 网络接口优化
    for interface in $(ls /sys/class/net/ | grep -E '^(eth|ens|enp)'); do
        if [[ -d "/sys/class/net/$interface" ]]; then
            # 增加接收缓冲区
            ethtool -G "$interface" rx 4096 tx 4096 2>/dev/null || true
            
            # 启用网络卸载功能
            ethtool -K "$interface" gso on gro on tso on 2>/dev/null || true
            
            log_info "已优化网络接口: $interface"
        fi
    done
    
    # 防火墙优化
    if command -v ufw >/dev/null 2>&1; then
        # 允许音频处理相关端口
        ufw allow 8000:8010/tcp comment "Audio Processing API"
        ufw allow 9000:9010/udp comment "Audio Streaming"
        log_success "防火墙规则配置完成"
    fi
}

# 存储优化
optimize_storage() {
    log_info "优化存储配置..."
    
    # SSD优化
    for disk in $(lsblk -d -o NAME | grep -E '^(sd|nvme)'); do
        # 启用TRIM
        if [[ -f "/sys/block/$disk/queue/discard_granularity" ]]; then
            echo mq-deadline > "/sys/block/$disk/queue/scheduler" 2>/dev/null || true
            log_info "已优化磁盘调度器: $disk"
        fi
    done
    
    # 临时文件系统优化
    if ! grep -q "tmpfs /tmp" /etc/fstab; then
        echo "tmpfs /tmp tmpfs defaults,noatime,mode=1777,size=2G 0 0" >> /etc/fstab
        log_info "已配置tmpfs，重启后生效"
    fi
}

# 服务优化
optimize_services() {
    log_info "优化系统服务..."
    
    # 禁用不必要的服务
    local services_to_disable=(
        "bluetooth"
        "cups"
        "avahi-daemon"
        "ModemManager"
        "whoopsie"
        "apport"
    )
    
    for service in "${services_to_disable[@]}"; do
        if systemctl is-enabled "$service" >/dev/null 2>&1; then
            systemctl disable "$service"
            systemctl stop "$service" 2>/dev/null || true
            log_info "已禁用服务: $service"
        fi
    done
    
    # 创建音频处理系统服务
    cat > /etc/systemd/system/audio-processing.service << EOF
[Unit]
Description=Audio Processing System
After=network.target sound.target

[Service]
Type=simple
User=audio
Group=audio
WorkingDirectory=/opt/audio-processing
ExecStart=/opt/audio-processing/bin/audio-processing-server
Restart=always
RestartSec=5
Nice=-10
IOSchedulingClass=1
IOSchedulingPriority=4

# 资源限制
LimitNOFILE=65536
LimitMEMLOCK=infinity
LimitRTPRIO=95

# 安全设置
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/audio-processing/data /var/log/audio-processing

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    log_success "音频处理系统服务配置完成"
}

# 监控配置
setup_monitoring() {
    log_info "配置系统监控..."
    
    # 创建监控脚本
    mkdir -p /opt/audio-processing/monitoring
    
    cat > /opt/audio-processing/monitoring/system_monitor.sh << 'EOF'
#!/bin/bash
# 系统监控脚本

LOG_FILE="/var/log/audio-processing/system_monitor.log"
ALERT_THRESHOLD_CPU=80
ALERT_THRESHOLD_MEMORY=85
ALERT_THRESHOLD_DISK=90

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    
    # CPU使用率
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    
    # 内存使用率
    MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    
    # 磁盘使用率
    DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | cut -d'%' -f1)
    
    # 记录日志
    echo "[$TIMESTAMP] CPU: ${CPU_USAGE}% Memory: ${MEMORY_USAGE}% Disk: ${DISK_USAGE}%" >> "$LOG_FILE"
    
    # 检查告警阈值
    if (( $(echo "$CPU_USAGE > $ALERT_THRESHOLD_CPU" | bc -l) )); then
        echo "[$TIMESTAMP] ALERT: High CPU usage: ${CPU_USAGE}%" >> "$LOG_FILE"
    fi
    
    if (( $(echo "$MEMORY_USAGE > $ALERT_THRESHOLD_MEMORY" | bc -l) )); then
        echo "[$TIMESTAMP] ALERT: High memory usage: ${MEMORY_USAGE}%" >> "$LOG_FILE"
    fi
    
    if [[ $DISK_USAGE -gt $ALERT_THRESHOLD_DISK ]]; then
        echo "[$TIMESTAMP] ALERT: High disk usage: ${DISK_USAGE}%" >> "$LOG_FILE"
    fi
    
    sleep 60
done
EOF

    chmod +x /opt/audio-processing/monitoring/system_monitor.sh
    
    # 创建监控服务
    cat > /etc/systemd/system/audio-monitoring.service << EOF
[Unit]
Description=Audio Processing System Monitor
After=audio-processing.service

[Service]
Type=simple
ExecStart=/opt/audio-processing/monitoring/system_monitor.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable audio-monitoring.service
    log_success "系统监控配置完成"
}

# 创建优化验证脚本
create_validation_script() {
    log_info "创建优化验证脚本..."
    
    cat > /opt/audio-processing/bin/validate_optimization.sh << 'EOF'
#!/bin/bash
# 优化验证脚本

echo "🔍 验证系统优化状态..."

# 检查内核参数
echo "📋 内核参数检查:"
echo "  实时调度: $(sysctl kernel.sched_rt_runtime_us | cut -d= -f2)"
echo "  交换倾向: $(sysctl vm.swappiness | cut -d= -f2)"
echo "  网络缓冲: $(sysctl net.core.rmem_max | cut -d= -f2)"

# 检查CPU调度器
echo "📋 CPU调度器检查:"
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    if [[ -f "$cpu" ]]; then
        echo "  $(basename $(dirname $cpu)): $(cat $cpu)"
        break
    fi
done

# 检查音频权限
echo "📋 音频权限检查:"
if getent group audio >/dev/null; then
    echo "  音频组: 存在"
else
    echo "  音频组: 不存在"
fi

# 检查服务状态
echo "📋 服务状态检查:"
for service in audio-processing audio-monitoring; do
    if systemctl is-enabled $service >/dev/null 2>&1; then
        echo "  $service: $(systemctl is-active $service)"
    else
        echo "  $service: 未配置"
    fi
done

# 性能测试
echo "📋 性能测试:"
echo "  CPU核心数: $(nproc)"
echo "  内存总量: $(free -h | grep Mem | awk '{print $2}')"
echo "  负载平均: $(uptime | awk -F'load average:' '{print $2}')"

echo "✅ 验证完成"
EOF

    chmod +x /opt/audio-processing/bin/validate_optimization.sh
    log_success "优化验证脚本创建完成"
}

# 主函数
main() {
    echo "🚀 音频处理系统优化脚本"
    echo "================================"
    
    check_root
    
    # 创建必要目录
    mkdir -p /opt/audio-processing/{bin,data,monitoring}
    mkdir -p /var/log/audio-processing
    
    # 执行优化步骤
    optimize_kernel_parameters
    configure_audio_permissions
    optimize_cpu_performance
    optimize_audio_services
    optimize_network
    optimize_storage
    optimize_services
    setup_monitoring
    create_validation_script
    
    echo ""
    log_success "系统优化完成！"
    echo ""
    echo "📝 后续步骤:"
    echo "1. 重启系统以应用所有优化"
    echo "2. 运行验证脚本: /opt/audio-processing/bin/validate_optimization.sh"
    echo "3. 启动音频处理服务: systemctl start audio-processing"
    echo "4. 启动监控服务: systemctl start audio-monitoring"
    echo ""
    echo "📊 监控日志位置: /var/log/audio-processing/"
    echo "🔧 配置备份位置: /etc/audio-processing/backups/"
}

# 脚本入口
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi