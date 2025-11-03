#!/bin/bash
# 便携式安装器构建脚本
# Portable Installer Build Script

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
    echo "便携式安装器构建脚本"
    echo
    echo "用法: $0 [选项] [离线包路径]"
    echo
    echo "选项:"
    echo "  -h, --help              显示此帮助信息"
    echo "  -o, --output DIR        输出目录 (默认: dist/portable)"
    echo "  -n, --name NAME         安装器名称"
    echo "  -b, --batch             创建批量安装脚本"
    echo "  -c, --checker           创建系统兼容性检查工具"
    echo "  -g, --configs           生成配置文件模板"
    echo "  -a, --all               创建所有工具"
    echo "  -v, --verbose           详细输出"
    echo
    echo "示例:"
    echo "  $0 package.tar.gz                    # 创建基本安装器"
    echo "  $0 --all package.tar.gz              # 创建完整工具集"
    echo "  $0 -b -c package.tar.gz              # 创建安装器和批量工具"
    echo "  $0 -o /tmp/portable package.tar.gz   # 指定输出目录"
}

# 检查依赖
check_dependencies() {
    log_info "检查构建依赖..."
    
    # 检查Python
    if ! command -v python3 &> /dev/null; then
        log_error "未找到Python3"
        exit 1
    fi
    
    # 检查必要的工具
    local tools=("tar" "gzip" "base64" "sha256sum")
    for tool in "${tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            log_error "未找到工具: $tool"
            exit 1
        fi
    done
    
    log_success "依赖检查通过"
}

# 验证离线包
verify_package() {
    local package="$1"
    
    log_info "验证离线包: $package"
    
    if [[ ! -f "$package" ]]; then
        log_error "离线包不存在: $package"
        exit 1
    fi
    
    # 检查文件格式
    if ! file "$package" | grep -q "gzip compressed"; then
        log_error "不是有效的gzip压缩文件"
        exit 1
    fi
    
    # 检查文件大小
    local size=$(stat -c%s "$package" 2>/dev/null || stat -f%z "$package" 2>/dev/null)
    local size_mb=$((size / 1024 / 1024))
    
    if [[ $size_mb -lt 10 ]]; then
        log_warning "离线包较小 (${size_mb}MB)，请确认包含完整内容"
    fi
    
    log_success "离线包验证通过 (${size_mb}MB)"
}

# 生成配置文件模板
generate_configs() {
    local output_dir="$1"
    
    log_info "生成配置文件模板..."
    
    python3 tools/config_generator.py --all --output "$output_dir/config" --deployment-script
    
    log_success "配置文件模板生成完成"
}

# 创建便携式安装器
create_portable_installer() {
    local package="$1"
    local output_dir="$2"
    local installer_name="$3"
    local create_batch="$4"
    local create_checker="$5"
    
    log_info "创建便携式安装器..."
    
    local args="--output $output_dir"
    
    if [[ -n "$installer_name" ]]; then
        args="$args --name $installer_name"
    fi
    
    if [[ "$create_batch" == "true" ]]; then
        args="$args --batch"
    fi
    
    if [[ "$create_checker" == "true" ]]; then
        args="$args --checker"
    fi
    
    if [[ "$VERBOSE" == "true" ]]; then
        args="$args --verbose"
    fi
    
    python3 tools/portable_installer_builder.py $args "$package"
    
    log_success "便携式安装器创建完成"
}

# 创建使用说明文档
create_documentation() {
    local output_dir="$1"
    
    log_info "创建使用说明文档..."
    
    cat > "$output_dir/README.md" << 'EOF'
# 便携式安装器使用说明

## 文件说明

### 安装器文件
- `*.run` - 自解压安装器，包含完整的离线安装包
- `system_checker.sh` - 系统兼容性检查工具
- `batch_install.sh` - 批量安装脚本

### 配置文件
- `config/` - 配置文件模板目录
- `config/deploy_config.sh` - 配置部署脚本

## 使用方法

### 1. 单机安装

#### 基本安装
```bash
# 传输安装器到目标设备
scp audio-processing-system-*.run user@target:/tmp/

# 在目标设备上运行
sudo ./audio-processing-system-*.run
```

#### 静默安装
```bash
# 无交互安装
sudo ./audio-processing-system-*.run --silent
```

#### 自定义安装目录
```bash
# 安装到指定目录
sudo ./audio-processing-system-*.run --install-dir /usr/local/audio
```

#### 检查系统兼容性
```bash
# 仅检查兼容性，不安装
./audio-processing-system-*.run --check-only

# 或使用独立检查工具
./system_checker.sh
```

### 2. 批量安装

#### 准备主机列表
创建 `hosts.txt` 文件，每行一个主机地址：
```
192.168.1.100
192.168.1.101
192.168.1.102
classroom-pc-01
classroom-pc-02
```

#### 执行批量安装
```bash
# 基本批量安装
./batch_install.sh hosts.txt

# 指定SSH用户和密钥
./batch_install.sh -u admin -k ~/.ssh/id_rsa hosts.txt

# 并行安装（同时安装10台）
./batch_install.sh --parallel 10 hosts.txt

# 仅检查连通性
./batch_install.sh --check-only hosts.txt
```

### 3. 配置管理

#### 查看可用配置
```bash
cd config/
./deploy_config.sh
```

#### 部署特定配置
```bash
# 部署标准教室配置
./deploy_config.sh classroom_standard.json

# 部署大型教室配置
./deploy_config.sh classroom_large.json
```

## 安装器选项

### 命令行参数
- `-h, --help` - 显示帮助信息
- `-s, --silent` - 静默安装模式
- `-d, --install-dir DIR` - 指定安装目录
- `-c, --check-only` - 仅检查系统兼容性
- `-u, --uninstall` - 卸载系统
- `-v, --verbose` - 详细输出
- `--no-start` - 安装后不启动服务
- `--force` - 强制安装，跳过兼容性检查

### 环境变量
- `INSTALL_DIR` - 安装目录（默认：/opt/audio-processing-system）
- `SILENT_MODE` - 静默模式（true/false）

## 系统要求

### 最低要求
- **操作系统**: Ubuntu 20.04+ / Debian 11+ / CentOS 8+
- **架构**: x86_64, aarch64, armv7l
- **内存**: 4GB RAM
- **存储**: 10GB 可用空间
- **Python**: 3.10+

### 推荐配置
- **内存**: 8GB RAM
- **存储**: 20GB SSD
- **网络**: 千兆以太网（可选）

## 故障排除

### 安装失败
1. 检查系统兼容性：`./system_checker.sh`
2. 查看详细日志：`--verbose` 选项
3. 检查磁盘空间和权限
4. 尝试强制安装：`--force` 选项

### 服务启动失败
```bash
# 查看服务状态
systemctl status audio-processing

# 查看日志
journalctl -u audio-processing -f

# 手动启动
systemctl start audio-processing
```

### 批量安装问题
1. 检查SSH连接：`ssh user@host`
2. 验证主机列表格式
3. 确认SSH密钥权限：`chmod 600 ~/.ssh/id_rsa`
4. 使用 `--check-only` 测试连通性

## 卸载

### 单机卸载
```bash
# 使用安装器卸载
sudo ./audio-processing-system-*.run --uninstall

# 手动卸载
sudo systemctl stop audio-processing
sudo systemctl disable audio-processing
sudo rm -rf /opt/audio-processing-system
sudo rm -f /etc/systemd/system/audio-processing*.service
```

### 批量卸载
```bash
# 在每台主机上运行卸载命令
for host in $(cat hosts.txt); do
    ssh $host "sudo systemctl stop audio-processing && sudo rm -rf /opt/audio-processing-system"
done
```

## 技术支持

如遇问题，请收集以下信息：
1. 系统兼容性检查结果
2. 安装日志（使用 --verbose）
3. 系统信息（uname -a, free -h, df -h）
4. 错误信息截图

EOF

    log_success "使用说明文档创建完成"
}

# 创建测试脚本
create_test_script() {
    local output_dir="$1"
    
    log_info "创建测试脚本..."
    
    cat > "$output_dir/test_installer.sh" << 'EOF'
#!/bin/bash
# 安装器测试脚本

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

# 测试安装器文件
test_installer_files() {
    log_info "测试安装器文件..."
    
    local installer_found=false
    for file in *.run; do
        if [[ -f "$file" ]]; then
            installer_found=true
            log_success "找到安装器: $file"
            
            # 检查文件权限
            if [[ -x "$file" ]]; then
                log_success "安装器具有执行权限"
            else
                log_error "安装器缺少执行权限"
                return 1
            fi
            
            # 测试帮助信息
            if ./"$file" --help &> /dev/null; then
                log_success "安装器帮助信息正常"
            else
                log_error "安装器帮助信息异常"
                return 1
            fi
        fi
    done
    
    if [[ "$installer_found" == "false" ]]; then
        log_error "未找到安装器文件"
        return 1
    fi
    
    return 0
}

# 测试系统检查工具
test_system_checker() {
    log_info "测试系统检查工具..."
    
    if [[ -f "system_checker.sh" ]]; then
        log_success "找到系统检查工具"
        
        if [[ -x "system_checker.sh" ]]; then
            log_success "系统检查工具具有执行权限"
        else
            log_error "系统检查工具缺少执行权限"
            return 1
        fi
        
        # 运行系统检查（允许失败）
        if ./system_checker.sh &> /dev/null; then
            log_success "系统检查工具运行正常"
        else
            log_info "系统检查工具运行完成（可能有警告）"
        fi
    else
        log_info "未找到系统检查工具（可选）"
    fi
    
    return 0
}

# 测试批量安装脚本
test_batch_installer() {
    log_info "测试批量安装脚本..."
    
    if [[ -f "batch_install.sh" ]]; then
        log_success "找到批量安装脚本"
        
        if [[ -x "batch_install.sh" ]]; then
            log_success "批量安装脚本具有执行权限"
        else
            log_error "批量安装脚本缺少执行权限"
            return 1
        fi
        
        # 测试帮助信息
        if ./batch_install.sh --help &> /dev/null; then
            log_success "批量安装脚本帮助信息正常"
        else
            log_error "批量安装脚本帮助信息异常"
            return 1
        fi
    else
        log_info "未找到批量安装脚本（可选）"
    fi
    
    return 0
}

# 测试配置文件
test_config_files() {
    log_info "测试配置文件..."
    
    if [[ -d "config" ]]; then
        log_success "找到配置目录"
        
        local config_count=$(find config -name "*.json" | wc -l)
        if [[ $config_count -gt 0 ]]; then
            log_success "找到 $config_count 个配置文件"
            
            # 验证JSON格式
            local valid_configs=0
            for config_file in config/*.json; do
                if python3 -m json.tool "$config_file" &> /dev/null; then
                    ((valid_configs++))
                else
                    log_error "配置文件格式错误: $config_file"
                fi
            done
            
            if [[ $valid_configs -eq $config_count ]]; then
                log_success "所有配置文件格式正确"
            else
                log_error "部分配置文件格式错误"
                return 1
            fi
        else
            log_info "配置目录为空"
        fi
        
        # 测试部署脚本
        if [[ -f "config/deploy_config.sh" ]]; then
            log_success "找到配置部署脚本"
        else
            log_info "未找到配置部署脚本"
        fi
    else
        log_info "未找到配置目录（可选）"
    fi
    
    return 0
}

# 主测试函数
main() {
    echo "=========================================="
    echo "    便携式安装器测试"
    echo "=========================================="
    echo
    
    local tests_passed=0
    local tests_total=0
    
    # 运行测试
    local test_functions=(
        "test_installer_files"
        "test_system_checker"
        "test_batch_installer"
        "test_config_files"
    )
    
    for test_func in "${test_functions[@]}"; do
        ((tests_total++))
        if $test_func; then
            ((tests_passed++))
        fi
        echo
    done
    
    # 显示结果
    echo "=========================================="
    echo "测试结果: $tests_passed/$tests_total 通过"
    echo "=========================================="
    
    if [[ $tests_passed -eq $tests_total ]]; then
        log_success "所有测试通过！"
        exit 0
    else
        log_error "部分测试失败"
        exit 1
    fi
}

main "$@"
EOF

    chmod +x "$output_dir/test_installer.sh"
    
    log_success "测试脚本创建完成"
}

# 显示构建结果
show_results() {
    local output_dir="$1"
    
    echo
    log_info "构建结果:"
    echo
    
    # 列出生成的文件
    if [[ -d "$output_dir" ]]; then
        find "$output_dir" -type f | sort | while read -r file; do
            local size=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null)
            local size_mb=$((size / 1024 / 1024))
            local size_kb=$((size / 1024))
            
            if [[ $size_mb -gt 0 ]]; then
                echo "  📦 $(basename "$file") (${size_mb}MB)"
            else
                echo "  📄 $(basename "$file") (${size_kb}KB)"
            fi
        done
    fi
    
    echo
    log_info "使用说明:"
    echo "1. 查看使用文档: cat $output_dir/README.md"
    echo "2. 测试安装器: cd $output_dir && ./test_installer.sh"
    echo "3. 传输到目标设备进行安装"
}

# 默认参数
OUTPUT_DIR="dist/portable"
INSTALLER_NAME=""
CREATE_BATCH="false"
CREATE_CHECKER="false"
CREATE_CONFIGS="false"
CREATE_ALL="false"
VERBOSE="false"
PACKAGE=""

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -n|--name)
            INSTALLER_NAME="$2"
            shift 2
            ;;
        -b|--batch)
            CREATE_BATCH="true"
            shift
            ;;
        -c|--checker)
            CREATE_CHECKER="true"
            shift
            ;;
        -g|--configs)
            CREATE_CONFIGS="true"
            shift
            ;;
        -a|--all)
            CREATE_ALL="true"
            shift
            ;;
        -v|--verbose)
            VERBOSE="true"
            shift
            ;;
        -*)
            log_error "未知选项: $1"
            show_help
            exit 1
            ;;
        *)
            PACKAGE="$1"
            shift
            ;;
    esac
done

# 检查参数
if [[ -z "$PACKAGE" ]]; then
    log_error "请指定离线包路径"
    show_help
    exit 1
fi

# 如果指定了 --all，启用所有选项
if [[ "$CREATE_ALL" == "true" ]]; then
    CREATE_BATCH="true"
    CREATE_CHECKER="true"
    CREATE_CONFIGS="true"
fi

# 主构建流程
main() {
    echo "=========================================="
    echo "    便携式安装器构建工具"
    echo "=========================================="
    echo
    
    check_dependencies
    verify_package "$PACKAGE"
    
    # 创建输出目录
    mkdir -p "$OUTPUT_DIR"
    
    # 生成配置文件模板
    if [[ "$CREATE_CONFIGS" == "true" ]]; then
        generate_configs "$OUTPUT_DIR"
    fi
    
    # 创建便携式安装器
    create_portable_installer "$PACKAGE" "$OUTPUT_DIR" "$INSTALLER_NAME" "$CREATE_BATCH" "$CREATE_CHECKER"
    
    # 创建文档和测试脚本
    create_documentation "$OUTPUT_DIR"
    create_test_script "$OUTPUT_DIR"
    
    # 显示结果
    show_results "$OUTPUT_DIR"
    
    echo
    log_success "便携式安装器构建完成！"
}

# 错误处理
trap 'log_error "构建过程中发生错误"; exit 1' ERR

# 运行主程序
main "$@"