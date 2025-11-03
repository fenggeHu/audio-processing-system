#!/usr/bin/env python3
"""
多架构离线包构建工具
Multi-Architecture Offline Package Builder

支持为不同架构（x86_64, ARM64, ARMv7）构建离线部署包
"""

import os
import sys
import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional
import argparse
import logging
import concurrent.futures
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class ArchitectureConfig:
    """架构配置"""
    name: str
    pip_platform: str
    docker_platform: str
    system_packages: Dict[str, List[str]]  # 不同发行版的系统包

class MultiArchBuilder:
    """多架构构建器"""
    
    def __init__(self, output_dir: str = "dist/multi-arch"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 架构配置
        self.architectures = {
            "x86_64": ArchitectureConfig(
                name="x86_64",
                pip_platform="linux_x86_64",
                docker_platform="linux/amd64",
                system_packages={
                    "ubuntu": [
                        "python3-dev", "portaudio19-dev", "libasound2-dev",
                        "libsndfile1-dev", "libfftw3-dev", "ffmpeg",
                        "gcc", "g++", "make", "pkg-config"
                    ],
                    "centos": [
                        "python3-devel", "portaudio-devel", "alsa-lib-devel",
                        "libsndfile-devel", "fftw-devel", "ffmpeg",
                        "gcc", "gcc-c++", "make", "pkgconfig"
                    ]
                }
            ),
            "aarch64": ArchitectureConfig(
                name="aarch64",
                pip_platform="linux_aarch64",
                docker_platform="linux/arm64",
                system_packages={
                    "ubuntu": [
                        "python3-dev", "portaudio19-dev", "libasound2-dev",
                        "libsndfile1-dev", "libfftw3-dev", "ffmpeg",
                        "gcc", "g++", "make", "pkg-config"
                    ],
                    "centos": [
                        "python3-devel", "portaudio-devel", "alsa-lib-devel",
                        "libsndfile-devel", "fftw-devel", "ffmpeg",
                        "gcc", "gcc-c++", "make", "pkgconfig"
                    ]
                }
            ),
            "armv7l": ArchitectureConfig(
                name="armv7l",
                pip_platform="linux_armv7l",
                docker_platform="linux/arm/v7",
                system_packages={
                    "ubuntu": [
                        "python3-dev", "portaudio19-dev", "libasound2-dev",
                        "libsndfile1-dev", "libfftw3-dev", "ffmpeg",
                        "gcc", "g++", "make", "pkg-config"
                    ]
                }
            )
        }
    
    def check_docker_availability(self) -> bool:
        """检查Docker是否可用"""
        try:
            result = subprocess.run(["docker", "--version"], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"Docker可用: {result.stdout.strip()}")
                return True
        except FileNotFoundError:
            pass
        
        logger.warning("Docker不可用，将使用本地环境构建")
        return False
    
    def build_for_architecture(self, arch_name: str, use_docker: bool = True) -> str:
        """为特定架构构建离线包"""
        if arch_name not in self.architectures:
            raise ValueError(f"不支持的架构: {arch_name}")
        
        arch_config = self.architectures[arch_name]
        logger.info(f"开始构建架构: {arch_name}")
        
        if use_docker and self.check_docker_availability():
            return self._build_with_docker(arch_config)
        else:
            return self._build_native(arch_config)
    
    def _build_with_docker(self, arch_config: ArchitectureConfig) -> str:
        """使用Docker构建"""
        logger.info(f"使用Docker构建 {arch_config.name}")
        
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # 创建Dockerfile
            dockerfile_content = f'''
FROM --platform={arch_config.docker_platform} python:3.10-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \\
    python3-dev \\
    portaudio19-dev \\
    libasound2-dev \\
    libsndfile1-dev \\
    libfftw3-dev \\
    ffmpeg \\
    gcc \\
    g++ \\
    make \\
    pkg-config \\
    curl \\
    wget \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制requirements文件
COPY requirements-offline.txt .

# 创建下载目录
RUN mkdir -p /packages

# 下载Python包
RUN pip download \\
    --requirement requirements-offline.txt \\
    --dest /packages \\
    --platform {arch_config.pip_platform} \\
    --python-version 3.10 \\
    --implementation cp \\
    --abi cp310 \\
    --only-binary=:all: || \\
    pip download \\
    --requirement requirements-offline.txt \\
    --dest /packages

# 创建输出脚本
CMD ["tar", "-czf", "/output/packages.tar.gz", "-C", "/packages", "."]
'''
            
            dockerfile_path = temp_path / "Dockerfile"
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)
            
            # 复制requirements文件
            shutil.copy2("requirements-offline.txt", temp_path)
            
            # 构建Docker镜像
            image_name = f"audio-processing-builder-{arch_config.name}"
            build_cmd = [
                "docker", "build",
                "--platform", arch_config.docker_platform,
                "-t", image_name,
                str(temp_path)
            ]
            
            subprocess.run(build_cmd, check=True)
            
            # 运行容器下载包
            output_dir = self.output_dir / arch_config.name
            output_dir.mkdir(exist_ok=True)
            
            run_cmd = [
                "docker", "run", "--rm",
                "--platform", arch_config.docker_platform,
                "-v", f"{output_dir}:/output",
                image_name
            ]
            
            subprocess.run(run_cmd, check=True)
            
            # 清理Docker镜像
            subprocess.run(["docker", "rmi", image_name], check=True)
            
            return str(output_dir / "packages.tar.gz")
    
    def _build_native(self, arch_config: ArchitectureConfig) -> str:
        """本地构建（当前架构）"""
        logger.info(f"本地构建 {arch_config.name}")
        
        output_dir = self.output_dir / arch_config.name
        output_dir.mkdir(exist_ok=True)
        
        # 使用pip下载包
        cmd = [
            sys.executable, "-m", "pip", "download",
            "--requirement", "requirements-offline.txt",
            "--dest", str(output_dir),
            "--platform", arch_config.pip_platform,
            "--python-version", "3.10",
            "--implementation", "cp",
            "--abi", "cp310",
            "--only-binary=:all:"
        ]
        
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            # 回退到不指定平台的下载
            fallback_cmd = [
                sys.executable, "-m", "pip", "download",
                "--requirement", "requirements-offline.txt",
                "--dest", str(output_dir)
            ]
            subprocess.run(fallback_cmd, check=True)
        
        return str(output_dir)
    
    def create_unified_installer(self, arch_packages: Dict[str, str]) -> str:
        """创建统一的多架构安装器"""
        logger.info("创建统一安装器...")
        
        installer_content = '''#!/bin/bash
# 音频处理系统多架构离线安装器
# Audio Processing System Multi-Architecture Offline Installer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/audio-processing-system"
USER_NAME="${SUDO_USER:-$USER}"

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

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检测架构
detect_architecture() {
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64|amd64)
            ARCH="x86_64"
            ;;
        aarch64|arm64)
            ARCH="aarch64"
            ;;
        armv7l|armhf)
            ARCH="armv7l"
            ;;
        *)
            log_error "不支持的架构: $ARCH"
            log_info "支持的架构: x86_64, aarch64, armv7l"
            exit 1
            ;;
    esac
    
    log_info "检测到架构: $ARCH"
    
    # 检查是否有对应架构的包
    if [[ ! -d "$SCRIPT_DIR/packages/$ARCH" ]]; then
        log_error "未找到架构 $ARCH 的安装包"
        log_info "可用架构:"
        ls -1 "$SCRIPT_DIR/packages/" 2>/dev/null || echo "  无"
        exit 1
    fi
}

# 检测操作系统
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS_ID=$ID
        OS_VERSION=$VERSION_ID
    else
        log_error "无法检测操作系统"
        exit 1
    fi
    
    log_info "检测到操作系统: $OS_ID $OS_VERSION"
}

# 安装系统依赖
install_system_dependencies() {
    log_info "安装系统依赖..."
    
    case "$OS_ID" in
        ubuntu|debian)
            apt-get update
            apt-get install -y \\
                python3-dev \\
                portaudio19-dev \\
                libasound2-dev \\
                libsndfile1-dev \\
                libfftw3-dev \\
                ffmpeg \\
                gcc \\
                g++ \\
                make \\
                pkg-config \\
                curl \\
                wget
            ;;
        centos|rhel|fedora)
            yum update -y
            yum groupinstall -y "Development Tools"
            yum install -y \\
                python3-devel \\
                portaudio-devel \\
                alsa-lib-devel \\
                libsndfile-devel \\
                fftw-devel \\
                ffmpeg \\
                curl \\
                wget
            ;;
        *)
            log_warning "未知操作系统 $OS_ID，请手动安装系统依赖"
            ;;
    esac
}

# 创建Python环境
create_python_environment() {
    log_info "创建Python虚拟环境..."
    
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    
    sudo -u "$USER_NAME" python3 -m venv venv
    source venv/bin/activate
    
    # 升级pip
    pip install --upgrade pip setuptools wheel
    
    # 安装离线包
    log_info "安装Python离线包..."
    pip install --no-index --find-links "$SCRIPT_DIR/packages/$ARCH" \\
        --requirement "$SCRIPT_DIR/requirements-offline.txt"
}

# 复制应用文件
copy_application() {
    log_info "复制应用文件..."
    
    # 复制源代码
    if [[ -d "$SCRIPT_DIR/src" ]]; then
        cp -r "$SCRIPT_DIR/src" "$INSTALL_DIR/"
    fi
    
    # 复制配置文件
    if [[ -d "$SCRIPT_DIR/config" ]]; then
        cp -r "$SCRIPT_DIR/config" "$INSTALL_DIR/"
    fi
    
    # 复制静态文件
    if [[ -d "$SCRIPT_DIR/static" ]]; then
        cp -r "$SCRIPT_DIR/static" "$INSTALL_DIR/"
    fi
    
    # 设置权限
    chown -R "$USER_NAME:$USER_NAME" "$INSTALL_DIR"
}

# 配置系统服务
configure_services() {
    log_info "配置系统服务..."
    
    # 创建systemd服务文件
    cat > /etc/systemd/system/audio-processing.service << EOF
[Unit]
Description=Audio Processing System
After=network.target sound.target
Wants=network.target

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR/src
ExecStart=$INSTALL_DIR/venv/bin/python -m audio_processing.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable audio-processing
}

# 验证安装
verify_installation() {
    log_info "验证安装..."
    
    cd "$INSTALL_DIR"
    source venv/bin/activate
    
    python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    import audio_processing
    print('✓ 核心模块导入成功')
except ImportError as e:
    print(f'✗ 模块导入失败: {e}')
    sys.exit(1)
"
}

# 主安装流程
main() {
    echo "=========================================="
    echo "  音频处理系统多架构离线安装器 v1.0"
    echo "=========================================="
    echo
    
    # 检查权限
    if [[ $EUID -ne 0 ]]; then
        log_error "请使用sudo运行此脚本"
        exit 1
    fi
    
    detect_architecture
    detect_os
    install_system_dependencies
    create_python_environment
    copy_application
    configure_services
    verify_installation
    
    echo
    log_success "多架构离线安装完成！"
    echo
    echo "安装目录: $INSTALL_DIR"
    echo "架构: $ARCH"
    echo "启动服务: systemctl start audio-processing"
    echo "Web界面: http://localhost"
}

main "$@"
'''
        
        installer_path = self.output_dir / "install_multi_arch.sh"
        with open(installer_path, "w") as f:
            f.write(installer_content)
        
        installer_path.chmod(0o755)
        
        return str(installer_path)
    
    def build_all_architectures(self, architectures: List[str] = None, 
                               use_docker: bool = True) -> str:
        """构建所有架构的离线包"""
        if architectures is None:
            architectures = list(self.architectures.keys())
        
        logger.info(f"开始构建多架构离线包: {architectures}")
        
        # 并行构建不同架构
        arch_packages = {}
        
        if use_docker and self.check_docker_availability():
            # 使用线程池并行构建
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                future_to_arch = {
                    executor.submit(self.build_for_architecture, arch, True): arch
                    for arch in architectures
                }
                
                for future in concurrent.futures.as_completed(future_to_arch):
                    arch = future_to_arch[future]
                    try:
                        package_path = future.result()
                        arch_packages[arch] = package_path
                        logger.info(f"架构 {arch} 构建完成: {package_path}")
                    except Exception as e:
                        logger.error(f"架构 {arch} 构建失败: {e}")
        else:
            # 顺序构建
            for arch in architectures:
                try:
                    package_path = self.build_for_architecture(arch, False)
                    arch_packages[arch] = package_path
                    logger.info(f"架构 {arch} 构建完成: {package_path}")
                except Exception as e:
                    logger.error(f"架构 {arch} 构建失败: {e}")
        
        # 创建统一安装器
        installer_path = self.create_unified_installer(arch_packages)
        
        # 复制应用文件到输出目录
        self._copy_application_to_output()
        
        # 复制requirements文件
        shutil.copy2("requirements-offline.txt", self.output_dir)
        
        # 创建最终的多架构包
        package_name = f"audio-processing-system-multi-arch-offline-v1.0.tar.gz"
        package_path = self.output_dir.parent / package_name
        
        import tarfile
        with tarfile.open(package_path, "w:gz") as tar:
            tar.add(self.output_dir, arcname="audio-processing-system-multi-arch")
        
        logger.info(f"多架构离线包构建完成: {package_path}")
        logger.info(f"包大小: {package_path.stat().st_size / 1024 / 1024:.1f} MB")
        
        return str(package_path)
    
    def _copy_application_to_output(self):
        """复制应用文件到输出目录"""
        logger.info("复制应用文件到输出目录...")
        
        # 复制源代码
        if Path("src").exists():
            shutil.copytree("src", self.output_dir / "src", dirs_exist_ok=True)
        
        # 复制配置文件
        if Path("config").exists():
            shutil.copytree("config", self.output_dir / "config", dirs_exist_ok=True)
        
        # 复制静态文件
        if Path("static").exists():
            shutil.copytree("static", self.output_dir / "static", dirs_exist_ok=True)
        
        # 复制重要文件
        important_files = ["README.md", "LICENSE", "pyproject.toml"]
        for file_name in important_files:
            file_path = Path(file_name)
            if file_path.exists():
                shutil.copy2(file_path, self.output_dir / file_name)

def main():
    parser = argparse.ArgumentParser(description="多架构离线包构建工具")
    parser.add_argument("--output", "-o", default="dist/multi-arch",
                       help="输出目录")
    parser.add_argument("--architectures", "-a", nargs="+",
                       choices=["x86_64", "aarch64", "armv7l"],
                       default=["x86_64", "aarch64"],
                       help="目标架构")
    parser.add_argument("--no-docker", action="store_true",
                       help="不使用Docker构建")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    builder = MultiArchBuilder(args.output)
    
    try:
        package_path = builder.build_all_architectures(
            args.architectures, 
            not args.no_docker
        )
        
        print(f"\n✓ 多架构离线包构建成功: {package_path}")
        print(f"\n支持的架构: {', '.join(args.architectures)}")
        print("\n使用方法:")
        print(f"1. 将 {Path(package_path).name} 传输到目标设备")
        print("2. 解压: tar -xzf audio-processing-system-multi-arch-offline-*.tar.gz")
        print("3. 安装: cd audio-processing-system-multi-arch && sudo ./install_multi_arch.sh")
        
    except Exception as e:
        logger.error(f"构建失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()