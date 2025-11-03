#!/bin/bash

# 音频处理系统自动化部署流程脚本
# Audio Processing System Automated Deployment Workflow

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 配置变量
DEPLOY_ENV=${DEPLOY_ENV:-production}
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
DEPLOY_DIR="$PROJECT_ROOT/deploy"
LOG_FILE="/tmp/audio-system-deploy-$(date +%Y%m%d-%H%M%S).log"

# 日志函数
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

# 错误处理
handle_error() {
    log_error "部署过程中发生错误，请查看日志: $LOG_FILE"
    exit 1
}

trap handle_error ERR

# 检查部署环境
check_environment() {
    log "检查部署环境: $DEPLOY_ENV"
    
    case $DEPLOY_ENV in
        production|staging|development)
            log_success "部署环境有效: $DEPLOY_ENV"
            ;;
        *)
            log_error "无效的部署环境: $DEPLOY_ENV"
            log "支持的环境: production, staging, development"
            exit 1
            ;;
    esac
    
    # 检查配置文件
    CONFIG_FILE="$DEPLOY_DIR/config/${DEPLOY_ENV}.json"
    if [[ ! -f "$CONFIG_FILE" ]]; then
        log_error "配置文件不存在: $CONFIG_FILE"
        exit 1
    fi
    
    log_success "配置文件检查通过: $CONFIG_FILE"
}

# 备份现有部署
backup_existing() {
    INSTALL_DIR="/opt/audio-processing-system"
    
    if [[ -d "$INSTALL_DIR" ]]; then
        log "备份现有部署..."
        BACKUP_DIR="/opt/audio-processing-system-backup-$(date +%Y%m%d-%H%M%S)"
        sudo cp -r "$INSTALL_DIR" "$BACKUP_DIR"
        log_success "备份完成: $BACKUP_DIR"
        
        # 停止现有服务
        log "停止现有服务..."
        sudo systemctl stop audio-processing-web || true
        sudo systemctl stop audio-processing || true
        log_success "服务已停止"
    else
        log "未发现现有部署，跳过备份"
    fi
}

# 选择部署方式
select_deployment_method() {
    log "选择部署方式..."
    
    if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
        log "检测到Docker环境，使用容器化部署"
        DEPLOYMENT_METHOD="docker"
    else
        log "使用传统部署方式"
        DEPLOYMENT_METHOD="traditional"
    fi
    
    log_success "部署方式: $DEPLOYMENT_METHOD"
}

# Docker部署
deploy_with_docker() {
    log "开始Docker容器化部署..."
    
    cd "$PROJECT_ROOT"
    
    # 构建镜像
    log "构建Docker镜像..."
    docker-compose -f deploy/docker-compose.yml build
    
    # 启动服务
    log "启动Docker服务..."
    docker-compose -f deploy/docker-compose.yml up -d
    
    # 等待服务启动
    log "等待服务启动..."
    sleep 30
    
    # 健康检查
    if docker-compose -f deploy/docker-compose.yml ps | grep -q "Up"; then
        log_success "Docker服务启动成功"
    else
        log_error "Docker服务启动失败"
        docker-compose -f deploy/docker-compose.yml logs
        exit 1
    fi
}

# 传统部署
deploy_traditional() {
    log "开始传统部署..."
    
    cd "$PROJECT_ROOT"
    
    # 运行安装脚本
    if [[ -f "deploy/install.sh" ]]; then
        log "运行安装脚本..."
        chmod +x deploy/install.sh
        sudo -E deploy/install.sh
    else
        log_error "安装脚本不存在: deploy/install.sh"
        exit 1
    fi
    
    # 使用Python部署脚本
    if [[ -f "deploy/deploy.py" ]]; then
        log "运行Python部署脚本..."
        sudo python3 deploy/deploy.py --config "$CONFIG_FILE"
    else
        log_warning "Python部署脚本不存在，跳过"
    fi
}

# 部署后验证
post_deployment_verification() {
    log "执行部署后验证..."
    
    # 等待服务完全启动
    sleep 10
    
    # 检查HTTP服务
    log "检查Web服务..."
    if curl -f http://localhost/health &> /dev/null; then
        log_success "Web服务健康检查通过"
    else
        log_error "Web服务健康检查失败"
        return 1
    fi
    
    # 检查API文档
    log "检查API文档..."
    if curl -f http://localhost/docs &> /dev/null; then
        log_success "API文档访问正常"
    else
        log_warning "API文档访问异常"
    fi
    
    # 检查系统服务状态
    if [[ "$DEPLOYMENT_METHOD" == "traditional" ]]; then
        log "检查系统服务状态..."
        
        services=("audio-processing" "audio-processing-web" "nginx")
        for service in "${services[@]}"; do
            if systemctl is-active --quiet "$service"; then
                log_success "服务 $service 运行正常"
            else
                log_error "服务 $service 运行异常"
                systemctl status "$service" --no-pager
                return 1
            fi
        done
    fi
    
    # 检查Docker服务状态
    if [[ "$DEPLOYMENT_METHOD" == "docker" ]]; then
        log "检查Docker服务状态..."
        
        if docker-compose -f deploy/docker-compose.yml ps | grep -q "Up"; then
            log_success "Docker服务运行正常"
        else
            log_error "Docker服务运行异常"
            docker-compose -f deploy/docker-compose.yml ps
            return 1
        fi
    fi
    
    log_success "部署后验证完成"
}

# 配置监控和告警
setup_monitoring() {
    log "配置监控和告警..."
    
    if [[ "$DEPLOYMENT_METHOD" == "docker" ]]; then
        # Docker环境已包含Prometheus和Grafana
        log "Docker环境监控已配置"
        
        # 等待监控服务启动
        sleep 20
        
        # 检查Prometheus
        if curl -f http://localhost:9090 &> /dev/null; then
            log_success "Prometheus监控服务正常"
        else
            log_warning "Prometheus监控服务异常"
        fi
        
        # 检查Grafana
        if curl -f http://localhost:3000 &> /dev/null; then
            log_success "Grafana仪表板服务正常"
        else
            log_warning "Grafana仪表板服务异常"
        fi
    else
        log "传统部署环境，跳过监控配置"
    fi
}

# 生成部署报告
generate_deployment_report() {
    log "生成部署报告..."
    
    REPORT_FILE="/tmp/audio-system-deployment-report-$(date +%Y%m%d-%H%M%S).txt"
    
    cat > "$REPORT_FILE" << EOF
音频处理系统部署报告
===================

部署时间: $(date)
部署环境: $DEPLOY_ENV
部署方式: $DEPLOYMENT_METHOD
项目路径: $PROJECT_ROOT
日志文件: $LOG_FILE

服务访问地址:
- Web界面: http://localhost
- API文档: http://localhost/docs
- 健康检查: http://localhost/health

EOF

    if [[ "$DEPLOYMENT_METHOD" == "docker" ]]; then
        cat >> "$REPORT_FILE" << EOF
监控服务:
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin123)
- Kibana: http://localhost:5601

Docker服务状态:
$(docker-compose -f deploy/docker-compose.yml ps)

EOF
    else
        cat >> "$REPORT_FILE" << EOF
系统服务状态:
$(systemctl status audio-processing --no-pager || true)
$(systemctl status audio-processing-web --no-pager || true)
$(systemctl status nginx --no-pager || true)

EOF
    fi
    
    cat >> "$REPORT_FILE" << EOF
系统资源使用:
$(free -h)
$(df -h)

网络端口监听:
$(netstat -tlnp | grep -E ':(80|8000|9090|3000)' || true)

部署完成！
EOF
    
    log_success "部署报告已生成: $REPORT_FILE"
    
    # 显示关键信息
    echo
    echo "=========================================="
    echo "           部署完成！"
    echo "=========================================="
    echo
    echo "Web界面: http://localhost"
    echo "API文档: http://localhost/docs"
    echo
    if [[ "$DEPLOYMENT_METHOD" == "docker" ]]; then
        echo "监控面板: http://localhost:3000"
        echo "指标监控: http://localhost:9090"
        echo
    fi
    echo "部署报告: $REPORT_FILE"
    echo "部署日志: $LOG_FILE"
    echo
}

# 主部署流程
main() {
    echo "=========================================="
    echo "    音频处理系统自动化部署"
    echo "    Audio Processing System Auto Deploy"
    echo "=========================================="
    echo
    
    log "开始自动化部署流程..."
    log "项目根目录: $PROJECT_ROOT"
    log "部署日志: $LOG_FILE"
    
    check_environment
    backup_existing
    select_deployment_method
    
    case $DEPLOYMENT_METHOD in
        docker)
            deploy_with_docker
            ;;
        traditional)
            deploy_traditional
            ;;
    esac
    
    post_deployment_verification
    setup_monitoring
    generate_deployment_report
    
    log_success "自动化部署流程完成！"
}

# 脚本入口
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi