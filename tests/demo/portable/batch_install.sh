#!/bin/bash
# 音频处理系统批量安装脚本
# Audio Processing System Batch Installer

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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
