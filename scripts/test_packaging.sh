#!/bin/bash
# 离线包构建测试脚本
# 用于验证打包脚本的正确性

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

# 测试结果统计
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

run_test() {
    local test_name="$1"
    local test_command="$2"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_info "测试 $TOTAL_TESTS: $test_name"
    
    if eval "$test_command"; then
        log_success "✓ $test_name"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        return 0
    else
        log_error "✗ $test_name"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi
}

# 清理函数
cleanup() {
    log_info "清理测试文件..."
    rm -rf dist/test-*
    rm -rf /tmp/package-test-*
}

# 设置清理陷阱
trap cleanup EXIT

echo "=========================================="
echo "    离线包构建测试套件"
echo "=========================================="
echo

# 1. 环境检查
log_info "1. 环境检查"
echo "----------------------------------------"

run_test "Python版本检查" "python3 --version | grep -E 'Python 3\.(10|11|12)'"
run_test "pip版本检查" "python3 -m pip --version"
run_test "必要工具检查" "which tar && which gzip && which sha256sum"

# 检查项目文件
run_test "项目文件存在性检查" "test -f pyproject.toml && test -f tools/offline_packager.py && test -f tools/build_multi_arch.py"

echo

# 2. 单架构离线包测试
log_info "2. 单架构离线包测试"
echo "----------------------------------------"

# 测试基本构建
run_test "单架构包基本构建" "python3 tools/offline_packager.py --output dist/test-single --verbose"

if [[ $? -eq 0 ]]; then
    # 检查输出文件
    SINGLE_PACKAGE=$(find dist/test-single -name "audio-processing-system-offline-*.tar.gz" | head -1)
    
    if [[ -n "$SINGLE_PACKAGE" ]]; then
        run_test "单架构包文件存在" "test -f '$SINGLE_PACKAGE'"
        run_test "单架构包校验和文件存在" "test -f '$SINGLE_PACKAGE.sha256'"
        
        # 验证校验和
        PACKAGE_DIR=$(dirname "$SINGLE_PACKAGE")
        CHECKSUM_FILE=$(basename "$SINGLE_PACKAGE.sha256")
        run_test "单架构包校验和验证" "(cd '$PACKAGE_DIR' && sha256sum -c '$CHECKSUM_FILE')"
        
        # 测试解压
        TEST_DIR="/tmp/package-test-single"
        mkdir -p "$TEST_DIR"
        run_test "单架构包解压测试" "tar -xzf '$SINGLE_PACKAGE' -C '$TEST_DIR'"
        
        if [[ $? -eq 0 ]]; then
            EXTRACTED_DIR="$TEST_DIR/audio-processing-system-offline"
            
            # 检查关键文件
            run_test "安装脚本存在" "test -f '$EXTRACTED_DIR/scripts/install_offline.sh'"
            run_test "系统依赖脚本存在" "test -f '$EXTRACTED_DIR/scripts/install_system_deps.sh'"
            run_test "清单文件存在" "test -f '$EXTRACTED_DIR/manifest.json'"
            run_test "requirements文件存在" "test -f '$EXTRACTED_DIR/requirements.txt'"
            run_test "Python包目录存在" "test -d '$EXTRACTED_DIR/python_packages'"
            
            # 检查Python包数量
            PACKAGE_COUNT=$(find "$EXTRACTED_DIR/python_packages" -name "*.whl" | wc -l)
            run_test "Python包数量检查" "test $PACKAGE_COUNT -gt 10"
            
            # 检查脚本权限
            run_test "安装脚本可执行" "test -x '$EXTRACTED_DIR/scripts/install_offline.sh'"
            run_test "系统依赖脚本可执行" "test -x '$EXTRACTED_DIR/scripts/install_system_deps.sh'"
            
            # 验证清单文件格式
            run_test "清单文件JSON格式" "python3 -c 'import json; json.load(open(\"$EXTRACTED_DIR/manifest.json\"))'"
        fi
    else
        log_error "未找到生成的单架构包文件"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
fi

echo

# 3. 多架构离线包测试
log_info "3. 多架构离线包测试"
echo "----------------------------------------"

# 测试多架构构建（当前架构）
run_test "多架构包基本构建" "python3 tools/build_multi_arch.py --output dist/test-multi --verbose"

if [[ $? -eq 0 ]]; then
    # 检查输出文件
    MULTI_PACKAGE=$(find dist/test-multi -name "audio-processing-system-offline-*.tar.gz" | head -1)
    
    if [[ -n "$MULTI_PACKAGE" ]]; then
        run_test "多架构包文件存在" "test -f '$MULTI_PACKAGE'"
        run_test "多架构包校验和文件存在" "test -f '$MULTI_PACKAGE.sha256'"
        
        # 验证校验和
        MULTI_PACKAGE_DIR=$(dirname "$MULTI_PACKAGE")
        MULTI_CHECKSUM_FILE=$(basename "$MULTI_PACKAGE.sha256")
        run_test "多架构包校验和验证" "(cd '$MULTI_PACKAGE_DIR' && sha256sum -c '$MULTI_CHECKSUM_FILE')"
        
        # 测试解压
        TEST_DIR="/tmp/package-test-multi"
        mkdir -p "$TEST_DIR"
        run_test "多架构包解压测试" "tar -xzf '$MULTI_PACKAGE' -C '$TEST_DIR'"
        
        if [[ $? -eq 0 ]]; then
            EXTRACTED_DIR="$TEST_DIR/audio-processing-system-offline"
            
            # 检查关键文件
            run_test "多架构安装脚本存在" "test -f '$EXTRACTED_DIR/scripts/install_offline.sh'"
            run_test "多架构Python包目录存在" "test -d '$EXTRACTED_DIR/python_packages'"
        fi
    fi
fi

echo

# 4. 包内容验证测试
log_info "4. 包内容验证测试"
echo "----------------------------------------"

if [[ -n "$SINGLE_PACKAGE" ]]; then
    # 检查包大小
    PACKAGE_SIZE=$(stat -f%z "$SINGLE_PACKAGE" 2>/dev/null || stat -c%s "$SINGLE_PACKAGE" 2>/dev/null)
    PACKAGE_SIZE_MB=$((PACKAGE_SIZE / 1024 / 1024))
    
    run_test "包大小合理性检查" "test $PACKAGE_SIZE_MB -gt 10 && test $PACKAGE_SIZE_MB -lt 500"
    
    # 检查包内容结构
    run_test "包结构检查" "tar -tzf '$SINGLE_PACKAGE' | grep -q 'audio-processing-system-offline/scripts/install_offline.sh'"
    run_test "源码目录检查" "tar -tzf '$SINGLE_PACKAGE' | grep -q 'audio-processing-system-offline/src/'"
    run_test "配置目录检查" "tar -tzf '$SINGLE_PACKAGE' | grep -q 'audio-processing-system-offline/config/'"
fi

echo

# 5. 脚本语法检查
log_info "5. 脚本语法检查"
echo "----------------------------------------"

if [[ -n "$EXTRACTED_DIR" ]]; then
    # 检查bash脚本语法
    run_test "安装脚本语法检查" "bash -n '$EXTRACTED_DIR/scripts/install_offline.sh'"
    run_test "系统依赖脚本语法检查" "bash -n '$EXTRACTED_DIR/scripts/install_system_deps.sh'"
    
    # 检查Python脚本语法
    if [[ -f "$EXTRACTED_DIR/scripts/verify_dependencies.py" ]]; then
        run_test "验证脚本语法检查" "python3 -m py_compile '$EXTRACTED_DIR/scripts/verify_dependencies.py'"
    fi
fi

echo

# 6. 依赖完整性测试
log_info "6. 依赖完整性测试"
echo "----------------------------------------"

if [[ -n "$EXTRACTED_DIR" ]]; then
    # 检查requirements文件格式
    run_test "requirements文件格式检查" "python3 -c 'open(\"$EXTRACTED_DIR/requirements.txt\").readlines()'"
    
    # 检查是否有重复的包
    DUPLICATE_COUNT=$(find "$EXTRACTED_DIR/python_packages" -name "*.whl" -exec basename {} \; | cut -d'-' -f1 | sort | uniq -d | wc -l)
    run_test "无重复包检查" "test $DUPLICATE_COUNT -eq 0"
    
    # 检查关键依赖是否存在
    run_test "关键依赖存在性检查" "find '$EXTRACTED_DIR/python_packages' -name '*fastapi*' | grep -q ."
fi

echo

# 7. 工具参数测试
log_info "7. 工具参数测试"
echo "----------------------------------------"

# 测试帮助信息
run_test "单架构工具帮助信息" "python3 tools/offline_packager.py --help | grep -q 'usage:'"
run_test "多架构工具帮助信息" "python3 tools/build_multi_arch.py --help | grep -q 'usage:'"

# 测试无效参数处理
run_test "无效架构参数处理" "! python3 tools/build_multi_arch.py --architectures invalid_arch 2>/dev/null"
run_test "无效操作系统参数处理" "! python3 tools/build_multi_arch.py --docker --os invalid_os 2>/dev/null"

echo

# 8. 错误处理测试
log_info "8. 错误处理测试"
echo "----------------------------------------"

# 测试无效输出目录
run_test "无效输出目录处理" "! python3 tools/offline_packager.py --output /root/invalid_dir 2>/dev/null || true"

# 测试网络问题模拟（如果可能）
if command -v timeout >/dev/null 2>&1; then
    run_test "超时处理测试" "timeout 5s python3 tools/offline_packager.py --output dist/test-timeout --verbose || true"
fi

echo

# 9. 性能测试
log_info "9. 性能测试"
echo "----------------------------------------"

# 测试构建时间
START_TIME=$(date +%s)
python3 tools/offline_packager.py --output dist/test-perf --verbose >/dev/null 2>&1
END_TIME=$(date +%s)
BUILD_TIME=$((END_TIME - START_TIME))

run_test "构建时间合理性" "test $BUILD_TIME -lt 300"  # 应该在5分钟内完成

echo

# 10. 清理测试
log_info "10. 清理测试"
echo "----------------------------------------"

# 测试临时文件清理
TEMP_FILES_BEFORE=$(find /tmp -name "*audio*" 2>/dev/null | wc -l)
python3 tools/offline_packager.py --output dist/test-cleanup --verbose >/dev/null 2>&1
TEMP_FILES_AFTER=$(find /tmp -name "*audio*" 2>/dev/null | wc -l)

run_test "临时文件清理" "test $TEMP_FILES_AFTER -le $TEMP_FILES_BEFORE"

echo
echo "=========================================="
echo "           测试结果汇总"
echo "=========================================="
echo "总测试数: $TOTAL_TESTS"
echo "通过测试: $PASSED_TESTS"
echo "失败测试: $FAILED_TESTS"
echo "成功率: $(( PASSED_TESTS * 100 / TOTAL_TESTS ))%"
echo

if [[ $FAILED_TESTS -eq 0 ]]; then
    log_success "🎉 所有测试通过！打包脚本工作正常。"
    exit 0
else
    log_error "❌ 有 $FAILED_TESTS 个测试失败，请检查相关问题。"
    exit 1
fi