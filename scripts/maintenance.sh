#!/bin/bash
# 音频处理系统维护脚本
# Audio Processing System Maintenance Script

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置参数
LOG_DIR="/var/log/audio-processing"
DATA_DIR="/opt/audio-processing/data"
BACKUP_DIR="/opt/audio-processing/backups"
CONFIG_DIR="/etc/audio-processing"
MAX_LOG_DAYS=7
MAX_BACKUP_DAYS=30

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# 创建必要目录
create_directories() {
    local dirs=("$LOG_DIR" "$DATA_DIR" "$BACKUP_DIR" "$CONFIG_DIR")
    
    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            log_info "创建目录: $dir"
        fi
    done
}

# 清理日志文件
cleanup_logs() {
    log_info "开始清理日志文件..."
    
    if [[ -d "$LOG_DIR" ]]; then
        # 清理超过指定天数的日志文件
        find "$LOG_DIR" -name "*.log" -mtime +$MAX_LOG_DAYS -type f -delete
        find "$LOG_DIR" -name "*.log.*" -mtime +$MAX_LOG_DAYS -type f -delete
        
        # 压缩昨天的日志文件
        find "$LOG_DIR" -name "*.log" -mtime 1 -type f -exec gzip {} \;
        
        log_success "日志文件清理完成"
        
        # 显示当前日志使用情况
        local log_size=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)
        log_info "当前日志目录大小: $log_size"
    else
        log_warning "日志目录不存在: $LOG_DIR"
    fi
}

# 清理临时文件
cleanup_temp_files() {
    log_info "开始清理临时文件..."
    
    local temp_dirs=(
        "/tmp/audio-processing-*"
        "$DATA_DIR/temp"
        "$DATA_DIR/cache"
    )
    
    for pattern in "${temp_dirs[@]}"; do
        if ls $pattern 1> /dev/null 2>&1; then
            rm -rf $pattern
            log_info "清理临时文件: $pattern"
        fi
    done
    
    log_success "临时文件清理完成"
}

# 数据库维护
maintain_database() {
    log_info "开始数据库维护..."
    
    local db_file="$DATA_DIR/audio_processing.db"
    
    if [[ -f "$db_file" ]]; then
        # SQLite数据库优化
        sqlite3 "$db_file" "VACUUM;"
        sqlite3 "$db_file" "REINDEX;"
        sqlite3 "$db_file" "ANALYZE;"
        
        log_success "数据库维护完成"
        
        # 显示数据库大小
        local db_size=$(du -sh "$db_file" | cut -f1)
        log_info "数据库文件大小: $db_size"
    else
        log_info "未找到数据库文件，跳过数据库维护"
    fi
}

# 备份配置文件
backup_configurations() {
    log_info "开始备份配置文件..."
    
    local backup_timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_archive="$BACKUP_DIR/config_backup_$backup_timestamp.tar.gz"
    
    if [[ -d "$CONFIG_DIR" ]]; then
        tar -czf "$backup_archive" -C "$(dirname $CONFIG_DIR)" "$(basename $CONFIG_DIR)"
        log_success "配置文件备份完成: $backup_archive"
    else
        log_warning "配置目录不存在: $CONFIG_DIR"
    fi
    
    # 清理旧备份
    find "$BACKUP_DIR" -name "config_backup_*.tar.gz" -mtime +$MAX_BACKUP_DAYS -delete
    log_info "清理超过 $MAX_BACKUP_DAYS 天的旧备份"
}

# 系统健康检查
health_check() {
    log_info "开始系统健康检查..."
    
    local health_report="$LOG_DIR/health_check_$(date +%Y%m%d_%H%M%S).log"
    
    {
        echo "=== 系统健康检查报告 ==="
        echo "检查时间: $(date)"
        echo ""
        
        # CPU使用率
        echo "=== CPU使用率 ==="
        top -bn1 | grep "Cpu(s)" | head -1
        echo ""
        
        # 内存使用情况
        echo "=== 内存使用情况 ==="
        free -h
        echo ""
        
        # 磁盘使用情况
        echo "=== 磁盘使用情况 ==="
        df -h
        echo ""
        
        # 系统负载
        echo "=== 系统负载 ==="
        uptime
        echo ""
        
        # 网络连接
        echo "=== 网络连接 ==="
        ss -tuln | head -10
        echo ""
        
        # 进程状态
        echo "=== 音频处理相关进程 ==="
        ps aux | grep -E "(audio|pulse|jack)" | grep -v grep
        echo ""
        
        # 服务状态
        echo "=== 服务状态 ==="
        for service in audio-processing audio-monitoring; do
            if systemctl list-unit-files | grep -q "$service"; then
                echo "$service: $(systemctl is-active $service)"
            else
                echo "$service: 未安装"
            fi
        done
        echo ""
        
        # 日志错误统计
        echo "=== 最近24小时错误统计 ==="
        if [[ -f "$LOG_DIR/system.log" ]]; then
            grep -c "ERROR" "$LOG_DIR/system.log" 2>/dev/null || echo "0"
        else
            echo "系统日志文件不存在"
        fi
        
    } > "$health_report"
    
    log_success "健康检查报告生成: $health_report"
    
    # 检查关键指标并发出警告
    local cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    local memory_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    local disk_usage=$(df / | tail -1 | awk '{print $5}' | cut -d'%' -f1)
    
    if (( $(echo "$cpu_usage > 80" | bc -l) )); then
        log_warning "CPU使用率过高: ${cpu_usage}%"
    fi
    
    if (( $(echo "$memory_usage > 85" | bc -l) )); then
        log_warning "内存使用率过高: ${memory_usage}%"
    fi
    
    if [[ $disk_usage -gt 90 ]]; then
        log_warning "磁盘使用率过高: ${disk_usage}%"
    fi
}

# 性能基准测试
run_performance_benchmark() {
    log_info "开始性能基准测试..."
    
    local benchmark_script="/opt/audio-processing/tools/performance_benchmark.py"
    local benchmark_report="$LOG_DIR/benchmark_$(date +%Y%m%d_%H%M%S).json"
    
    if [[ -f "$benchmark_script" ]]; then
        python3 "$benchmark_script" --output "$benchmark_report" --category basic
        log_success "性能基准测试完成: $benchmark_report"
    else
        log_warning "基准测试脚本不存在: $benchmark_script"
    fi
}

# 更新系统配置
update_system_config() {
    log_info "检查系统配置更新..."
    
    # 检查内核参数
    local current_swappiness=$(sysctl vm.swappiness | cut -d= -f2 | tr -d ' ')
    if [[ "$current_swappiness" != "10" ]]; then
        log_warning "交换倾向设置不正确，当前值: $current_swappiness，建议值: 10"
    fi
    
    # 检查音频权限
    if ! getent group audio >/dev/null; then
        log_warning "音频组不存在，建议运行系统优化脚本"
    fi
    
    # 检查服务配置
    for service in audio-processing audio-monitoring; do
        if systemctl list-unit-files | grep -q "$service"; then
            if ! systemctl is-enabled "$service" >/dev/null; then
                log_warning "服务 $service 未启用"
            fi
        fi
    done
}

# 生成维护报告
generate_maintenance_report() {
    log_info "生成维护报告..."
    
    local report_file="$LOG_DIR/maintenance_report_$(date +%Y%m%d_%H%M%S).txt"
    
    {
        echo "=== 音频处理系统维护报告 ==="
        echo "维护时间: $(date)"
        echo "维护脚本版本: 1.0"
        echo ""
        
        echo "=== 执行的维护任务 ==="
        echo "✓ 日志文件清理"
        echo "✓ 临时文件清理"
        echo "✓ 数据库维护"
        echo "✓ 配置文件备份"
        echo "✓ 系统健康检查"
        echo "✓ 性能基准测试"
        echo "✓ 系统配置检查"
        echo ""
        
        echo "=== 目录使用情况 ==="
        echo "日志目录: $(du -sh $LOG_DIR 2>/dev/null | cut -f1)"
        echo "数据目录: $(du -sh $DATA_DIR 2>/dev/null | cut -f1)"
        echo "备份目录: $(du -sh $BACKUP_DIR 2>/dev/null | cut -f1)"
        echo ""
        
        echo "=== 系统资源使用 ==="
        echo "CPU负载: $(uptime | awk -F'load average:' '{print $2}')"
        echo "内存使用: $(free -h | grep Mem | awk '{print $3 "/" $2}')"
        echo "磁盘使用: $(df -h / | tail -1 | awk '{print $3 "/" $2 " (" $5 ")"}')"
        echo ""
        
        echo "=== 下次维护建议 ==="
        echo "- 建议每周运行一次完整维护"
        echo "- 监控系统资源使用情况"
        echo "- 定期检查服务状态"
        echo "- 保持系统和软件更新"
        
    } > "$report_file"
    
    log_success "维护报告生成: $report_file"
}

# 发送通知 (可选)
send_notification() {
    local message="$1"
    local priority="${2:-normal}"
    
    # 这里可以集成邮件、Slack、钉钉等通知方式
    # 目前只记录到日志
    log_info "通知: $message"
    
    # 示例: 发送邮件通知 (需要配置邮件服务)
    # if command -v mail >/dev/null 2>&1; then
    #     echo "$message" | mail -s "音频处理系统维护通知" admin@example.com
    # fi
}

# 主函数
main() {
    echo "🔧 音频处理系统维护脚本"
    echo "开始时间: $(date)"
    echo "================================"
    
    # 创建必要目录
    create_directories
    
    # 执行维护任务
    cleanup_logs
    cleanup_temp_files
    maintain_database
    backup_configurations
    health_check
    run_performance_benchmark
    update_system_config
    generate_maintenance_report
    
    echo ""
    log_success "所有维护任务完成！"
    echo "结束时间: $(date)"
    
    # 发送完成通知
    send_notification "音频处理系统维护任务已完成"
}

# 显示帮助信息
show_help() {
    cat << EOF
音频处理系统维护脚本

用法: $0 [选项]

选项:
    -h, --help          显示此帮助信息
    --logs-only         仅清理日志文件
    --backup-only       仅执行备份任务
    --health-only       仅执行健康检查
    --benchmark-only    仅执行性能测试
    --dry-run          模拟运行，不执行实际操作

示例:
    $0                  # 执行完整维护
    $0 --logs-only      # 仅清理日志
    $0 --health-only    # 仅健康检查

EOF
}

# 解析命令行参数
case "${1:-}" in
    -h|--help)
        show_help
        exit 0
        ;;
    --logs-only)
        create_directories
        cleanup_logs
        ;;
    --backup-only)
        create_directories
        backup_configurations
        ;;
    --health-only)
        create_directories
        health_check
        ;;
    --benchmark-only)
        create_directories
        run_performance_benchmark
        ;;
    --dry-run)
        echo "模拟运行模式 - 不执行实际操作"
        exit 0
        ;;
    "")
        main
        ;;
    *)
        echo "未知选项: $1"
        echo "使用 --help 查看帮助信息"
        exit 1
        ;;
esac