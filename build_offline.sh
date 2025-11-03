#!/bin/bash
# 音频处理系统离线包构建脚本
# Audio Processing System Offline Package Build Script

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

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 显示帮助信息
show_help() {
    echo "音频处理系统离线包构建脚本"
    echo
    echo "用法: $0 [选项]"
    echo
    echo "选项:"
    echo "  -h, --help              显示此帮助信息"
    echo "  -s, --single-arch       构建单架构包（当前架构）"
    echo "  -m, --multi-arch        构建多架构包（x86_64, aarch64）"
    echo "  -a, --arch ARCH         指定架构 (x86_64|aarch64|armv7l)"
    echo "  -o, --output DIR        输出目录 (默认: dist/)"
    echo "  --no-docker             不使用Docker构建"
    echo "  -v, --verbose           详细输出"
    echo
    echo "示例:"
    echo "  $0 -s                   构建当前架构的离线包"
    echo "  $0 -m                   构建多架构离线包"
    echo "  $0 -a x86_64 -o /tmp    构建x86_64架构包到/tmp目录"
}

# 检查依赖
check_dependencies() {
    log_info "检查构建依赖..."
    
    # 检查Python
    if ! command -v python3 &> /dev/null; then
        log_error "未找到Python3"
        exit 1
    fi
    
    # 检查pip
    if ! python3 -m pip --version &> /dev/null; then
        log_error "未找到pip"
        exit 1
    fi
    
    # 检查必要的Python包
    python3 -c "
import sys
try:
    import tomllib
except ImportError:
    try:
        import tomli
        print('使用tomli作为tomllib的替代')
    except ImportError:
        print('需要安装tomli: pip install tomli')
        sys.exit(1)
" || exit 1
    
    log_success "依赖检查通过"
}

# 准备构建环境
prepare_build_env() {
    log_info "准备构建环境..."
    
    # 创建输出目录
    mkdir -p "$OUTPUT_DIR"
    
    # 检查项目文件
    if [[ ! -f "pyproject.toml" ]]; then
        log_error "未找到pyproject.toml，请在项目根目录运行此脚本"
        exit 1
    fi
    
    if [[ ! -f "requirements-offline.txt" ]]; then
        log_warning "未找到requirements-offline.txt，将从pyproject.toml生成"
        # 这里可以添加从pyproject.toml提取依赖的逻辑
    fi
    
    log_success "构建环境准备完成"
}

# 构建单架构包
build_single_arch() {
    log_info "构建单架构离线包..."
    
    local arch_arg=""
    if [[ -n "$ARCH" ]]; then
        arch_arg="--architectures $ARCH"
    fi
    
    local docker_arg=""
    if [[ "$NO_DOCKER" == "true" ]]; then
        docker_arg="--no-docker"
    fi
    
    local verbose_arg=""
    if [[ "$VERBOSE" == "true" ]]; then
        verbose_arg="--verbose"
    fi
    
    python3 tools/offline_packager.py \
        --output "$OUTPUT_DIR/single-arch" \
        $arch_arg \
        $verbose_arg
    
    log_success "单架构包构建完成"
}

# 构建多架构包
build_multi_arch() {
    log_info "构建多架构离线包..."
    
    local arch_arg="--architectures x86_64 aarch64"
    if [[ -n "$ARCH" ]]; then
        arch_arg="--architectures $ARCH"
    fi
    
    local docker_arg=""
    if [[ "$NO_DOCKER" == "true" ]]; then
        docker_arg="--no-docker"
    fi
    
    local verbose_arg=""
    if [[ "$VERBOSE" == "true" ]]; then
        verbose_arg="--verbose"
    fi
    
    python3 tools/build_multi_arch.py \
        --output "$OUTPUT_DIR/multi-arch" \
        $arch_arg \
        $docker_arg \
        $verbose_arg
    
    log_success "多架构包构建完成"
}

# 显示构建结果
show_results() {
    log_info "构建结果:"
    echo
    
    if [[ -d "$OUTPUT_DIR" ]]; then
        find "$OUTPUT_DIR" -name "*.tar.gz" -type f | while read -r file; do
            size=$(du -h "$file" | cut -f1)
            echo "  📦 $(basename "$file") ($size)"
        done
    fi
    
    echo
    log_info "使用说明:"
    echo "1. 将离线包传输到目标设备"
    echo "2. 解压离线包"
    echo "3. 运行安装脚本"
    echo
    echo "详细说明请参考 deploy/README.md"
}

# 默认参数
BUILD_TYPE=""
ARCH=""
OUTPUT_DIR="dist"
NO_DOCKER="false"
VERBOSE="false"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -s|--single-arch)
            BUILD_TYPE="single"
            shift
            ;;
        -m|--multi-arch)
            BUILD_TYPE="multi"
            shift
            ;;
        -a|--arch)
            ARCH="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --no-docker)
            NO_DOCKER="true"
            shift
            ;;
        -v|--verbose)
            VERBOSE="true"
            shift
            ;;
        *)
            log_error "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
done

# 如果没有指定构建类型，询问用户
if [[ -z "$BUILD_TYPE" ]]; then
    echo "请选择构建类型:"
    echo "1) 单架构包（当前架构）"
    echo "2) 多架构包（x86_64 + aarch64）"
    read -p "请输入选择 (1-2): " choice
    
    case $choice in
        1)
            BUILD_TYPE="single"
            ;;
        2)
            BUILD_TYPE="multi"
            ;;
        *)
            log_error "无效选择"
            exit 1
            ;;
    esac
fi

# 主构建流程
main() {
    echo "=========================================="
    echo "    音频处理系统离线包构建工具"
    echo "=========================================="
    echo
    
    check_dependencies
    prepare_build_env
    
    case "$BUILD_TYPE" in
        single)
            build_single_arch
            ;;
        multi)
            build_multi_arch
            ;;
        *)
            log_error "未知构建类型: $BUILD_TYPE"
            exit 1
            ;;
    esac
    
    show_results
    
    echo
    log_success "离线包构建完成！"
}

# 错误处理
trap 'log_error "构建过程中发生错误"; exit 1' ERR

# 运行主程序
main "$@"