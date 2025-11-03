#!/usr/bin/env python3
"""
便携式安装器构建工具
Portable Installer Builder

创建自解压的便携式安装包，支持一键安装和批量部署
"""

import sys
import base64
import gzip
from pathlib import Path
from typing import List
import argparse
import logging
import hashlib

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PortableInstallerBuilder:
    """便携式安装器构建器"""
    
    def __init__(self, output_dir: str = "dist/portable"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 模板目录
        self.templates_dir = Path(__file__).parent / "templates"
        self.templates_dir.mkdir(exist_ok=True)
        
    def create_self_extracting_installer(self, source_package: str, 
                                       installer_name: str = None) -> str:
        """创建自解压安装器"""
        logger.info(f"创建自解压安装器: {source_package}")
        
        if not Path(source_package).exists():
            raise FileNotFoundError(f"源包不存在: {source_package}")
        
        # 生成安装器名称
        if installer_name is None:
            base_name = Path(source_package).stem.replace('.tar', '')
            installer_name = f"{base_name}-installer.run"
        
        installer_path = self.output_dir / installer_name
        
        # 读取并压缩源包
        with open(source_package, 'rb') as f:
            package_data = f.read()
        
        compressed_data = gzip.compress(package_data)
        encoded_data = base64.b64encode(compressed_data).decode('ascii')
        
        # 计算校验和
        package_checksum = hashlib.sha256(package_data).hexdigest()
        
        # 生成安装器脚本
        installer_script = self._generate_installer_script(
            encoded_data, 
            package_checksum,
            Path(source_package).name
        )
        
        # 写入安装器文件
        with open(installer_path, 'w') as f:
            f.write(installer_script)
        
        # 设置执行权限
        installer_path.chmod(0o755)
        
        logger.info(f"自解压安装器创建完成: {installer_path}")
        logger.info(f"安装器大小: {installer_path.stat().st_size / 1024 / 1024:.1f} MB")
        
        return str(installer_path)
    
    def _generate_installer_script(self, encoded_data: str, 
                                 checksum: str, package_name: str) -> str:
        """生成安装器脚本"""
        
        script_template = '''#!/bin/bash
# 音频处理系统便携式安装器
# Audio Processing System Portable Installer
# 
# 这是一个自解压安装器，包含完整的离线安装包
# This is a self-extracting installer with complete offline package

set -e

# 安装器信息
INSTALLER_VERSION="1.0.0"
PACKAGE_NAME="{package_name}"
PACKAGE_CHECKSUM="{checksum}"
INSTALL_DIR="/opt/audio-processing-system"
TEMP_DIR=""

# 颜色定义
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
BOLD='\\033[1m'
NC='\\033[0m'

# 日志函数
log_info() {{
    echo -e "${{BLUE}}[INFO]${{NC}} $1"
}}

log_success() {{
    echo -e "${{GREEN}}[SUCCESS]${{NC}} $1"
}}

log_warning() {{
    echo -e "${{YELLOW}}[WARNING]${{NC}} $1"
}}

log_error() {{
    echo -e "${{RED}}[ERROR]${{NC}} $1"
}}

log_header() {{
    echo -e "${{BOLD}}${{BLUE}}$1${{NC}}"
}}

# 显示帮助信息
show_help() {{
    cat << EOF
音频处理系统便携式安装器 v$INSTALLER_VERSION

用法: $0 [选项]

选项:
  -h, --help              显示此帮助信息
  -s, --silent            静默安装模式
  -d, --install-dir DIR   指定安装目录 (默认: $INSTALL_DIR)
  -c, --check-only        仅检查系统兼容性，不安装
  -u, --uninstall         卸载已安装的系统
  -v, --verbose           详细输出
  --no-start              安装后不启动服务
  --force                 强制安装，跳过兼容性检查

示例:
  $0                      交互式安装
  $0 --silent             静默安装
  $0 --check-only         检查系统兼容性
  $0 --install-dir /usr/local/audio  自定义安装目录

EOF
}}

# 检查系统兼容性
check_system_compatibility() {{
    log_info "检查系统兼容性..."
    
    local errors=0
    
    # 检查操作系统
    if [[ ! -f /etc/os-release ]]; then
        log_error "无法检测操作系统版本"
        ((errors++))
    else
        . /etc/os-release
        log_info "操作系统: $NAME $VERSION_ID"
        
        case "$ID" in
            ubuntu|debian|centos|rhel|fedora)
                log_success "支持的操作系统: $ID"
                ;;
            *)
                log_warning "未测试的操作系统: $ID，可能存在兼容性问题"
                ;;
        esac
    fi
    
    # 检查架构
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64|aarch64|armv7l)
            log_success "支持的架构: $ARCH"
            ;;
        *)
            log_error "不支持的架构: $ARCH"
            ((errors++))
            ;;
    esac
    
    # 检查Python版本
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        if [[ $(echo "$PYTHON_VERSION >= 3.10" | bc -l 2>/dev/null || echo 0) -eq 1 ]]; then
            log_success "Python版本: $PYTHON_VERSION"
        else
            log_error "需要Python 3.10或更高版本，当前: $PYTHON_VERSION"
            ((errors++))
        fi
    else
        log_error "未找到Python3"
        ((errors++))
    fi
    
    # 检查内存
    MEMORY_GB=$(free -g | awk '/^Mem:/{{print $2}}')
    if [[ $MEMORY_GB -ge 4 ]]; then
        log_success "内存: ${{MEMORY_GB}}GB"
    else
        log_warning "建议至少4GB内存，当前: ${{MEMORY_GB}}GB"
    fi
    
    # 检查磁盘空间
    DISK_SPACE=$(df -BG "${{INSTALL_DIR%/*}}" 2>/dev/null | awk 'NR==2 {{print $4}}' | sed 's/G//' || echo "0")
    if [[ $DISK_SPACE -ge 2 ]]; then
        log_success "磁盘空间: ${{DISK_SPACE}}GB"
    else
        log_error "需要至少2GB磁盘空间，当前可用: ${{DISK_SPACE}}GB"
        ((errors++))
    fi
    
    # 检查权限
    if [[ $EUID -ne 0 ]]; then
        log_error "需要root权限运行安装器"
        ((errors++))
    fi
    
    # 检查网络（可选）
    if ping -c 1 8.8.8.8 &> /dev/null; then
        log_info "网络连接: 可用（可选）"
    else
        log_info "网络连接: 不可用（离线安装）"
    fi
    
    if [[ $errors -gt 0 ]]; then
        log_error "系统兼容性检查失败，发现 $errors 个问题"
        return 1
    else
        log_success "系统兼容性检查通过"
        return 0
    fi
}}

# 解压安装包
extract_package() {{
    log_info "解压安装包..."
    
    # 创建临时目录
    TEMP_DIR=$(mktemp -d -t audio-installer-XXXXXX)
    
    # 解压嵌入的数据
    local package_file="$TEMP_DIR/$PACKAGE_NAME"
    
    # 提取并解压数据（从脚本末尾）
    local data_start=$(awk '/^__PACKAGE_DATA__$/ {{print NR + 1; exit 0; }}' "$0")
    tail -n +$data_start "$0" | base64 -d | gunzip > "$package_file"
    
    # 验证校验和
    local actual_checksum=$(sha256sum "$package_file" | cut -d' ' -f1)
    if [[ "$actual_checksum" != "$PACKAGE_CHECKSUM" ]]; then
        log_error "包校验和验证失败"
        log_error "期望: $PACKAGE_CHECKSUM"
        log_error "实际: $actual_checksum"
        return 1
    fi
    
    log_success "包校验和验证通过"
    
    # 解压tar包
    cd "$TEMP_DIR"
    tar -xzf "$package_file"
    
    # 查找解压后的目录
    EXTRACTED_DIR=$(find . -maxdepth 1 -type d ! -name "." | head -1)
    if [[ -z "$EXTRACTED_DIR" ]]; then
        log_error "未找到解压后的目录"
        return 1
    fi
    
    log_success "安装包解压完成: $TEMP_DIR/$EXTRACTED_DIR"
    echo "$TEMP_DIR/$EXTRACTED_DIR"
}}

# 运行安装
run_installation() {{
    local extracted_dir="$1"
    
    log_info "开始安装音频处理系统..."
    
    cd "$extracted_dir"
    
    # 查找安装脚本
    local install_script=""
    if [[ -f "install_offline.sh" ]]; then
        install_script="install_offline.sh"
    elif [[ -f "install_multi_arch.sh" ]]; then
        install_script="install_multi_arch.sh"
    elif [[ -f "scripts/install_offline.sh" ]]; then
        install_script="scripts/install_offline.sh"
    else
        log_error "未找到安装脚本"
        return 1
    fi
    
    log_info "使用安装脚本: $install_script"
    
    # 设置安装目录环境变量
    export INSTALL_DIR="$INSTALL_DIR"
    
    # 运行安装脚本
    if [[ "$SILENT_MODE" == "true" ]]; then
        # 静默模式
        bash "$install_script" --silent 2>&1 | tee "$TEMP_DIR/install.log"
    else
        # 交互模式
        bash "$install_script"
    fi
    
    local install_result=$?
    
    if [[ $install_result -eq 0 ]]; then
        log_success "安装完成"
        return 0
    else
        log_error "安装失败，退出码: $install_result"
        if [[ -f "$TEMP_DIR/install.log" ]]; then
            log_info "安装日志保存在: $TEMP_DIR/install.log"
        fi
        return 1
    fi
}}

# 启动服务
start_services() {{
    if [[ "$NO_START" == "true" ]]; then
        log_info "跳过服务启动（--no-start）"
        return 0
    fi
    
    log_info "启动音频处理系统服务..."
    
    # 启动服务
    systemctl enable audio-processing 2>/dev/null || true
    systemctl start audio-processing
    
    # 检查服务状态
    sleep 3
    if systemctl is-active --quiet audio-processing; then
        log_success "音频处理系统服务启动成功"
        
        # 检查Web界面
        if curl -s http://localhost/health &> /dev/null; then
            log_success "Web界面可访问: http://localhost"
        else
            log_warning "Web界面暂时不可访问，请稍后重试"
        fi
    else
        log_warning "服务启动可能有问题，请检查日志: journalctl -u audio-processing"
    fi
}}

# 卸载系统
uninstall_system() {{
    log_info "卸载音频处理系统..."
    
    # 停止服务
    systemctl stop audio-processing 2>/dev/null || true
    systemctl disable audio-processing 2>/dev/null || true
    
    # 删除服务文件
    rm -f /etc/systemd/system/audio-processing*.service
    systemctl daemon-reload
    
    # 删除安装目录
    if [[ -d "$INSTALL_DIR" ]]; then
        rm -rf "$INSTALL_DIR"
        log_success "删除安装目录: $INSTALL_DIR"
    fi
    
    # 删除数据目录
    rm -rf /var/lib/audio-processing
    rm -rf /var/run/audio-processing
    
    log_success "卸载完成"
}}

# 清理临时文件
cleanup() {{
    if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
    fi
}}

# 错误处理
trap cleanup EXIT

# 解析命令行参数
SILENT_MODE="false"
CHECK_ONLY="false"
UNINSTALL="false"
VERBOSE="false"
NO_START="false"
FORCE="false"

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -s|--silent)
            SILENT_MODE="true"
            shift
            ;;
        -d|--install-dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        -c|--check-only)
            CHECK_ONLY="true"
            shift
            ;;
        -u|--uninstall)
            UNINSTALL="true"
            shift
            ;;
        -v|--verbose)
            VERBOSE="true"
            shift
            ;;
        --no-start)
            NO_START="true"
            shift
            ;;
        --force)
            FORCE="true"
            shift
            ;;
        *)
            log_error "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
done

# 主安装流程
main() {{
    # 显示标题
    log_header "=========================================="
    log_header "  音频处理系统便携式安装器 v$INSTALLER_VERSION"
    log_header "=========================================="
    echo
    
    # 处理卸载
    if [[ "$UNINSTALL" == "true" ]]; then
        uninstall_system
        exit 0
    fi
    
    # 系统兼容性检查
    if ! check_system_compatibility; then
        if [[ "$FORCE" != "true" ]]; then
            log_error "系统兼容性检查失败，使用 --force 强制安装"
            exit 1
        else
            log_warning "强制安装模式，跳过兼容性检查"
        fi
    fi
    
    # 仅检查模式
    if [[ "$CHECK_ONLY" == "true" ]]; then
        log_success "系统兼容性检查完成"
        exit 0
    fi
    
    # 确认安装
    if [[ "$SILENT_MODE" != "true" ]]; then
        echo
        log_info "安装目录: $INSTALL_DIR"
        read -p "是否继续安装？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "安装已取消"
            exit 0
        fi
    fi
    
    # 解压安装包
    local extracted_dir
    extracted_dir=$(extract_package)
    if [[ $? -ne 0 ]]; then
        log_error "解压安装包失败"
        exit 1
    fi
    
    # 运行安装
    if run_installation "$extracted_dir"; then
        echo
        log_success "音频处理系统安装成功！"
        echo
        log_info "安装目录: $INSTALL_DIR"
        log_info "Web界面: http://localhost"
        log_info "API文档: http://localhost/docs"
        echo
        log_info "管理命令:"
        log_info "  启动服务: systemctl start audio-processing"
        log_info "  停止服务: systemctl stop audio-processing"
        log_info "  查看状态: systemctl status audio-processing"
        log_info "  查看日志: journalctl -u audio-processing -f"
        echo
        
        # 启动服务
        start_services
        
    else
        log_error "安装失败"
        exit 1
    fi
}}

# 运行主程序
main "$@"

# 数据分隔符（不要删除此行）
exit 0
__PACKAGE_DATA__
{encoded_data}'''
        
        return script_template.format(
            package_name=package_name,
            checksum=checksum,
            encoded_data=encoded_data
        )
    
    def create_batch_installer(self, installers: List[str], 
                             batch_name: str = "batch_install.sh") -> str:
        """创建批量安装脚本"""
        logger.info("创建批量安装脚本...")
        
        batch_script = '''#!/bin/bash
# 音频处理系统批量安装脚本
# Audio Processing System Batch Installer

set -e

# 颜色定义
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
NC='\\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 显示帮助
show_help() {
    cat << EOF
音频处理系统批量安装脚本

用法: $0 [选项] [主机列表文件]

选项:
  -h, --help              显示此帮助信息
  -u, --user USER         SSH用户名 (默认: root)
  -k, --key KEY_FILE      SSH私钥文件
  -p, --parallel NUM      并行安装数量 (默认: 5)
  -i, --installer FILE    安装器文件路径
  --check-only            仅检查主机连通性
  --dry-run               试运行，不执行实际安装

主机列表文件格式:
  每行一个主机地址，支持以下格式:
  - IP地址: 192.168.1.100
  - 主机名: classroom-pc-01
  - 带端口: 192.168.1.100:2222

示例:
  $0 hosts.txt                    # 使用默认设置批量安装
  $0 -u admin -k ~/.ssh/id_rsa hosts.txt  # 指定用户和密钥
  $0 --parallel 10 hosts.txt      # 并行安装10台设备

EOF
}

# 检查主机连通性
check_host_connectivity() {
    local host="$1"
    local user="$2"
    local key_file="$3"
    
    local ssh_opts="-o ConnectTimeout=10 -o StrictHostKeyChecking=no"
    if [[ -n "$key_file" ]]; then
        ssh_opts="$ssh_opts -i $key_file"
    fi
    
    if ssh $ssh_opts "$user@$host" "echo 'connected'" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# 在远程主机上安装
install_on_host() {
    local host="$1"
    local user="$2"
    local key_file="$3"
    local installer="$4"
    
    log_info "开始安装到主机: $host"
    
    local ssh_opts="-o ConnectTimeout=30 -o StrictHostKeyChecking=no"
    if [[ -n "$key_file" ]]; then
        ssh_opts="$ssh_opts -i $key_file"
    fi
    
    # 复制安装器到远程主机
    if [[ -n "$key_file" ]]; then
        scp -i "$key_file" -o StrictHostKeyChecking=no "$installer" "$user@$host:/tmp/"
    else
        scp -o StrictHostKeyChecking=no "$installer" "$user@$host:/tmp/"
    fi
    
    local installer_name=$(basename "$installer")
    
    # 在远程主机上运行安装器
    ssh $ssh_opts "$user@$host" "
        cd /tmp
        chmod +x '$installer_name'
        ./'$installer_name' --silent
    "
    
    if [[ $? -eq 0 ]]; then
        log_success "主机 $host 安装成功"
        return 0
    else
        log_error "主机 $host 安装失败"
        return 1
    fi
}

# 批量安装
batch_install() {
    local hosts_file="$1"
    local user="$2"
    local key_file="$3"
    local installer="$4"
    local parallel="$5"
    local check_only="$6"
    local dry_run="$7"
    
    if [[ ! -f "$hosts_file" ]]; then
        log_error "主机列表文件不存在: $hosts_file"
        return 1
    fi
    
    if [[ ! -f "$installer" ]]; then
        log_error "安装器文件不存在: $installer"
        return 1
    fi
    
    # 读取主机列表
    local hosts=()
    while IFS= read -r line; do
        # 跳过空行和注释
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        hosts+=("$line")
    done < "$hosts_file"
    
    log_info "找到 ${#hosts[@]} 台主机"
    
    # 检查连通性
    log_info "检查主机连通性..."
    local reachable_hosts=()
    local unreachable_hosts=()
    
    for host in "${hosts[@]}"; do
        if check_host_connectivity "$host" "$user" "$key_file"; then
            reachable_hosts+=("$host")
            log_success "主机 $host 可达"
        else
            unreachable_hosts+=("$host")
            log_error "主机 $host 不可达"
        fi
    done
    
    log_info "可达主机: ${#reachable_hosts[@]}"
    log_info "不可达主机: ${#unreachable_hosts[@]}"
    
    if [[ "$check_only" == "true" ]]; then
        return 0
    fi
    
    if [[ ${#reachable_hosts[@]} -eq 0 ]]; then
        log_error "没有可达的主机"
        return 1
    fi
    
    if [[ "$dry_run" == "true" ]]; then
        log_info "试运行模式，将在以下主机上安装:"
        for host in "${reachable_hosts[@]}"; do
            echo "  - $host"
        done
        return 0
    fi
    
    # 批量安装
    log_info "开始批量安装..."
    
    local success_count=0
    local failed_count=0
    local pids=()
    
    for host in "${reachable_hosts[@]}"; do
        # 控制并行数量
        while [[ ${#pids[@]} -ge $parallel ]]; do
            for i in "${!pids[@]}"; do
                if ! kill -0 "${pids[i]}" 2>/dev/null; then
                    wait "${pids[i]}"
                    local exit_code=$?
                    if [[ $exit_code -eq 0 ]]; then
                        ((success_count++))
                    else
                        ((failed_count++))
                    fi
                    unset pids[i]
                fi
            done
            pids=("${pids[@]}")  # 重新索引数组
            sleep 1
        done
        
        # 启动新的安装进程
        install_on_host "$host" "$user" "$key_file" "$installer" &
        pids+=($!)
    done
    
    # 等待所有进程完成
    for pid in "${pids[@]}"; do
        wait "$pid"
        local exit_code=$?
        if [[ $exit_code -eq 0 ]]; then
            ((success_count++))
        else
            ((failed_count++))
        fi
    done
    
    # 显示结果
    echo
    log_info "批量安装完成"
    log_success "成功: $success_count 台"
    if [[ $failed_count -gt 0 ]]; then
        log_error "失败: $failed_count 台"
    fi
    
    return $failed_count
}

# 默认参数
USER="root"
KEY_FILE=""
PARALLEL=5
INSTALLER=""
CHECK_ONLY="false"
DRY_RUN="false"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -u|--user)
            USER="$2"
            shift 2
            ;;
        -k|--key)
            KEY_FILE="$2"
            shift 2
            ;;
        -p|--parallel)
            PARALLEL="$2"
            shift 2
            ;;
        -i|--installer)
            INSTALLER="$2"
            shift 2
            ;;
        --check-only)
            CHECK_ONLY="true"
            shift
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        -*)
            log_error "未知选项: $1"
            show_help
            exit 1
            ;;
        *)
            HOSTS_FILE="$1"
            shift
            ;;
    esac
done

# 检查参数
if [[ -z "$HOSTS_FILE" ]]; then
    log_error "请指定主机列表文件"
    show_help
    exit 1
fi

# 查找安装器文件
if [[ -z "$INSTALLER" ]]; then
    # 自动查找安装器
    for file in *.run; do
        if [[ -f "$file" ]]; then
            INSTALLER="$file"
            break
        fi
    done
    
    if [[ -z "$INSTALLER" ]]; then
        log_error "未找到安装器文件，请使用 -i 选项指定"
        exit 1
    fi
fi

log_info "使用安装器: $INSTALLER"

# 运行批量安装
batch_install "$HOSTS_FILE" "$USER" "$KEY_FILE" "$INSTALLER" "$PARALLEL" "$CHECK_ONLY" "$DRY_RUN"
'''
        
        batch_path = self.output_dir / batch_name
        with open(batch_path, 'w') as f:
            f.write(batch_script)
        
        batch_path.chmod(0o755)
        
        logger.info(f"批量安装脚本创建完成: {batch_path}")
        return str(batch_path)
    
    def create_system_checker(self) -> str:
        """创建系统兼容性检查工具"""
        logger.info("创建系统兼容性检查工具...")
        
        checker_script = '''#!/bin/bash
# 音频处理系统兼容性检查工具
# Audio Processing System Compatibility Checker

set -e

# 颜色定义
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
BOLD='\\033[1m'
NC='\\033[0m'

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
'''
        
        checker_path = self.output_dir / "system_checker.sh"
        with open(checker_path, 'w') as f:
            f.write(checker_script)
        
        checker_path.chmod(0o755)
        
        logger.info(f"系统兼容性检查工具创建完成: {checker_path}")
        return str(checker_path)

def main():
    parser = argparse.ArgumentParser(description="便携式安装器构建工具")
    parser.add_argument("source_package", help="源离线包路径")
    parser.add_argument("--output", "-o", default="dist/portable", 
                       help="输出目录")
    parser.add_argument("--name", "-n", help="安装器名称")
    parser.add_argument("--batch", "-b", action="store_true",
                       help="同时创建批量安装脚本")
    parser.add_argument("--checker", "-c", action="store_true",
                       help="创建系统兼容性检查工具")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    builder = PortableInstallerBuilder(args.output)
    
    try:
        # 创建自解压安装器
        installer_path = builder.create_self_extracting_installer(
            args.source_package, 
            args.name
        )
        
        print(f"\n✓ 便携式安装器创建成功: {installer_path}")
        
        # 创建批量安装脚本
        if args.batch:
            batch_path = builder.create_batch_installer([installer_path])
            print(f"✓ 批量安装脚本创建成功: {batch_path}")
        
        # 创建系统检查工具
        if args.checker:
            checker_path = builder.create_system_checker()
            print(f"✓ 系统兼容性检查工具创建成功: {checker_path}")
        
        print(f"\n使用方法:")
        print(f"1. 传输安装器到目标设备: {Path(installer_path).name}")
        print(f"2. 运行安装器: sudo ./{Path(installer_path).name}")
        print(f"3. 或静默安装: sudo ./{Path(installer_path).name} --silent")
        
        if args.batch:
            print(f"\n批量部署:")
            print(f"1. 创建主机列表文件 hosts.txt")
            print(f"2. 运行批量安装: ./{Path(batch_path).name} hosts.txt")
        
    except Exception as e:
        logger.error(f"构建失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()