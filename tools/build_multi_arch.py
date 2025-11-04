#!/usr/bin/env python3
"""
多架构离线包构建工具
Multi-Architecture Offline Package Builder

支持为不同架构（x86_64, ARM64, ARMv7）构建离线部署包
"""

import sys
import subprocess
import tempfile
import shutil
import tarfile
import hashlib
import json
import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import argparse
import logging
import concurrent.futures
from dataclasses import dataclass, asdict

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

@dataclass
class OSConfig:
    """操作系统配置"""
    name: str
    version: str
    docker_image: str
    package_manager: str
    system_packages: List[str]
    install_commands: List[str]

@dataclass
class PackageManifest:
    """包清单"""
    version: str
    created_at: str
    python_version: str
    platform: str
    architecture: str
    os_name: str
    os_version: str
    package_count: int
    total_size: int
    checksum: str
    supported_architectures: List[str]

class MultiArchBuilder:
    """多架构构建器"""
    
    def __init__(self, output_dir: str = "dist/multi-arch"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.version = "1.0.0"
        
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
        
        # 操作系统配置
        self.os_configs = {
            "ubuntu20": OSConfig(
                name="ubuntu",
                version="20.04",
                docker_image="ubuntu:20.04",
                package_manager="apt",
                system_packages=[
                    "python3", "python3-pip", "python3-dev", "python3-venv",
                    "portaudio19-dev", "libasound2-dev", "libsndfile1-dev",
                    "libfftw3-dev", "ffmpeg", "gcc", "g++", "make", "pkg-config",
                    "curl", "wget", "ca-certificates"
                ],
                install_commands=[
                    "apt-get update",
                    "DEBIAN_FRONTEND=noninteractive apt-get install -y"
                ]
            ),
            "ubuntu22": OSConfig(
                name="ubuntu",
                version="22.04",
                docker_image="ubuntu:22.04",
                package_manager="apt",
                system_packages=[
                    "python3", "python3-pip", "python3-dev", "python3-venv",
                    "portaudio19-dev", "libasound2-dev", "libsndfile1-dev",
                    "libfftw3-dev", "ffmpeg", "gcc", "g++", "make", "pkg-config",
                    "curl", "wget", "ca-certificates"
                ],
                install_commands=[
                    "apt-get update",
                    "DEBIAN_FRONTEND=noninteractive apt-get install -y"
                ]
            ),
            "ubuntu24": OSConfig(
                name="ubuntu",
                version="24.04",
                docker_image="ubuntu:24.04",
                package_manager="apt",
                system_packages=[
                    "python3", "python3-pip", "python3-dev", "python3-venv",
                    "portaudio19-dev", "libasound2-dev", "libsndfile1-dev",
                    "libfftw3-dev", "ffmpeg", "gcc", "g++", "make", "pkg-config",
                    "curl", "wget", "ca-certificates"
                ],
                install_commands=[
                    "apt-get update",
                    "DEBIAN_FRONTEND=noninteractive apt-get install -y"
                ]
            ),
            "centos7": OSConfig(
                name="centos",
                version="7",
                docker_image="centos:7",
                package_manager="yum",
                system_packages=[
                    "python3", "python3-pip", "python3-devel",
                    "portaudio-devel", "alsa-lib-devel", "libsndfile-devel",
                    "fftw-devel", "ffmpeg", "gcc", "gcc-c++", "make",
                    "pkgconfig", "curl", "wget", "ca-certificates"
                ],
                install_commands=[
                    "yum update -y",
                    "yum install -y epel-release",
                    "yum install -y"
                ]
            ),
            "centos8": OSConfig(
                name="centos",
                version="8",
                docker_image="quay.io/centos/centos:stream8",
                package_manager="dnf",
                system_packages=[
                    "python3", "python3-pip", "python3-devel",
                    "portaudio-devel", "alsa-lib-devel", "libsndfile-devel",
                    "fftw-devel", "gcc", "gcc-c++", "make",
                    "pkgconfig", "curl", "wget", "ca-certificates"
                ],
                install_commands=[
                    "dnf update -y",
                    "dnf install -y epel-release",
                    "dnf config-manager --set-enabled powertools",
                    "dnf install -y"
                ]
            ),
            "rocky8": OSConfig(
                name="rocky",
                version="8",
                docker_image="rockylinux:8",
                package_manager="dnf",
                system_packages=[
                    "python3", "python3-pip", "python3-devel",
                    "portaudio-devel", "alsa-lib-devel", "libsndfile-devel",
                    "fftw-devel", "gcc", "gcc-c++", "make",
                    "pkgconfig", "curl", "wget", "ca-certificates"
                ],
                install_commands=[
                    "dnf update -y",
                    "dnf install -y epel-release",
                    "dnf config-manager --set-enabled powertools",
                    "dnf install -y"
                ]
            ),
            "rocky9": OSConfig(
                name="rocky",
                version="9",
                docker_image="rockylinux:9",
                package_manager="dnf",
                system_packages=[
                    "python3", "python3-pip", "python3-devel",
                    "portaudio-devel", "alsa-lib-devel", "libsndfile-devel",
                    "fftw-devel", "gcc", "gcc-c++", "make",
                    "pkgconfig", "curl", "wget", "ca-certificates"
                ],
                install_commands=[
                    "dnf update -y",
                    "dnf install -y epel-release",
                    "dnf config-manager --set-enabled crb",
                    "dnf install -y"
                ]
            )
        }
    
    def detect_platform(self) -> Tuple[str, str]:
        """检测当前平台和架构"""
        import platform
        
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        # 标准化架构名称
        arch_mapping = {
            "x86_64": "x86_64",
            "amd64": "x86_64",
            "aarch64": "aarch64",
            "arm64": "aarch64",
            "armv7l": "armv7l",
            "armhf": "armv7l"
        }
        
        arch = arch_mapping.get(machine, machine)
        
        return system, arch
    
    def get_requirements(self) -> List[str]:
        """获取项目依赖列表"""
        requirements = []
        
        # 从 pyproject.toml 读取依赖
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
            
        pyproject_path = Path("pyproject.toml")
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                
            # 主要依赖
            if "project" in data and "dependencies" in data["project"]:
                requirements.extend(data["project"]["dependencies"])
        
        # 从 requirements.txt 读取（如果存在）
        req_file = Path("requirements.txt")
        if req_file.exists():
            with open(req_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        requirements.append(line)
        
        # 添加打包相关的额外依赖
        packaging_deps = [
            "pip-tools>=7.0.0",
            "wheel>=0.40.0",
            "setuptools>=68.0.0",
            "pip>=23.0.0"
        ]
        requirements.extend(packaging_deps)
        
        return list(set(requirements))  # 去重
    
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
    
    def build_for_architecture(self, arch_name: str, os_name: str = None,
                              use_docker: bool = True, 
                              create_individual_package: bool = True) -> str:
        """为特定架构和操作系统构建离线包"""
        if arch_name not in self.architectures:
            raise ValueError(f"不支持的架构: {arch_name}")
        
        arch_config = self.architectures[arch_name]
        
        # 如果指定了操作系统，验证其有效性
        os_config = None
        if os_name:
            if os_name not in self.os_configs:
                raise ValueError(f"不支持的操作系统: {os_name}")
            os_config = self.os_configs[os_name]
            logger.info(f"开始构建架构: {arch_name}, 操作系统: {os_config.name} {os_config.version}")
        else:
            logger.info(f"开始构建架构: {arch_name}")
        
        # 创建架构和操作系统特定的工作目录
        if os_config:
            work_dir_name = f"{arch_name}-{os_name}"
        else:
            work_dir_name = arch_name
            
        arch_work_dir = self.output_dir / work_dir_name
        arch_work_dir.mkdir(exist_ok=True)
        
        if use_docker and self.check_docker_availability():
            packages_path = self._build_with_docker(arch_config, arch_work_dir, os_config)
        else:
            packages_path = self._build_native(arch_config, arch_work_dir)
        
        if create_individual_package:
            return self._create_individual_package(arch_config, arch_work_dir, packages_path, os_config)
        else:
            return packages_path
    
    def _build_with_docker(self, arch_config: ArchitectureConfig, 
                          arch_work_dir: Path, os_config: OSConfig = None) -> str:
        """使用Docker构建"""
        if os_config:
            logger.info(f"使用Docker构建 {arch_config.name} ({os_config.name} {os_config.version})")
        else:
            logger.info(f"使用Docker构建 {arch_config.name}")
        
        # 获取依赖列表
        requirements = self.get_requirements()
        
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # 创建requirements文件
            req_file = temp_path / "requirements.txt"
            with open(req_file, "w") as f:
                for req in requirements:
                    f.write(f"{req}\n")
            
            # 根据是否指定操作系统创建不同的Dockerfile
            if os_config:
                dockerfile_content = self._create_os_specific_dockerfile(arch_config, os_config)
            else:
                dockerfile_content = self._create_default_dockerfile(arch_config)
            
            dockerfile_path = temp_path / "Dockerfile"
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)
            
            dockerfile_path = temp_path / "Dockerfile"
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)
            
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
            packages_dir = arch_work_dir / "python_packages"
            packages_dir.mkdir(exist_ok=True)
            
            run_cmd = [
                "docker", "run", "--rm",
                "--platform", arch_config.docker_platform,
                "-v", f"{packages_dir}:/output",
                image_name
            ]
            
            subprocess.run(run_cmd, check=True)
            
            # 清理Docker镜像
            subprocess.run(["docker", "rmi", image_name], check=True)
            
            return str(packages_dir / "packages.tar.gz")
    
    def _build_native(self, arch_config: ArchitectureConfig, 
                     arch_work_dir: Path) -> str:
        """本地构建（当前架构）"""
        logger.info(f"本地构建 {arch_config.name}")
        
        # 获取依赖列表
        requirements = self.get_requirements()
        
        # 创建Python包目录
        packages_dir = arch_work_dir / "python_packages" / arch_config.name
        packages_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建requirements文件
        req_file = arch_work_dir / "requirements.txt"
        with open(req_file, "w") as f:
            for req in requirements:
                f.write(f"{req}\n")
        
        # 智能下载策略：多种方案确保成功率
        download_success = False
        
        # 策略1：尝试平台特定下载（如果不是当前平台）
        current_platform, current_arch = self.detect_platform()
        if arch_config.name != current_arch:
            logger.info(f"尝试下载 {arch_config.name} 平台特定的包...")
            cmd_platform = [
                sys.executable, "-m", "pip", "download",
                "--requirement", str(req_file),
                "--dest", str(packages_dir),
                "--platform", arch_config.pip_platform,
                "--python-version", "3.10",
                "--implementation", "cp",
                "--abi", "cp310",
                "--only-binary=:all:"
            ]
            
            try:
                subprocess.run(cmd_platform, capture_output=True, text=True, check=True)
                download_success = True
                logger.info("平台特定下载成功")
            except subprocess.CalledProcessError as e:
                logger.info("平台特定下载失败，尝试通用下载...")
        
        # 策略2：通用下载（适用于当前平台或作为回退）
        if not download_success:
            logger.info("使用通用下载策略...")
            cmd_generic = [
                sys.executable, "-m", "pip", "download",
                "--requirement", str(req_file),
                "--dest", str(packages_dir),
                "--prefer-binary"
            ]
            
            try:
                subprocess.run(cmd_generic, capture_output=True, text=True, check=True)
                download_success = True
                logger.info("通用下载成功")
            except subprocess.CalledProcessError:
                logger.info("通用下载失败，尝试逐个下载...")
        
        # 策略3：逐个下载（最后的回退方案）
        if not download_success:
            successful_packages = []
            failed_packages = []
            
            for req in requirements:
                package_downloaded = False
                package_name = req.split('>=')[0].split('==')[0].split('<')[0].split('>')[0].strip()
                
                # 尝试下载指定版本
                try:
                    cmd_single = [
                        sys.executable, "-m", "pip", "download",
                        req,
                        "--dest", str(packages_dir),
                        "--prefer-binary"
                    ]
                    subprocess.run(cmd_single, capture_output=True, text=True, check=True)
                    successful_packages.append(req)
                    package_downloaded = True
                except subprocess.CalledProcessError:
                    # 尝试下载最新版本
                    try:
                        cmd_latest = [
                            sys.executable, "-m", "pip", "download",
                            package_name,
                            "--dest", str(packages_dir),
                            "--prefer-binary"
                        ]
                        subprocess.run(cmd_latest, capture_output=True, text=True, check=True)
                        successful_packages.append(package_name)
                        package_downloaded = True
                    except subprocess.CalledProcessError:
                        failed_packages.append(req)
            
            if successful_packages:
                download_success = True
                logger.info(f"逐个下载完成，成功: {len(successful_packages)}, 失败: {len(failed_packages)}")
                if failed_packages:
                    logger.warning(f"无法下载的包: {failed_packages}")
        
        if not download_success:
            raise RuntimeError("所有下载策略都失败了")
        
        return str(packages_dir)
    
    def _create_default_dockerfile(self, arch_config: ArchitectureConfig) -> str:
        """创建默认的Dockerfile（基于Python官方镜像）"""
        return f'''FROM --platform={arch_config.docker_platform} python:3.10-slim

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
COPY requirements.txt .

# 创建下载目录
RUN mkdir -p /packages

# 下载Python包
RUN pip download \\
    --requirement requirements.txt \\
    --dest /packages \\
    --platform {arch_config.pip_platform} \\
    --python-version 3.10 \\
    --implementation cp \\
    --abi cp310 \\
    --only-binary=:all: || \\
    pip download \\
    --requirement requirements.txt \\
    --dest /packages

# 创建输出脚本
CMD ["tar", "-czf", "/output/packages.tar.gz", "-C", "/packages", "."]
'''
    
    def _create_os_specific_dockerfile(self, arch_config: ArchitectureConfig, 
                                     os_config: OSConfig) -> str:
        """创建特定操作系统的Dockerfile"""
        
        # 构建系统包安装命令
        install_cmd = " ".join(os_config.install_commands)
        packages = " ".join(os_config.system_packages)
        
        # 根据包管理器类型调整清理命令
        if os_config.package_manager == "apt":
            cleanup_cmd = "&& rm -rf /var/lib/apt/lists/*"
        elif os_config.package_manager in ["yum", "dnf"]:
            cleanup_cmd = "&& yum clean all" if os_config.package_manager == "yum" else "&& dnf clean all"
        else:
            cleanup_cmd = ""
        
        return f'''FROM --platform={arch_config.docker_platform} {os_config.docker_image}

# 安装系统依赖
RUN {install_cmd} {packages} {cleanup_cmd}

# 确保Python3和pip可用
RUN python3 --version && pip3 --version

WORKDIR /app

# 复制requirements文件
COPY requirements.txt .

# 创建下载目录
RUN mkdir -p /packages

# 下载Python包
RUN pip3 download \\
    --requirement requirements.txt \\
    --dest /packages \\
    --platform {arch_config.pip_platform} \\
    --python-version 3.10 \\
    --implementation cp \\
    --abi cp310 \\
    --only-binary=:all: || \\
    pip3 download \\
    --requirement requirements.txt \\
    --dest /packages

# 创建输出脚本
CMD ["tar", "-czf", "/output/packages.tar.gz", "-C", "/packages", "."]
'''
    
    def _create_individual_package(self, arch_config: ArchitectureConfig, 
                                  arch_work_dir: Path, packages_path: str, 
                                  os_config: OSConfig = None) -> str:
        """为单个架构创建完整的离线包"""
        if os_config:
            logger.info(f"创建 {arch_config.name} 架构的单独离线包 ({os_config.name} {os_config.version})...")
        else:
            logger.info(f"创建 {arch_config.name} 架构的单独离线包...")
        
        # 检测平台
        platform, _ = self.detect_platform()
        
        # 复制应用文件到架构工作目录
        self._copy_application_to_arch_dir(arch_work_dir)
        
        # 创建架构特定的安装脚本
        self._create_arch_installer(arch_config, arch_work_dir, os_config)
        
        # 创建系统依赖安装脚本
        self._create_system_deps_script(arch_config, arch_work_dir, os_config)
        
        # 创建清单文件
        self._create_arch_manifest(arch_config, arch_work_dir, packages_path, os_config)
        
        # 创建最终的tar包
        if os_config:
            package_name = f"audio-processing-system-offline-{self.version}-{os_config.name}{os_config.version}-{arch_config.name}.tar.gz"
        else:
            package_name = f"audio-processing-system-offline-{self.version}-{platform}-{arch_config.name}.tar.gz"
        package_path = self.output_dir / package_name
        
        with tarfile.open(package_path, "w:gz") as tar:
            tar.add(arch_work_dir, arcname=f"audio-processing-system-offline")
        
        # 计算校验和
        with open(package_path, "rb") as f:
            checksum = hashlib.sha256(f.read()).hexdigest()
        
        # 创建校验和文件
        checksum_file = package_path.with_suffix(package_path.suffix + ".sha256")
        with open(checksum_file, "w") as f:
            f.write(f"{checksum}  {package_name}\n")
        
        logger.info(f"单架构包创建完成: {package_path}")
        logger.info(f"包大小: {package_path.stat().st_size / 1024 / 1024:.1f} MB")
        logger.info(f"校验和: {checksum}")
        
        return str(package_path)
    
    def _copy_application_to_arch_dir(self, arch_work_dir: Path):
        """复制应用文件到架构目录"""
        # 复制源代码
        if Path("src").exists():
            shutil.copytree("src", arch_work_dir / "src", dirs_exist_ok=True)
        
        # 复制配置文件
        if Path("config").exists():
            shutil.copytree("config", arch_work_dir / "config", dirs_exist_ok=True)
        
        # 复制静态文件
        if Path("static").exists():
            shutil.copytree("static", arch_work_dir / "static", dirs_exist_ok=True)
        
        # 复制重要文件
        important_files = ["README.md", "LICENSE", "pyproject.toml"]
        for file_name in important_files:
            file_path = Path(file_name)
            if file_path.exists():
                shutil.copy2(file_path, arch_work_dir / file_name)
    
    def _create_arch_installer(self, arch_config: ArchitectureConfig, arch_work_dir: Path, 
                              os_config: OSConfig = None):
        """创建架构特定的安装脚本"""
        scripts_dir = arch_work_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        
        installer_content = f'''#!/bin/bash
# 音频处理系统离线安装器 - {arch_config.name}
# Audio Processing System Offline Installer - {arch_config.name}

set -e

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
INSTALL_DIR="/opt/audio-processing-system"
USER_NAME="${{SUDO_USER:-$USER}}"
ARCH="{arch_config.name}"

# 颜色定义
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
NC='\\033[0m'

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

# 检查架构匹配
check_architecture() {{
    CURRENT_ARCH=$(uname -m)
    case "$CURRENT_ARCH" in
        x86_64|amd64)
            CURRENT_ARCH="x86_64"
            ;;
        aarch64|arm64)
            CURRENT_ARCH="aarch64"
            ;;
        armv7l|armhf)
            CURRENT_ARCH="armv7l"
            ;;
    esac
    
    if [[ "$CURRENT_ARCH" != "$ARCH" ]]; then
        log_warning "架构不匹配: 当前=$CURRENT_ARCH, 包=$ARCH"
        log_warning "继续安装可能会遇到兼容性问题"
        read -p "是否继续? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        log_info "架构匹配: $ARCH"
    fi
}}

# 安装系统依赖
install_system_dependencies() {{
    log_info "安装系统依赖..."
    
    if [[ -f "$SCRIPT_DIR/install_system_deps.sh" ]]; then
        bash "$SCRIPT_DIR/install_system_deps.sh"
    else
        log_warning "未找到系统依赖安装脚本"
    fi
}}

# 创建Python环境
create_python_environment() {{
    log_info "创建Python虚拟环境..."
    
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    
    if [[ $EUID -eq 0 ]]; then
        sudo -u "$USER_NAME" python3 -m venv venv
    else
        python3 -m venv venv
    fi
    
    source venv/bin/activate
    pip install --upgrade pip setuptools wheel
    
    # 安装离线包
    log_info "安装Python离线包..."
    PACKAGES_DIR="$SCRIPT_DIR/../python_packages/$ARCH"
    if [[ -d "$PACKAGES_DIR" ]]; then
        pip install --no-index --find-links "$PACKAGES_DIR" \\
            --requirement "$SCRIPT_DIR/../requirements.txt"
    else
        log_error "未找到Python包目录: $PACKAGES_DIR"
        exit 1
    fi
}}

# 复制应用文件
copy_application() {{
    log_info "复制应用文件..."
    
    for dir in src config static; do
        if [[ -d "$SCRIPT_DIR/../$dir" ]]; then
            cp -r "$SCRIPT_DIR/../$dir" "$INSTALL_DIR/"
        fi
    done
    
    # 设置权限
    if [[ $EUID -eq 0 ]]; then
        chown -R "$USER_NAME:$USER_NAME" "$INSTALL_DIR"
    fi
}}

# 主安装流程
main() {{
    echo "=========================================="
    echo "  音频处理系统离线安装器 - $ARCH"
    echo "=========================================="
    echo
    
    check_architecture
    install_system_dependencies
    create_python_environment
    copy_application
    
    echo
    log_success "离线安装完成！"
    echo
    echo "安装目录: $INSTALL_DIR"
    echo "架构: $ARCH"
}}

main "$@"
'''
        
        installer_path = scripts_dir / "install_offline.sh"
        with open(installer_path, "w") as f:
            f.write(installer_content)
        
        installer_path.chmod(0o755)
    
    def _create_system_deps_script(self, arch_config: ArchitectureConfig, arch_work_dir: Path,
                                  os_config: OSConfig = None):
        """创建系统依赖安装脚本"""
        scripts_dir = arch_work_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        
        # 创建系统依赖安装脚本
        script_content = '''#!/bin/bash
# 系统依赖安装脚本
# System Dependencies Installation Script

set -e

# 颜色定义
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# 检查是否为root用户
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "此脚本需要root权限，请使用sudo运行"
        exit 1
    fi
}

# 检测操作系统
detect_os() {
    case "$(uname -s)" in
        Linux*)
            if [[ -f /etc/os-release ]]; then
                . /etc/os-release
                OS=$ID
                VER=$VERSION_ID
            elif [[ -f /etc/redhat-release ]]; then
                OS="centos"
                VER=$(cat /etc/redhat-release | grep -oE '[0-9]+\\.[0-9]+' | head -1)
            elif [[ -f /etc/debian_version ]]; then
                OS="debian"
                VER=$(cat /etc/debian_version)
            else
                OS="linux"
                VER="unknown"
            fi
            ;;
        Darwin*)
            OS="macos"
            VER=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
            log_warning "检测到macOS系统，系统依赖需要手动安装"
            log_warning "请使用Homebrew安装依赖: brew install portaudio libsndfile fftw ffmpeg"
            return 0
            ;;
        *)
            OS="unknown"
            VER="unknown"
            log_warning "未知操作系统: $(uname -s)"
            log_warning "请手动安装系统依赖"
            return 0
            ;;
    esac
    
    log_info "检测到操作系统: $OS $VER"
}

# 安装Ubuntu/Debian依赖
install_ubuntu_deps() {
    log_info "安装Ubuntu/Debian系统依赖..."
    
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
        
    log_info "Ubuntu/Debian依赖安装完成"
}

# 安装CentOS/RHEL依赖
install_centos_deps() {
    log_info "安装CentOS/RHEL系统依赖..."
    
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
        
    log_info "CentOS/RHEL依赖安装完成"
}

# 主函数
main() {
    log_info "开始安装系统依赖..."
    
    if [[ "$(uname -s)" == "Linux" ]]; then
        check_root
    fi
    
    detect_os
    
    case "$OS" in
        ubuntu|debian)
            install_ubuntu_deps
            ;;
        centos|rhel|fedora|rocky|almalinux)
            install_centos_deps
            ;;
        *)
            log_warning "不支持的操作系统: $OS ($(uname -s))"
            log_warning "请手动安装系统依赖"
            ;;
    esac
    
    log_info "系统依赖处理完成！"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
'''
        
        script_path = scripts_dir / "install_system_deps.sh"
        with open(script_path, "w") as f:
            f.write(script_content)
        
        script_path.chmod(0o755)
    
    def _create_arch_manifest(self, arch_config: ArchitectureConfig, 
                             arch_work_dir: Path, packages_path: str,
                             os_config: OSConfig = None):
        """创建架构特定的清单文件"""
        platform, _ = self.detect_platform()
        
        # 计算包数量和大小
        packages_dir = Path(packages_path)
        if packages_dir.is_file() and packages_dir.suffix == ".gz":
            # 如果是tar.gz文件，解压计算
            with tarfile.open(packages_dir, "r:gz") as tar:
                package_count = len(tar.getnames())
                total_size = sum(member.size for member in tar.getmembers() if member.isfile())
        else:
            # 如果是目录，直接计算
            package_files = list(packages_dir.glob("*.whl")) + list(packages_dir.glob("*.tar.gz"))
            package_count = len(package_files)
            total_size = sum(f.stat().st_size for f in package_files)
        
        manifest = PackageManifest(
            version=self.version,
            created_at=datetime.datetime.now().isoformat(),
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
            platform=platform,
            architecture=arch_config.name,
            os_name=os_config.name if os_config else platform,
            os_version=os_config.version if os_config else "unknown",
            package_count=package_count,
            total_size=total_size,
            checksum="",  # 将在最终包创建后计算
            supported_architectures=[arch_config.name]
        )
        
        manifest_path = arch_work_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(asdict(manifest), f, indent=2)
    
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
                               os_name: str = None,
                               use_docker: bool = True,
                               create_individual: bool = True,
                               create_unified: bool = True) -> Dict[str, str]:
        """构建所有架构的离线包"""
        if architectures is None:
            architectures = list(self.architectures.keys())
        
        if os_name:
            logger.info(f"开始构建多架构离线包: {architectures}, 操作系统: {os_name}")
        else:
            logger.info(f"开始构建多架构离线包: {architectures}")
        
        # 存储构建结果
        individual_packages = {}
        arch_packages = {}
        
        if use_docker and self.check_docker_availability():
            # 使用线程池并行构建
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                future_to_arch = {
                    executor.submit(self.build_for_architecture, arch, os_name, True, create_individual): arch
                    for arch in architectures
                }
                
                for future in concurrent.futures.as_completed(future_to_arch):
                    arch = future_to_arch[future]
                    try:
                        package_path = future.result()
                        if create_individual:
                            individual_packages[arch] = package_path
                        arch_packages[arch] = package_path
                        logger.info(f"架构 {arch} 构建完成: {package_path}")
                    except Exception as e:
                        logger.error(f"架构 {arch} 构建失败: {e}")
        else:
            # 顺序构建
            for arch in architectures:
                try:
                    package_path = self.build_for_architecture(arch, os_name, False, create_individual)
                    if create_individual:
                        individual_packages[arch] = package_path
                    arch_packages[arch] = package_path
                    logger.info(f"架构 {arch} 构建完成: {package_path}")
                except Exception as e:
                    logger.error(f"架构 {arch} 构建失败: {e}")
        
        result = {"individual": individual_packages}
        
        # 创建统一的多架构包
        if create_unified and len(arch_packages) > 1:
            unified_package = self._create_unified_package(architectures, arch_packages)
            result["unified"] = unified_package
        
        return result
    
    def _create_unified_package(self, architectures: List[str], 
                               arch_packages: Dict[str, str]) -> str:
        """创建统一的多架构包"""
        logger.info("创建统一的多架构离线包...")
        
        # 创建统一包的工作目录
        unified_dir = self.output_dir / "unified"
        unified_dir.mkdir(exist_ok=True)
        
        # 复制所有架构的包到统一目录
        packages_dir = unified_dir / "packages"
        packages_dir.mkdir(exist_ok=True)
        
        for arch in architectures:
            arch_packages_dir = packages_dir / arch
            arch_packages_dir.mkdir(exist_ok=True)
            
            # 复制架构特定的Python包
            source_packages = self.output_dir / arch / "python_packages" / arch
            if source_packages.exists():
                shutil.copytree(source_packages, arch_packages_dir, dirs_exist_ok=True)
        
        # 创建统一安装器
        self.create_unified_installer(arch_packages)
        shutil.copy2(self.output_dir / "install_multi_arch.sh", unified_dir)
        
        # 复制应用文件
        self._copy_application_to_output_dir(unified_dir)
        
        # 创建requirements文件
        requirements = self.get_requirements()
        req_file = unified_dir / "requirements.txt"
        with open(req_file, "w") as f:
            for req in requirements:
                f.write(f"{req}\n")
        
        # 创建统一清单
        self._create_unified_manifest(architectures, unified_dir)
        
        # 检测平台
        platform, _ = self.detect_platform()
        
        # 创建最终的多架构包
        package_name = f"audio-processing-system-multi-arch-offline-{self.version}-{platform}.tar.gz"
        package_path = self.output_dir / package_name
        
        with tarfile.open(package_path, "w:gz") as tar:
            tar.add(unified_dir, arcname="audio-processing-system-multi-arch")
        
        # 计算校验和
        with open(package_path, "rb") as f:
            checksum = hashlib.sha256(f.read()).hexdigest()
        
        # 创建校验和文件
        checksum_file = package_path.with_suffix(package_path.suffix + ".sha256")
        with open(checksum_file, "w") as f:
            f.write(f"{checksum}  {package_name}\n")
        
        logger.info(f"统一多架构包创建完成: {package_path}")
        logger.info(f"包大小: {package_path.stat().st_size / 1024 / 1024:.1f} MB")
        logger.info(f"校验和: {checksum}")
        
        return str(package_path)
    
    def _copy_application_to_output_dir(self, output_dir: Path):
        """复制应用文件到指定输出目录"""
        # 复制源代码
        if Path("src").exists():
            shutil.copytree("src", output_dir / "src", dirs_exist_ok=True)
        
        # 复制配置文件
        if Path("config").exists():
            shutil.copytree("config", output_dir / "config", dirs_exist_ok=True)
        
        # 复制静态文件
        if Path("static").exists():
            shutil.copytree("static", output_dir / "static", dirs_exist_ok=True)
        
        # 复制重要文件
        important_files = ["README.md", "LICENSE", "pyproject.toml"]
        for file_name in important_files:
            file_path = Path(file_name)
            if file_path.exists():
                shutil.copy2(file_path, output_dir / file_name)
    
    def _create_unified_manifest(self, architectures: List[str], unified_dir: Path):
        """创建统一包的清单文件"""
        platform, _ = self.detect_platform()
        
        # 计算总的包数量和大小
        total_packages = 0
        total_size = 0
        
        packages_dir = unified_dir / "packages"
        for arch in architectures:
            arch_dir = packages_dir / arch
            if arch_dir.exists():
                package_files = list(arch_dir.glob("*.whl")) + list(arch_dir.glob("*.tar.gz"))
                total_packages += len(package_files)
                total_size += sum(f.stat().st_size for f in package_files)
        
        manifest = PackageManifest(
            version=self.version,
            created_at=datetime.datetime.now().isoformat(),
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
            platform=platform,
            architecture="multi-arch",
            package_count=total_packages,
            total_size=total_size,
            checksum="",  # 将在最终包创建后计算
            supported_architectures=architectures
        )
        
        manifest_path = unified_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(asdict(manifest), f, indent=2)
    
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
                       help="目标架构（默认：当前架构）")
    parser.add_argument("--os", choices=["ubuntu20", "ubuntu22", "ubuntu24", 
                                        "centos7", "centos8", "rocky8", "rocky9"],
                       help="目标操作系统（仅Docker构建时使用）")
    parser.add_argument("--docker", action="store_true",
                       help="使用Docker构建（支持跨平台）")
    parser.add_argument("--individual-only", action="store_true",
                       help="只创建单架构包，不创建统一包")
    parser.add_argument("--unified-only", action="store_true",
                       help="只创建统一多架构包，不创建单架构包")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    builder = MultiArchBuilder(args.output)
    
    # 确定目标架构
    if args.architectures:
        architectures = args.architectures
    else:
        # 默认使用当前架构
        _, current_arch = builder.detect_platform()
        architectures = [current_arch]
        logger.info(f"未指定架构，使用当前架构: {current_arch}")
    
    # 确定构建模式
    use_docker = args.docker
    if use_docker and not args.os:
        # Docker构建时默认使用Ubuntu 22.04
        args.os = "ubuntu22"
        logger.info("Docker构建模式，默认使用 Ubuntu 22.04")
    
    # 确定构建选项
    create_individual = not args.unified_only
    create_unified = not args.individual_only and len(architectures) > 1
    
    try:
        results = builder.build_all_architectures(
            architectures,
            args.os,
            use_docker,
            create_individual,
            create_unified
        )
        
        print(f"\n✓ 离线包构建完成！")
        print(f"构建模式: {'Docker' if use_docker else '本地'}")
        if args.os:
            print(f"目标系统: {args.os}")
        print(f"支持的架构: {', '.join(architectures)}")
        
        # 显示单架构包
        if "individual" in results and results["individual"]:
            print(f"\n单架构包:")
            for arch, package_path in results["individual"].items():
                package_name = Path(package_path).name
                package_size = Path(package_path).stat().st_size / 1024 / 1024
                print(f"  {arch}: {package_name} ({package_size:.1f} MB)")
        
        # 显示统一包
        if "unified" in results:
            unified_name = Path(results["unified"]).name
            unified_size = Path(results["unified"]).stat().st_size / 1024 / 1024
            print(f"\n统一多架构包: {unified_name} ({unified_size:.1f} MB)")
        
        print(f"\n使用方法:")
        if "individual" in results and results["individual"]:
            print("单架构包:")
            print("1. 选择对应架构的包传输到目标设备")
            print("2. 解压: tar -xzf audio-processing-system-offline-*.tar.gz")
            print("3. 安装: cd audio-processing-system-offline && sudo ./scripts/install_offline.sh")
        
        if "unified" in results:
            print("统一多架构包:")
            print("1. 将统一包传输到目标设备")
            print("2. 解压: tar -xzf audio-processing-system-multi-arch-offline-*.tar.gz")
            print("3. 安装: cd audio-processing-system-multi-arch && sudo ./install_multi_arch.sh")
        
    except Exception as e:
        logger.error(f"构建失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()