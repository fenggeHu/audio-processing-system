#!/usr/bin/env python3
"""
音频处理系统自动化部署脚本
Audio Processing System Automated Deployment Script
"""

import os
import sys
import json
import subprocess
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional
import shutil
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('deploy.log')
    ]
)
logger = logging.getLogger(__name__)

class AudioSystemDeployer:
    """音频处理系统部署器"""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or "deploy/config/production.json"
        self.config = self.load_config()
        self.install_dir = "/opt/audio-processing-system"
        self.user = os.getenv('USER', 'audiouser')
        
    def load_config(self) -> Dict:
        """加载部署配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"配置文件未找到: {self.config_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.error(f"配置文件格式错误: {e}")
            sys.exit(1)
    
    def check_prerequisites(self) -> bool:
        """检查部署前提条件"""
        logger.info("检查部署前提条件...")
        
        # 检查Python版本
        if sys.version_info < (3, 10):
            logger.error("需要Python 3.10或更高版本")
            return False
        
        # 检查必要的系统命令
        required_commands = ['systemctl', 'nginx', 'docker', 'docker-compose']
        for cmd in required_commands:
            if not shutil.which(cmd):
                logger.warning(f"未找到命令: {cmd}")
        
        # 检查磁盘空间
        disk_usage = shutil.disk_usage('/')
        free_gb = disk_usage.free // (1024**3)
        if free_gb < 10:
            logger.error(f"磁盘空间不足，需要至少10GB，当前可用: {free_gb}GB")
            return False
        
        logger.info("前提条件检查通过")
        return True
    
    def create_directories(self):
        """创建必要的目录结构"""
        logger.info("创建目录结构...")
        
        directories = [
            self.install_dir,
            f"{self.install_dir}/config",
            f"{self.install_dir}/logs",
            f"{self.install_dir}/recordings",
            f"{self.install_dir}/plugins",
            f"{self.install_dir}/backups",
            "/var/lib/audio-processing",
            "/var/run/audio-processing"
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            if os.geteuid() == 0:  # 如果是root用户
                shutil.chown(directory, self.user, self.user)
    
    def install_system_dependencies(self):
        """安装系统依赖"""
        logger.info("安装系统依赖...")
        
        # 检测操作系统
        if os.path.exists('/etc/debian_version'):
            # Debian/Ubuntu
            packages = [
                'python3-pip', 'python3-venv', 'python3-dev',
                'portaudio19-dev', 'libasound2-dev', 'libsndfile1-dev',
                'ffmpeg', 'gcc', 'g++', 'make', 'nginx', 'supervisor'
            ]
            cmd = ['apt-get', 'update'] 
            subprocess.run(cmd, check=True)
            cmd = ['apt-get', 'install', '-y'] + packages
            subprocess.run(cmd, check=True)
            
        elif os.path.exists('/etc/redhat-release'):
            # CentOS/RHEL
            packages = [
                'python3-pip', 'python3-devel',
                'portaudio-devel', 'alsa-lib-devel', 'libsndfile-devel',
                'ffmpeg', 'gcc', 'gcc-c++', 'make', 'nginx', 'supervisor'
            ]
            cmd = ['yum', 'install', '-y'] + packages
            subprocess.run(cmd, check=True)
        else:
            logger.warning("未识别的操作系统，请手动安装依赖")
    
    def setup_python_environment(self):
        """设置Python环境"""
        logger.info("设置Python虚拟环境...")
        
        venv_path = f"{self.install_dir}/venv"
        
        # 创建虚拟环境
        subprocess.run([sys.executable, '-m', 'venv', venv_path], check=True)
        
        # 安装依赖
        pip_path = f"{venv_path}/bin/pip"
        subprocess.run([pip_path, 'install', '--upgrade', 'pip'], check=True)
        
        # 安装项目依赖
        if os.path.exists('requirements.txt'):
            subprocess.run([pip_path, 'install', '-r', 'requirements.txt'], check=True)
    
    def deploy_application(self):
        """部署应用程序"""
        logger.info("部署应用程序...")
        
        # 复制源代码
        if os.path.exists('src'):
            shutil.copytree('src', f"{self.install_dir}/src", dirs_exist_ok=True)
        
        # 复制配置文件
        if os.path.exists('config'):
            shutil.copytree('config', f"{self.install_dir}/config", dirs_exist_ok=True)
        
        # 复制静态文件
        if os.path.exists('static'):
            shutil.copytree('static', f"{self.install_dir}/static", dirs_exist_ok=True)
    
    def configure_systemd_services(self):
        """配置systemd服务"""
        logger.info("配置系统服务...")
        
        # 主服务配置
        main_service = f"""[Unit]
Description=Audio Processing System
After=network.target sound.target
Wants=network.target

[Service]
Type=simple
User={self.user}
Group={self.user}
WorkingDirectory={self.install_dir}
Environment=PYTHONPATH={self.install_dir}/src
ExecStart={self.install_dir}/venv/bin/python -m audio_processing.main
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
        
        with open('/etc/systemd/system/audio-processing.service', 'w') as f:
            f.write(main_service)
        
        # Web服务配置
        web_service = f"""[Unit]
Description=Audio Processing Web Interface
After=network.target audio-processing.service
Wants=audio-processing.service

[Service]
Type=simple
User={self.user}
Group={self.user}
WorkingDirectory={self.install_dir}
Environment=PYTHONPATH={self.install_dir}/src
ExecStart={self.install_dir}/venv/bin/uvicorn audio_processing.services.control:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        
        with open('/etc/systemd/system/audio-processing-web.service', 'w') as f:
            f.write(web_service)
        
        # 重新加载systemd
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
    
    def configure_nginx(self):
        """配置Nginx"""
        logger.info("配置Nginx...")
        
        nginx_config = f"""server {{
    listen 80;
    server_name localhost;
    
    location /static/ {{
        alias {self.install_dir}/static/;
        expires 1y;
    }}
    
    location / {{
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
    
    location /health {{
        proxy_pass http://127.0.0.1:8000/health;
        access_log off;
    }}
}}
"""
        
        with open('/etc/nginx/sites-available/audio-processing', 'w') as f:
            f.write(nginx_config)
        
        # 启用站点
        os.symlink('/etc/nginx/sites-available/audio-processing', 
                  '/etc/nginx/sites-enabled/audio-processing')
        
        # 删除默认站点
        default_site = '/etc/nginx/sites-enabled/default'
        if os.path.exists(default_site):
            os.remove(default_site)
        
        # 测试配置
        subprocess.run(['nginx', '-t'], check=True)
    
    def start_services(self):
        """启动服务"""
        logger.info("启动服务...")
        
        services = [
            'audio-processing',
            'audio-processing-web',
            'nginx'
        ]
        
        for service in services:
            subprocess.run(['systemctl', 'enable', service], check=True)
            subprocess.run(['systemctl', 'start', service], check=True)
            
            # 等待服务启动
            time.sleep(2)
            
            # 检查服务状态
            result = subprocess.run(['systemctl', 'is-active', service], 
                                  capture_output=True, text=True)
            if result.stdout.strip() == 'active':
                logger.info(f"服务 {service} 启动成功")
            else:
                logger.error(f"服务 {service} 启动失败")
    
    def run_health_check(self):
        """运行健康检查"""
        logger.info("运行健康检查...")
        
        import requests
        import time
        
        # 等待服务完全启动
        time.sleep(10)
        
        try:
            response = requests.get('http://localhost/health', timeout=10)
            if response.status_code == 200:
                logger.info("健康检查通过")
                return True
            else:
                logger.error(f"健康检查失败，状态码: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"健康检查异常: {e}")
            return False
    
    def deploy(self):
        """执行完整部署流程"""
        logger.info("开始部署音频处理系统...")
        
        try:
            if not self.check_prerequisites():
                logger.error("前提条件检查失败，部署终止")
                return False
            
            self.create_directories()
            self.install_system_dependencies()
            self.setup_python_environment()
            self.deploy_application()
            self.configure_systemd_services()
            self.configure_nginx()
            self.start_services()
            
            if self.run_health_check():
                logger.info("部署成功完成！")
                logger.info("Web界面: http://localhost")
                logger.info("API文档: http://localhost/docs")
                return True
            else:
                logger.error("部署完成但健康检查失败")
                return False
                
        except Exception as e:
            logger.error(f"部署过程中发生错误: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description='音频处理系统自动化部署')
    parser.add_argument('--config', '-c', help='配置文件路径')
    parser.add_argument('--dry-run', action='store_true', help='试运行模式')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if os.geteuid() != 0:
        logger.error("请使用root权限运行此脚本")
        sys.exit(1)
    
    deployer = AudioSystemDeployer(args.config)
    
    if args.dry_run:
        logger.info("试运行模式，不会执行实际部署")
        return
    
    success = deployer.deploy()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()