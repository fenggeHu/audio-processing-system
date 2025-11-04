#!/usr/bin/env python3
"""
离线依赖包构建工具
Offline Dependency Package Builder

用于创建包含所有Python和系统依赖的离线安装包，支持无网络环境的部署。
"""

import sys
import json
import shutil
import subprocess
import tempfile
import tarfile
import hashlib
from pathlib import Path
from typing import List, Tuple
import argparse
import logging
from dataclasses import dataclass, asdict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class PackageInfo:
    """包信息数据类"""
    name: str
    version: str
    size: int
    checksum: str
    dependencies: List[str]
    architecture: str = "any"
    
@dataclass
class OfflinePackageManifest:
    """离线包清单"""
    version: str
    created_at: str
    python_version: str
    platform: str
    architecture: str
    packages: List[PackageInfo]
    system_dependencies: List[str]
    total_size: int
    checksum: str

class OfflinePackager:
    """离线依赖包构建器"""
    
    def __init__(self, output_dir: str = "dist/offline"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 临时工作目录
        self.work_dir = Path(tempfile.mkdtemp(prefix="audio_offline_"))
        self.python_packages_dir = self.work_dir / "python_packages"
        self.system_packages_dir = self.work_dir / "system_packages"
        self.scripts_dir = self.work_dir / "scripts"
        
        # 创建工作目录结构
        self.python_packages_dir.mkdir(parents=True)
        self.system_packages_dir.mkdir(parents=True)
        self.scripts_dir.mkdir(parents=True)
        
        # 支持的架构
        self.supported_architectures = ["x86_64", "aarch64", "armv7l"]
        
        logger.info(f"工作目录: {self.work_dir}")
        logger.info(f"输出目录: {self.output_dir}")
    
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
                
            # 开发依赖（可选）
            if "project" in data and "optional-dependencies" in data["project"]:
                for group, deps in data["project"]["optional-dependencies"].items():
                    if group == "dev":  # 只包含开发依赖
                        requirements.extend(deps)
        
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
    
    def download_python_packages(self, requirements: List[str], 
                                architecture: str = None) -> List[PackageInfo]:
        """下载Python包到离线目录"""
        logger.info("开始下载Python依赖包...")
        
        if architecture is None:
            _, architecture = self.detect_platform()
        
        # 创建架构特定的目录
        arch_dir = self.python_packages_dir / architecture
        arch_dir.mkdir(exist_ok=True)
        
        # 创建requirements文件
        req_file = self.work_dir / "requirements.txt"
        with open(req_file, "w") as f:
            for req in requirements:
                f.write(f"{req}\n")
        
        # 智能下载策略：多种方案确保成功率
        logger.info("开始下载Python包...")
        
        download_success = False
        successful_packages = []
        failed_packages = []
        
        # 策略1：尝试简单下载（适用于当前平台）
        logger.info("策略1：标准下载...")
        cmd_simple = [
            sys.executable, "-m", "pip", "download",
            "--requirement", str(req_file),
            "--dest", str(arch_dir),
            "--prefer-binary"
        ]
        
        try:
            result = subprocess.run(cmd_simple, capture_output=True, text=True, check=True)
            logger.info("标准下载成功")
            download_success = True
        except subprocess.CalledProcessError as e:
            logger.info("标准下载失败，尝试逐个下载...")
            
            # 策略2：逐个下载包，使用多种回退方案
            for req in requirements:
                package_downloaded = False
                package_name = req.split('>=')[0].split('==')[0].split('<')[0].split('>')[0].strip()
                
                # 尝试1：下载指定版本
                try:
                    cmd_versioned = [
                        sys.executable, "-m", "pip", "download",
                        req,
                        "--dest", str(arch_dir),
                        "--prefer-binary"
                    ]
                    subprocess.run(cmd_versioned, capture_output=True, text=True, check=True)
                    successful_packages.append(req)
                    package_downloaded = True
                    logger.debug(f"✓ 下载成功: {req}")
                except subprocess.CalledProcessError:
                    pass
                
                # 尝试2：下载最新版本（不指定版本约束）
                if not package_downloaded:
                    try:
                        cmd_latest = [
                            sys.executable, "-m", "pip", "download",
                            package_name,
                            "--dest", str(arch_dir),
                            "--prefer-binary"
                        ]
                        subprocess.run(cmd_latest, capture_output=True, text=True, check=True)
                        successful_packages.append(package_name)
                        package_downloaded = True
                        logger.debug(f"✓ 下载最新版本: {package_name}")
                    except subprocess.CalledProcessError:
                        pass
                
                # 尝试3：允许源码包
                if not package_downloaded:
                    try:
                        cmd_source = [
                            sys.executable, "-m", "pip", "download",
                            package_name,
                            "--dest", str(arch_dir),
                            "--no-binary", ":all:"
                        ]
                        subprocess.run(cmd_source, capture_output=True, text=True, check=True)
                        successful_packages.append(package_name)
                        package_downloaded = True
                        logger.debug(f"✓ 下载源码包: {package_name}")
                    except subprocess.CalledProcessError:
                        pass
                
                if not package_downloaded:
                    failed_packages.append(req)
                    logger.debug(f"✗ 无法下载: {req}")
            
            download_success = len(successful_packages) > 0
        
        # 报告下载结果
        if download_success:
            logger.info(f"成功下载 {len(successful_packages)} 个包")
            if failed_packages:
                logger.warning(f"无法下载 {len(failed_packages)} 个包: {failed_packages}")
                logger.warning("这些包可能需要在目标系统上手动安装或使用pip在线安装")
        else:
            logger.error("所有下载方案都失败了")
            raise RuntimeError("无法下载任何Python包")
        
        logger.info("Python包下载完成")
        
        # 分析下载的包
        packages = []
        for package_file in arch_dir.glob("*.whl"):
            info = self._analyze_package(package_file)
            packages.append(info)
        
        for package_file in arch_dir.glob("*.tar.gz"):
            info = self._analyze_package(package_file)
            packages.append(info)
        
        logger.info(f"共下载 {len(packages)} 个Python包")
        return packages
    
    def _get_pip_platform(self, architecture: str) -> str:
        """获取pip平台标识符"""
        import platform
        
        system = platform.system().lower()
        
        # 根据系统和架构生成平台标识符
        if system == "linux":
            platform_mapping = {
                "x86_64": "linux_x86_64",
                "aarch64": "linux_aarch64", 
                "armv7l": "linux_armv7l"
            }
            return platform_mapping.get(architecture, f"linux_{architecture}")
        elif system == "darwin":
            # macOS平台
            platform_mapping = {
                "x86_64": "macosx_10_9_x86_64",
                "aarch64": "macosx_11_0_arm64",
                "arm64": "macosx_11_0_arm64"
            }
            return platform_mapping.get(architecture, f"macosx_11_0_{architecture}")
        elif system == "windows":
            platform_mapping = {
                "x86_64": "win_amd64",
                "amd64": "win_amd64",
                "i386": "win32"
            }
            return platform_mapping.get(architecture, "win_amd64")
        else:
            return "any"
    
    def _analyze_package(self, package_path: Path) -> PackageInfo:
        """分析包信息"""
        stat = package_path.stat()
        
        # 计算校验和
        with open(package_path, "rb") as f:
            checksum = hashlib.sha256(f.read()).hexdigest()
        
        # 解析包名和版本
        name = package_path.stem
        if package_path.suffix == ".whl":
            # wheel格式: name-version-python-abi-platform.whl
            parts = name.split("-")
            pkg_name = parts[0]
            version = parts[1] if len(parts) > 1 else "unknown"
        else:
            # tar.gz格式: name-version.tar.gz
            if "-" in name:
                pkg_name, version = name.rsplit("-", 1)
            else:
                pkg_name = name
                version = "unknown"
        
        return PackageInfo(
            name=pkg_name,
            version=version,
            size=stat.st_size,
            checksum=checksum,
            dependencies=[],  # 暂时为空，需要进一步分析
            architecture="any"
        )
    
    def create_system_dependencies_script(self) -> str:
        """创建系统依赖安装脚本"""
        logger.info("创建系统依赖安装脚本...")
        
        # 定义不同系统的依赖包
        system_deps = {
            "ubuntu": [
                "python3-dev",
                "portaudio19-dev", 
                "libasound2-dev",
                "libsndfile1-dev",
                "libfftw3-dev",
                "ffmpeg",
                "gcc",
                "g++",
                "make",
                "pkg-config",
                "curl",
                "wget"
            ],
            "centos": [
                "python3-devel",
                "portaudio-devel",
                "alsa-lib-devel", 
                "libsndfile-devel",
                "fftw-devel",
                "ffmpeg",
                "gcc",
                "gcc-c++",
                "make",
                "pkgconfig",
                "curl",
                "wget"
            ]
        }
        
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
    # 检测操作系统类型
    case "$(uname -s)" in
        Linux*)
            # Linux系统，进一步检测发行版
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
        CYGWIN*|MINGW*|MSYS*)
            OS="windows"
            VER="unknown"
            log_warning "检测到Windows系统，系统依赖需要手动安装"
            log_warning "请参考文档安装相应的开发工具和库"
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
    
    # 对于非Linux系统，不需要root权限检查
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
        macos)
            log_info "macOS系统依赖安装指南："
            log_info "1. 安装Homebrew (如果尚未安装):"
            log_info "   /bin/bash -c \\"\\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\\""
            log_info "2. 安装系统依赖:"
            log_info "   brew install portaudio libsndfile fftw ffmpeg python@3.10"
            log_info "3. 安装开发工具:"
            log_info "   xcode-select --install"
            log_info ""
            log_info "系统依赖安装指南已显示，请手动执行上述命令"
            ;;
        windows)
            log_info "Windows系统依赖安装指南："
            log_info "1. 安装Visual Studio Build Tools"
            log_info "2. 安装Python开发环境"
            log_info "3. 参考项目文档安装音频处理库"
            log_info ""
            log_info "系统依赖安装指南已显示，请参考文档手动安装"
            ;;
        *)
            log_warning "不支持的操作系统: $OS ($(uname -s))"
            log_warning "请手动安装以下依赖包："
            log_warning "- Python开发包 (python3-dev/python3-devel)"
            log_warning "- PortAudio开发包 (portaudio19-dev/portaudio-devel)"
            log_warning "- ALSA开发包 (libasound2-dev/alsa-lib-devel)"
            log_warning "- libsndfile开发包 (libsndfile1-dev/libsndfile-devel)"
            log_warning "- FFTW开发包 (libfftw3-dev/fftw-devel)"
            log_warning "- FFmpeg (ffmpeg)"
            log_warning "- 编译工具 (gcc, g++, make)"
            ;;
    esac
    
    log_info "系统依赖处理完成！"
}

# 如果直接运行此脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
'''
        
        script_path = self.scripts_dir / "install_system_deps.sh"
        with open(script_path, "w") as f:
            f.write(script_content)
        
        # 设置执行权限
        script_path.chmod(0o755)
        
        return str(script_path)
    
    def create_offline_installer(self) -> str:
        """创建离线安装器脚本"""
        logger.info("创建离线安装器...")
        
        installer_content = '''#!/bin/bash
# 音频处理系统离线安装器
# Audio Processing System Offline Installer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 根据操作系统设置安装目录
case "$(uname -s)" in
    Darwin*)
        INSTALL_DIR="/usr/local/audio-processing-system"
        ;;
    *)
        INSTALL_DIR="/opt/audio-processing-system"
        ;;
esac

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

# 检查权限
check_permissions() {
    # 检测操作系统
    case "$(uname -s)" in
        Darwin*)
            # macOS系统，不强制要求root权限
            if [[ $EUID -eq 0 ]]; then
                log_warning "检测到root权限，建议使用普通用户运行"
                log_warning "macOS系统通常不需要root权限进行安装"
            fi
            ;;
        Linux*)
            # Linux系统，需要root权限
            if [[ $EUID -ne 0 ]]; then
                log_error "Linux系统需要root权限，请使用sudo运行此脚本"
                exit 1
            fi
            ;;
        *)
            # 其他系统，给出提示但不强制退出
            if [[ $EUID -ne 0 ]]; then
                log_warning "当前不是root用户，某些操作可能需要管理员权限"
            fi
            ;;
    esac
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
            exit 1
            ;;
    esac
    
    log_info "检测到架构: $ARCH"
}

# 安装系统依赖
install_system_dependencies() {
    log_info "安装系统依赖..."
    
    # 检测操作系统类型
    case "$(uname -s)" in
        Darwin*)
            log_info "检测到macOS系统"
            log_warning "macOS系统依赖需要手动安装，跳过自动安装步骤"
            log_info "请参考以下命令手动安装依赖："
            log_info "1. 安装Homebrew: /bin/bash -c \\"\\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\\""
            log_info "2. 安装依赖: brew install portaudio libsndfile fftw ffmpeg python@3.10"
            log_info "3. 安装开发工具: xcode-select --install"
            return 0
            ;;
        CYGWIN*|MINGW*|MSYS*)
            log_info "检测到Windows系统"
            log_warning "Windows系统依赖需要手动安装，跳过自动安装步骤"
            log_info "请参考项目文档安装相应的开发工具和库"
            return 0
            ;;
    esac
    
    # Linux系统继续原有逻辑
    # 查找系统依赖安装脚本
    SYSTEM_DEPS_SCRIPT=""
    
    # 可能的脚本位置
    POSSIBLE_PATHS=(
        "$SCRIPT_DIR/scripts/install_system_deps.sh"
        "$SCRIPT_DIR/install_system_deps.sh"
        "$(dirname "$0")/install_system_deps.sh"
        "./scripts/install_system_deps.sh"
        "./install_system_deps.sh"
    )
    
    for path in "${POSSIBLE_PATHS[@]}"; do
        if [[ -f "$path" ]]; then
            SYSTEM_DEPS_SCRIPT="$path"
            break
        fi
    done
    
    if [[ -n "$SYSTEM_DEPS_SCRIPT" ]]; then
        log_info "找到系统依赖安装脚本: $SYSTEM_DEPS_SCRIPT"
        bash "$SYSTEM_DEPS_SCRIPT"
    else
        log_warning "未找到系统依赖安装脚本，请手动安装以下依赖："
        log_warning "Ubuntu/Debian: sudo apt-get install python3-dev portaudio19-dev libasound2-dev libsndfile1-dev libfftw3-dev ffmpeg gcc g++ make pkg-config"
        log_warning "CentOS/RHEL: sudo yum install python3-devel portaudio-devel alsa-lib-devel libsndfile-devel fftw-devel ffmpeg gcc gcc-c++ make pkgconfig"
    fi
}

# 创建目录结构
create_directories() {
    log_info "创建目录结构..."
    
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"/{config,logs,recordings,plugins,backups}
    
    # 根据操作系统创建不同的数据目录
    case "$(uname -s)" in
        Darwin*)
            # macOS使用用户目录
            mkdir -p "$HOME/Library/Application Support/audio-processing"
            mkdir -p "/tmp/audio-processing"
            DATA_DIR="$HOME/Library/Application Support/audio-processing"
            RUN_DIR="/tmp/audio-processing"
            ;;
        *)
            # Linux使用系统目录
            mkdir -p /var/lib/audio-processing
            mkdir -p /var/run/audio-processing
            DATA_DIR="/var/lib/audio-processing"
            RUN_DIR="/var/run/audio-processing"
            ;;
    esac
    
    # 设置权限
    if [[ "$(uname -s)" == "Linux" ]] && [[ $EUID -eq 0 ]]; then
        chown -R "$USER_NAME:$USER_NAME" "$INSTALL_DIR"
        chown -R "$USER_NAME:$USER_NAME" "$DATA_DIR"
        chown -R "$USER_NAME:$USER_NAME" "$RUN_DIR"
    else
        # 非Linux系统或非root用户，使用当前用户权限
        chmod -R 755 "$INSTALL_DIR"
    fi
}

# 安装Python环境
install_python_environment() {
    log_info "创建Python虚拟环境..."
    
    cd "$INSTALL_DIR"
    
    # 根据系统和权限情况创建虚拟环境
    if [[ "$(uname -s)" == "Linux" ]] && [[ $EUID -eq 0 ]]; then
        sudo -u "$USER_NAME" python3 -m venv venv
    else
        python3 -m venv venv
    fi
    
    # 激活虚拟环境并安装离线包
    source venv/bin/activate
    
    log_info "升级pip和基础工具..."
    pip install --upgrade pip setuptools wheel
    
    log_info "安装Python离线包..."
    
    # 查找Python包目录
    PYTHON_PACKAGES_DIR=""
    POSSIBLE_PACKAGE_DIRS=(
        "$SCRIPT_DIR/python_packages/$ARCH"
        "$SCRIPT_DIR/python_packages"
        "$(dirname "$0")/python_packages/$ARCH"
        "$(dirname "$0")/python_packages"
        "./python_packages/$ARCH"
        "./python_packages"
    )
    
    for dir in "${POSSIBLE_PACKAGE_DIRS[@]}"; do
        if [[ -d "$dir" ]]; then
            PYTHON_PACKAGES_DIR="$dir"
            break
        fi
    done
    
    if [[ -n "$PYTHON_PACKAGES_DIR" ]]; then
        log_info "找到Python包目录: $PYTHON_PACKAGES_DIR"
        
        # 查找requirements文件
        REQUIREMENTS_FILE=""
        POSSIBLE_REQ_FILES=(
            "$SCRIPT_DIR/requirements.txt"
            "$(dirname "$0")/requirements.txt"
            "./requirements.txt"
        )
        
        for req_file in "${POSSIBLE_REQ_FILES[@]}"; do
            if [[ -f "$req_file" ]]; then
                REQUIREMENTS_FILE="$req_file"
                break
            fi
        done
        
        if [[ -n "$REQUIREMENTS_FILE" ]]; then
            log_info "使用requirements文件: $REQUIREMENTS_FILE"
            pip install --no-index --find-links "$PYTHON_PACKAGES_DIR" \\
                --requirement "$REQUIREMENTS_FILE"
        else
            log_info "未找到requirements文件，安装目录中的所有包..."
            pip install --no-index --find-links "$PYTHON_PACKAGES_DIR" \\
                "$PYTHON_PACKAGES_DIR"/*.whl "$PYTHON_PACKAGES_DIR"/*.tar.gz 2>/dev/null || true
        fi
    else
        log_error "未找到架构 $ARCH 的Python包目录"
        log_error "可能的目录位置:"
        for dir in "${POSSIBLE_PACKAGE_DIRS[@]}"; do
            log_error "  - $dir"
        done
        exit 1
    fi
}

# 复制应用文件
copy_application() {
    log_info "复制应用文件..."
    
    if [[ -d "$SCRIPT_DIR/src" ]]; then
        cp -r "$SCRIPT_DIR/src" "$INSTALL_DIR/"
    fi
    
    if [[ -d "$SCRIPT_DIR/config" ]]; then
        cp -r "$SCRIPT_DIR/config" "$INSTALL_DIR/"
    fi
    
    if [[ -d "$SCRIPT_DIR/static" ]]; then
        cp -r "$SCRIPT_DIR/static" "$INSTALL_DIR/"
    fi
    
    # 设置权限
    chown -R "$USER_NAME:$USER_NAME" "$INSTALL_DIR"
}

# 配置系统服务
configure_services() {
    log_info "配置系统服务..."
    
    case "$(uname -s)" in
        Darwin*)
            log_info "macOS系统，跳过systemd服务配置"
            log_info "可以手动启动服务："
            log_info "cd $INSTALL_DIR && source venv/bin/activate && python3 src/main.py"
            ;;
        Linux*)
            # 复制服务配置文件
            if [[ -f "$SCRIPT_DIR/systemd/audio-processing.service" ]]; then
                cp "$SCRIPT_DIR/systemd/audio-processing.service" /etc/systemd/system/
                systemctl daemon-reload
                systemctl enable audio-processing
                log_info "systemd服务已配置"
            else
                log_warning "未找到systemd服务配置文件"
            fi
            ;;
        *)
            log_info "非Linux系统，跳过systemd服务配置"
            ;;
    esac
}

# 验证安装
verify_installation() {
    log_info "验证安装..."
    
    cd "$INSTALL_DIR"
    source venv/bin/activate
    
    # 测试导入
    python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    import audio_processing
    print('✓ 核心模块导入成功')
except ImportError as e:
    print(f'✗ 核心模块导入失败: {e}')
    sys.exit(1)
"
    
    log_success "安装验证通过"
}

# 主安装流程
main() {
    echo "=========================================="
    echo "    音频处理系统离线安装器 v1.0"
    echo "=========================================="
    echo
    
    check_permissions
    detect_architecture
    install_system_dependencies
    create_directories
    install_python_environment
    copy_application
    configure_services
    verify_installation
    
    echo
    log_success "离线安装完成！"
    echo
    echo "安装目录: $INSTALL_DIR"
    echo "启动服务: systemctl start audio-processing"
    echo "Web界面: http://localhost"
}

main "$@"
'''
        
        installer_path = self.scripts_dir / "install_offline.sh"
        with open(installer_path, "w") as f:
            f.write(installer_content)
        
        installer_path.chmod(0o755)
        
        return str(installer_path)
    
    def create_dependency_verification(self) -> str:
        """创建依赖完整性验证脚本"""
        logger.info("创建依赖验证脚本...")
        
        verifier_content = '''#!/usr/bin/env python3
"""
依赖完整性验证工具
Dependency Integrity Verifier
"""

import json
import hashlib
import sys
from pathlib import Path

def verify_manifest(manifest_path: str) -> bool:
    """验证清单文件完整性"""
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        
        print(f"验证离线包: {manifest['version']}")
        print(f"创建时间: {manifest['created_at']}")
        print(f"Python版本: {manifest['python_version']}")
        print(f"平台: {manifest['platform']}")
        print(f"架构: {manifest['architecture']}")
        print(f"包数量: {len(manifest['packages'])}")
        print(f"总大小: {manifest['total_size'] / 1024 / 1024:.1f} MB")
        
        # 验证每个包的校验和
        base_dir = Path(manifest_path).parent
        failed_packages = []
        
        for pkg in manifest['packages']:
            pkg_path = base_dir / "python_packages" / manifest['architecture'] / f"{pkg['name']}-{pkg['version']}"
            
            # 尝试不同的文件扩展名
            for ext in ['.whl', '.tar.gz']:
                full_path = Path(str(pkg_path) + ext)
                if full_path.exists():
                    with open(full_path, 'rb') as f:
                        actual_checksum = hashlib.sha256(f.read()).hexdigest()
                    
                    if actual_checksum != pkg['checksum']:
                        failed_packages.append(pkg['name'])
                        print(f"✗ {pkg['name']}: 校验和不匹配")
                    else:
                        print(f"✓ {pkg['name']}: 校验和正确")
                    break
            else:
                failed_packages.append(pkg['name'])
                print(f"✗ {pkg['name']}: 文件未找到")
        
        if failed_packages:
            print(f"\\n验证失败，{len(failed_packages)} 个包有问题:")
            for pkg in failed_packages:
                print(f"  - {pkg}")
            return False
        else:
            print(f"\\n✓ 所有 {len(manifest['packages'])} 个包验证通过")
            return True
            
    except Exception as e:
        print(f"验证过程中发生错误: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python3 verify_dependencies.py <manifest.json>")
        sys.exit(1)
    
    manifest_path = sys.argv[1]
    if verify_manifest(manifest_path):
        print("\\n依赖包完整性验证通过！")
        sys.exit(0)
    else:
        print("\\n依赖包完整性验证失败！")
        sys.exit(1)
'''
        
        verifier_path = self.scripts_dir / "verify_dependencies.py"
        with open(verifier_path, "w") as f:
            f.write(verifier_content)
        
        verifier_path.chmod(0o755)
        
        return str(verifier_path)
    
    def create_manifest(self, packages: List[PackageInfo], 
                       system_deps: List[str]) -> OfflinePackageManifest:
        """创建离线包清单"""
        import datetime
        
        platform, architecture = self.detect_platform()
        
        total_size = sum(pkg.size for pkg in packages)
        
        # 计算整体校验和
        manifest_data = {
            "packages": [asdict(pkg) for pkg in packages],
            "system_dependencies": system_deps,
            "total_size": total_size
        }
        
        manifest_str = json.dumps(manifest_data, sort_keys=True)
        checksum = hashlib.sha256(manifest_str.encode()).hexdigest()
        
        return OfflinePackageManifest(
            version="1.0.0",
            created_at=datetime.datetime.now().isoformat(),
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
            platform=platform,
            architecture=architecture,
            packages=packages,
            system_dependencies=system_deps,
            total_size=total_size,
            checksum=checksum
        )
    
    def build_offline_package(self, architectures: List[str] = None) -> str:
        """构建完整的离线包"""
        if architectures is None:
            _, current_arch = self.detect_platform()
            architectures = [current_arch]
        
        logger.info(f"开始构建离线包，目标架构: {architectures}")
        
        try:
            # 获取依赖列表
            requirements = self.get_requirements()
            logger.info(f"找到 {len(requirements)} 个Python依赖")
            
            all_packages = []
            
            # 为每个架构下载包
            for arch in architectures:
                logger.info(f"处理架构: {arch}")
                packages = self.download_python_packages(requirements, arch)
                all_packages.extend(packages)
            
            # 创建系统依赖脚本
            self.create_system_dependencies_script()
            
            # 创建离线安装器
            self.create_offline_installer()
            
            # 创建验证脚本
            self.create_dependency_verification()
            
            # 复制应用源码
            self._copy_application_files()
            
            # 创建清单
            system_deps = ["python3-dev", "portaudio19-dev", "libasound2-dev", 
                          "libsndfile1-dev", "ffmpeg", "gcc", "g++"]
            manifest = self.create_manifest(all_packages, system_deps)
            
            # 保存清单
            manifest_path = self.work_dir / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(asdict(manifest), f, indent=2)
            
            # 复制requirements文件
            req_file = self.work_dir / "requirements.txt"
            with open(req_file, "w") as f:
                for req in requirements:
                    f.write(f"{req}\n")
            
            # 创建最终的tar包
            package_name = f"audio-processing-system-offline-{manifest.version}-{manifest.platform}-{manifest.architecture}.tar.gz"
            package_path = self.output_dir / package_name
            
            with tarfile.open(package_path, "w:gz") as tar:
                tar.add(self.work_dir, arcname="audio-processing-system-offline")
            
            # 计算最终包的校验和
            with open(package_path, "rb") as f:
                final_checksum = hashlib.sha256(f.read()).hexdigest()
            
            # 创建校验和文件
            checksum_file = package_path.with_suffix(package_path.suffix + ".sha256")
            with open(checksum_file, "w") as f:
                f.write(f"{final_checksum}  {package_name}\n")
            
            logger.info(f"离线包构建完成: {package_path}")
            logger.info(f"包大小: {package_path.stat().st_size / 1024 / 1024:.1f} MB")
            logger.info(f"校验和: {final_checksum}")
            
            return str(package_path)
            
        finally:
            # 清理临时目录
            shutil.rmtree(self.work_dir, ignore_errors=True)
    
    def _copy_application_files(self):
        """复制应用程序文件到工作目录"""
        logger.info("复制应用程序文件...")
        
        # 复制源代码
        if Path("src").exists():
            shutil.copytree("src", self.work_dir / "src")
        
        # 复制配置文件
        if Path("config").exists():
            shutil.copytree("config", self.work_dir / "config")
        
        # 复制静态文件
        if Path("static").exists():
            shutil.copytree("static", self.work_dir / "static")
        
        # 复制文档
        if Path("docs").exists():
            shutil.copytree("docs", self.work_dir / "docs")
        
        # 复制重要文件
        important_files = ["README.md", "LICENSE", "pyproject.toml"]
        for file_name in important_files:
            file_path = Path(file_name)
            if file_path.exists():
                shutil.copy2(file_path, self.work_dir / file_name)

def main():
    parser = argparse.ArgumentParser(description="音频处理系统离线依赖包构建工具")
    parser.add_argument("--output", "-o", default="dist/offline", 
                       help="输出目录 (默认: dist/offline)")
    parser.add_argument("--architectures", "-a", nargs="+", 
                       choices=["x86_64", "aarch64", "armv7l"],
                       help="目标架构 (默认: 当前架构)")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    packager = OfflinePackager(args.output)
    
    # 如果未指定架构，使用当前架构
    if not args.architectures:
        _, current_arch = packager.detect_platform()
        args.architectures = [current_arch]
        logger.info(f"未指定架构，使用当前架构: {current_arch}")
    
    try:
        package_path = packager.build_offline_package(args.architectures)
        print(f"\n✓ 离线包构建成功: {package_path}")
        
        # 显示包信息
        package_size = Path(package_path).stat().st_size / 1024 / 1024
        print(f"包大小: {package_size:.1f} MB")
        print(f"支持架构: {', '.join(args.architectures)}")
        
        print("\n使用方法:")
        print(f"1. 将 {Path(package_path).name} 传输到目标设备")
        print("2. 解压: tar -xzf audio-processing-system-offline-*.tar.gz")
        print("3. 安装: cd audio-processing-system-offline && sudo ./scripts/install_offline.sh")
        
    except Exception as e:
        logger.error(f"构建失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()