#!/bin/bash

# 音频处理系统安装脚本
# Audio Processing System Installation Script
# 适用于 Ubuntu 20.04+ / Debian 11+ / CentOS 8+

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
    if [[ $EUID -eq 0 ]]; then
        log_error "请不要使用root用户运行此脚本"
        log_info "建议创建专用用户: sudo useradd -m -s /bin/bash audiouser"
        exit 1
    fi
}

# 检测操作系统
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$NAME
        VER=$VERSION_ID
    else
        log_error "无法检测操作系统版本"
        exit 1
    fi
    
    log_info "检测到操作系统: $OS $VER"
}

# 检查系统要求
check_requirements() {
    log_info "检查系统要求..."
    
    # 检查Python版本
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        if [[ $(echo "$PYTHON_VERSION >= 3.10" | bc -l) -eq 1 ]]; then
            log_success "Python版本: $PYTHON_VERSION ✓"
        else
            log_error "需要Python 3.10或更高版本，当前版本: $PYTHON_VERSION"
            exit 1
        fi
    else
        log_error "未找到Python3"
        exit 1
    fi
    
    # 检查内存
    MEMORY_GB=$(free -g | awk '/^Mem:/{print $2}')
    if [[ $MEMORY_GB -ge 4 ]]; then
        log_success "内存: ${MEMORY_GB}GB ✓"
    else
        log_warning "建议至少4GB内存，当前: ${MEMORY_GB}GB"
    fi
    
    # 检查磁盘空间
    DISK_SPACE=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
    if [[ $DISK_SPACE -ge 10 ]]; then
        log_success "磁盘空间: ${DISK_SPACE}GB ✓"
    else
        log_error "需要至少10GB磁盘空间，当前可用: ${DISK_SPACE}GB"
        exit 1
    fi
}

# 安装系统依赖
install_system_deps() {
    log_info "安装系统依赖..."
    
    if [[ "$OS" == *"Ubuntu"* ]] || [[ "$OS" == *"Debian"* ]]; then
        sudo apt-get update
        sudo apt-get install -y \
            python3-pip \
            python3-venv \
            python3-dev \
            portaudio19-dev \
            libasound2-dev \
            libsndfile1-dev \
            libfftw3-dev \
            ffmpeg \
            gcc \
            g++ \
            make \
            pkg-config \
            curl \
            wget \
            git \
            htop \
            supervisor \
            nginx
            
    elif [[ "$OS" == *"CentOS"* ]] || [[ "$OS" == *"Red Hat"* ]]; then
        sudo yum update -y
        sudo yum groupinstall -y "Development Tools"
        sudo yum install -y \
            python3-pip \
            python3-devel \
            portaudio-devel \
            alsa-lib-devel \
            libsndfile-devel \
            fftw-devel \
            ffmpeg \
            curl \
            wget \
            git \
            htop \
            supervisor \
            nginx
    else
        log_error "不支持的操作系统: $OS"
        exit 1
    fi
    
    log_success "系统依赖安装完成"
}

# 创建项目目录结构
create_directories() {
    log_info "创建项目目录结构..."
    
    # 主目录
    INSTALL_DIR="/opt/audio-processing-system"
    sudo mkdir -p "$INSTALL_DIR"
    sudo chown $USER:$USER "$INSTALL_DIR"
    
    # 子目录
    mkdir -p "$INSTALL_DIR"/{config,logs,recordings,plugins,backups,tmp}
    mkdir -p "$INSTALL_DIR"/config/{templates,environments}
    mkdir -p "$INSTALL_DIR"/logs/{application,system,audit}
    
    # 数据目录
    sudo mkdir -p /var/lib/audio-processing
    sudo chown $USER:$USER /var/lib/audio-processing
    
    # 运行时目录
    sudo mkdir -p /var/run/audio-processing
    sudo chown $USER:$USER /var/run/audio-processing
    
    log_success "目录结构创建完成: $INSTALL_DIR"
}

# 安装Python依赖
install_python_deps() {
    log_info "创建Python虚拟环境..."
    
    cd "$INSTALL_DIR"
    python3 -m venv venv
    source venv/bin/activate
    
    # 升级pip
    pip install --upgrade pip setuptools wheel
    
    log_info "安装Python依赖包..."
    
    # 创建requirements.txt
    cat > requirements.txt << EOF
# 核心依赖
numpy>=1.24.0
scipy>=1.10.0
pydantic>=2.0.0
structlog>=23.0.0

# 音频处理
pyaudio>=0.2.11
librosa>=0.10.0
webrtcvad>=2.0.10
soundfile>=0.12.0

# Web框架
fastapi>=0.100.0
websockets>=11.0.0
uvicorn[standard]>=0.23.0
jinja2>=3.1.0

# 系统监控
psutil>=5.9.0
prometheus-client>=0.17.0

# 数据库和缓存
redis>=4.5.0
sqlalchemy>=2.0.0
alembic>=1.11.0

# 开发和测试
pytest>=7.0.0
pytest-asyncio>=0.21.0
coverage>=7.0.0
black>=23.0.0
mypy>=1.5.0
ruff>=0.0.280
EOF
    
    pip install -r requirements.txt
    
    log_success "Python依赖安装完成"
}

# 复制应用文件
copy_application() {
    log_info "复制应用文件..."
    
    # 假设脚本在项目根目录运行
    if [[ -d "src" ]]; then
        cp -r src "$INSTALL_DIR/"
        cp -r config "$INSTALL_DIR/"
        cp -r static "$INSTALL_DIR/" 2>/dev/null || true
        cp -r docs "$INSTALL_DIR/" 2>/dev/null || true
        
        # 复制配置模板
        if [[ -f "config/audio_system.json" ]]; then
            cp config/audio_system.json "$INSTALL_DIR/config/templates/"
        fi
        
        log_success "应用文件复制完成"
    else
        log_error "未找到源代码目录，请在项目根目录运行此脚本"
        exit 1
    fi
}

# 配置系统服务
configure_services() {
    log_info "配置系统服务..."
    
    # 创建systemd服务文件
    sudo tee /etc/systemd/system/audio-processing.service > /dev/null << EOF
[Unit]
Description=Audio Processing System
After=network.target sound.target
Wants=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR/src
ExecStart=$INSTALL_DIR/venv/bin/python -m audio_processing.main
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=audio-processing

# 资源限制
LimitNOFILE=65536
LimitNPROC=4096

# 安全设置
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR /var/lib/audio-processing /var/run/audio-processing

[Install]
WantedBy=multi-user.target
EOF

    # Web控制界面服务
    sudo tee /etc/systemd/system/audio-processing-web.service > /dev/null << EOF
[Unit]
Description=Audio Processing Web Interface
After=network.target audio-processing.service
Wants=audio-processing.service

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR/src
ExecStart=$INSTALL_DIR/venv/bin/uvicorn audio_processing.services.control:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=audio-processing-web

[Install]
WantedBy=multi-user.target
EOF

    # 重新加载systemd
    sudo systemctl daemon-reload
    
    log_success "系统服务配置完成"
}

# 配置Nginx反向代理
configure_nginx() {
    log_info "配置Nginx反向代理..."
    
    sudo tee /etc/nginx/sites-available/audio-processing > /dev/null << EOF
server {
    listen 80;
    server_name localhost;
    
    # 静态文件
    location /static/ {
        alias $INSTALL_DIR/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # API和WebSocket
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # 健康检查
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        access_log off;
    }
}
EOF

    # 启用站点
    sudo ln -sf /etc/nginx/sites-available/audio-processing /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    
    # 测试配置
    sudo nginx -t
    
    log_success "Nginx配置完成"
}

# 配置日志轮转
configure_logrotate() {
    log_info "配置日志轮转..."
    
    sudo tee /etc/logrotate.d/audio-processing > /dev/null << EOF
$INSTALL_DIR/logs/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
EOF

    log_success "日志轮转配置完成"
}

# 设置防火墙
configure_firewall() {
    log_info "配置防火墙..."
    
    if command -v ufw &> /dev/null; then
        sudo ufw allow 80/tcp
        sudo ufw allow 8000/tcp
        sudo ufw --force enable
        log_success "UFW防火墙配置完成"
    else
        log_warning "未检测到防火墙，请手动配置"
    fi
}

# 创建启动脚本
create_startup_script() {
    log_info "创建启动脚本..."
    
    cat > "$INSTALL_DIR/start.sh" << EOF
#!/bin/bash
# 音频处理系统启动脚本

cd "$INSTALL_DIR"
source venv/bin/activate

# 检查音频设备
echo "检查音频设备..."
python3 -c "
import pyaudio
pa = pyaudio.PyAudio()
print(f'音频设备数量: {pa.get_device_count()}')
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info['maxInputChannels'] > 0:
        print(f'输入设备 {i}: {info[\"name\"]} ({info[\"maxInputChannels\"]} 通道)')
pa.terminate()
"

# 启动服务
echo "启动音频处理系统..."
sudo systemctl start audio-processing
sudo systemctl start audio-processing-web
sudo systemctl start nginx

# 检查状态
sleep 3
sudo systemctl status audio-processing --no-pager
sudo systemctl status audio-processing-web --no-pager

echo "系统启动完成！"
echo "Web界面: http://localhost"
echo "API文档: http://localhost/docs"
EOF

    chmod +x "$INSTALL_DIR/start.sh"
    
    # 停止脚本
    cat > "$INSTALL_DIR/stop.sh" << EOF
#!/bin/bash
# 音频处理系统停止脚本

echo "停止音频处理系统..."
sudo systemctl stop audio-processing
sudo systemctl stop audio-processing-web

echo "系统已停止"
EOF

    chmod +x "$INSTALL_DIR/stop.sh"
    
    log_success "启动脚本创建完成"
}

# 运行系统测试
run_tests() {
    log_info "运行系统测试..."
    
    cd "$INSTALL_DIR"
    source venv/bin/activate
    
    # 基础导入测试
    python3 -c "
import sys
sys.path.insert(0, 'src')

try:
    import audio_processing
    print('✓ 核心模块导入成功')
except ImportError as e:
    print(f'✗ 核心模块导入失败: {e}')
    sys.exit(1)

try:
    import numpy, scipy, pydantic
    print('✓ 科学计算库导入成功')
except ImportError as e:
    print(f'✗ 科学计算库导入失败: {e}')
    sys.exit(1)

try:
    import pyaudio
    print('✓ 音频库导入成功')
except ImportError as e:
    print(f'✗ 音频库导入失败: {e}')
    sys.exit(1)

print('所有依赖检查通过！')
"
    
    log_success "系统测试完成"
}

# 主安装流程
main() {
    echo "=========================================="
    echo "    音频处理系统安装程序 v1.0"
    echo "    Audio Processing System Installer"
    echo "=========================================="
    echo
    
    check_root
    detect_os
    check_requirements
    
    echo
    read -p "是否继续安装？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "安装已取消"
        exit 0
    fi
    
    install_system_deps
    create_directories
    install_python_deps
    copy_application
    configure_services
    configure_nginx
    configure_firewall
    create_startup_script
    run_tests
    
    echo
    echo "=========================================="
    log_success "安装完成！"
    echo "=========================================="
    echo
    echo "安装目录: $INSTALL_DIR"
    echo "配置文件: $INSTALL_DIR/config/"
    echo "日志目录: $INSTALL_DIR/logs/"
    echo
    echo "启动系统: $INSTALL_DIR/start.sh"
    echo "停止系统: $INSTALL_DIR/stop.sh"
    echo
    echo "Web界面: http://localhost"
    echo "API文档: http://localhost/docs"
    echo
    echo "请查看用户手册了解详细配置说明"
}

# 错误处理
trap 'log_error "安装过程中发生错误，请检查日志"; exit 1' ERR

# 运行主程序
main "$@"