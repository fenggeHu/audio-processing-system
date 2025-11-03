#!/bin/bash
# 音频处理系统兼容性检查工具
# Audio Processing System Compatibility Checker

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

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

log_header() {
    echo -e "${BOLD}${BLUE}$1${NC}"
}

# 检查操作系统
check_os() {
    log_header "检查操作系统..."
    
    if [[ ! -f /etc/os-release ]]; then
        log_error "无法检测操作系统版本"
        return 1
    fi
    
    . /etc/os-release
    log_info "操作系统: $NAME"
    log_info "版本: $VERSION_ID"
    log_info "架构: $(uname -m)"
    
    case "$ID" in
        ubuntu)
            if [[ $(echo "$VERSION_ID >= 20.04" | bc -l 2>/dev/null || echo 0) -eq 1 ]]; then
                log_success "Ubuntu版本支持"
            else
                log_warning "建议使用Ubuntu 20.04或更高版本"
            fi
            ;;
        debian)
            if [[ $(echo "$VERSION_ID >= 11" | bc -l 2>/dev/null || echo 0) -eq 1 ]]; then
                log_success "Debian版本支持"
            else
                log_warning "建议使用Debian 11或更高版本"
            fi
            ;;
        centos|rhel)
            if [[ $(echo "$VERSION_ID >= 8" | bc -l 2>/dev/null || echo 0) -eq 1 ]]; then
                log_success "CentOS/RHEL版本支持"
            else
                log_warning "建议使用CentOS/RHEL 8或更高版本"
            fi
            ;;
        fedora)
            log_success "Fedora系统支持"
            ;;
        *)
            log_warning "未测试的操作系统: $ID"
            ;;
    esac
    
    return 0
}

# 检查硬件要求
check_hardware() {
    log_header "检查硬件要求..."
    
    local errors=0
    
    # CPU核心数
    local cpu_cores=$(nproc)
    log_info "CPU核心数: $cpu_cores"
    if [[ $cpu_cores -ge 4 ]]; then
        log_success "CPU核心数满足要求"
    else
        log_warning "建议至少4个CPU核心，当前: $cpu_cores"
    fi
    
    # 内存
    local memory_gb=$(free -g | awk '/^Mem:/{print $2}')
    log_info "内存: ${memory_gb}GB"
    if [[ $memory_gb -ge 4 ]]; then
        log_success "内存满足要求"
    else
        log_error "需要至少4GB内存，当前: ${memory_gb}GB"
        ((errors++))
    fi
    
    # 磁盘空间
    local disk_space=$(df -BG / | awk 'NR==2 {print $4}' | sed 's/G//')
    log_info "可用磁盘空间: ${disk_space}GB"
    if [[ $disk_space -ge 10 ]]; then
        log_success "磁盘空间满足要求"
    else
        log_error "需要至少10GB磁盘空间，当前: ${disk_space}GB"
        ((errors++))
    fi
    
    return $errors
}

# 检查软件依赖
check_software() {
    log_header "检查软件依赖..."
    
    local errors=0
    
    # Python版本
    if command -v python3 &> /dev/null; then
        local python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        log_info "Python版本: $python_version"
        if [[ $(echo "$python_version >= 3.10" | bc -l 2>/dev/null || echo 0) -eq 1 ]]; then
            log_success "Python版本满足要求"
        else
            log_error "需要Python 3.10或更高版本，当前: $python_version"
            ((errors++))
        fi
    else
        log_error "未找到Python3"
        ((errors++))
    fi
    
    # pip
    if python3 -m pip --version &> /dev/null; then
        log_success "pip可用"
    else
        log_error "未找到pip"
        ((errors++))
    fi
    
    # 编译工具
    if command -v gcc &> /dev/null; then
        log_success "GCC编译器可用"
    else
        log_warning "未找到GCC编译器，可能需要安装build-essential"
    fi
    
    # 系统包管理器
    if command -v apt-get &> /dev/null; then
        log_success "APT包管理器可用"
    elif command -v yum &> /dev/null; then
        log_success "YUM包管理器可用"
    elif command -v dnf &> /dev/null; then
        log_success "DNF包管理器可用"
    else
        log_warning "未找到支持的包管理器"
    fi
    
    return $errors
}

# 检查音频系统
check_audio() {
    log_header "检查音频系统..."
    
    local warnings=0
    
    # ALSA
    if [[ -d /proc/asound ]]; then
        log_success "ALSA音频系统可用"
        
        # 音频设备
        local audio_devices=$(ls /proc/asound/ | grep -E '^card[0-9]+$' | wc -l)
        log_info "检测到 $audio_devices 个音频设备"
        
        if [[ $audio_devices -gt 0 ]]; then
            log_success "找到音频设备"
        else
            log_warning "未检测到音频设备"
            ((warnings++))
        fi
    else
        log_warning "ALSA音频系统不可用"
        ((warnings++))
    fi
    
    # PulseAudio
    if command -v pulseaudio &> /dev/null; then
        log_info "PulseAudio可用"
    else
        log_info "PulseAudio不可用（可选）"
    fi
    
    return $warnings
}

# 检查网络
check_network() {
    log_header "检查网络连接..."
    
    # 本地网络
    if ip route | grep -q default; then
        log_success "默认路由配置正确"
    else
        log_warning "未找到默认路由"
    fi
    
    # 外网连接
    if ping -c 1 -W 5 8.8.8.8 &> /dev/null; then
        log_success "外网连接正常"
    else
        log_info "外网连接不可用（离线安装可忽略）"
    fi
    
    # DNS解析
    if nslookup google.com &> /dev/null; then
        log_success "DNS解析正常"
    else
        log_info "DNS解析不可用（离线安装可忽略）"
    fi
    
    return 0
}

# 检查权限
check_permissions() {
    log_header "检查权限..."
    
    if [[ $EUID -eq 0 ]]; then
        log_success "具有root权限"
    else
        log_warning "当前用户不是root，安装时需要sudo权限"
    fi
    
    # 检查sudo
    if command -v sudo &> /dev/null; then
        log_success "sudo命令可用"
    else
        log_warning "sudo命令不可用"
    fi
    
    return 0
}

# 生成报告
generate_report() {
    local total_errors=$1
    local total_warnings=$2
    
    echo
    log_header "=========================================="
    log_header "           兼容性检查报告"
    log_header "=========================================="
    echo
    
    if [[ $total_errors -eq 0 ]]; then
        log_success "✓ 系统满足安装要求"
        echo
        log_info "建议操作:"
        log_info "1. 运行安装器进行安装"
        log_info "2. 如有警告，建议先解决相关问题"
        echo
    else
        log_error "✗ 系统不满足安装要求"
        echo
        log_error "发现 $total_errors 个错误，$total_warnings 个警告"
        echo
        log_info "必须解决的问题:"
        log_info "1. 确保有足够的内存和磁盘空间"
        log_info "2. 安装Python 3.10或更高版本"
        log_info "3. 确保有root或sudo权限"
        echo
    fi
    
    log_info "详细信息请查看上述检查结果"
}

# 主函数
main() {
    log_header "=========================================="
    log_header "    音频处理系统兼容性检查工具"
    log_header "=========================================="
    echo
    
    local total_errors=0
    local total_warnings=0
    
    # 运行各项检查
    check_os
    
    check_hardware
    total_errors=$((total_errors + $?))
    
    check_software  
    total_errors=$((total_errors + $?))
    
    check_audio
    total_warnings=$((total_warnings + $?))
    
    check_network
    
    check_permissions
    
    # 生成报告
    generate_report $total_errors $total_warnings
    
    # 返回适当的退出码
    if [[ $total_errors -eq 0 ]]; then
        exit 0
    else
        exit 1
    fi
}

# 运行主程序
main "$@"
