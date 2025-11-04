# 多架构离线包构建指南

## 概述

多架构构建工具 `tools/build_multi_arch.py` 支持为不同架构（x86_64, ARM64, ARMv7）构建离线部署包，提供了灵活的包命名和构建选项。

## 功能特性

### 支持的架构
- **x86_64**: Intel/AMD 64位处理器
- **aarch64**: ARM 64位处理器 (ARM64)
- **armv7l**: ARM 32位处理器 (ARMv7)

### 包命名规则
- **单架构包**: `audio-processing-system-offline-{version}-{platform}-{arch}.tar.gz`
- **多架构包**: `audio-processing-system-multi-arch-offline-{version}-{platform}.tar.gz`
- **校验和文件**: 每个包都附带 `.sha256` 校验和文件

### 构建模式
1. **单架构包**: 为每个架构生成独立的完整安装包
2. **统一多架构包**: 包含所有架构的Python包，安装时自动选择
3. **混合模式**: 同时生成单架构包和统一包

## 使用方法

### 基本用法

```bash
# 构建当前架构的包（默认本地构建）
python3 tools/build_multi_arch.py

# 指定架构（本地构建）
python3 tools/build_multi_arch.py --architectures x86_64 aarch64

# 指定输出目录
python3 tools/build_multi_arch.py --output dist/my-builds

# 使用Docker构建（默认Ubuntu 22.04）
python3 tools/build_multi_arch.py --docker --architectures x86_64 aarch64
```

### 构建选项

```bash
# 只构建单架构包
python3 tools/build_multi_arch.py --individual-only

# 只构建统一多架构包
python3 tools/build_multi_arch.py --unified-only

# 使用Docker构建
python3 tools/build_multi_arch.py --docker

# 指定操作系统（仅Docker构建）
python3 tools/build_multi_arch.py --docker --os ubuntu24

# 详细输出
python3 tools/build_multi_arch.py --verbose
```

### 高级用法

```bash
# 为ARM设备构建单架构包（本地构建）
python3 tools/build_multi_arch.py \
    --architectures aarch64 armv7l \
    --individual-only \
    --verbose

# 构建CentOS 8的包（Docker构建）
python3 tools/build_multi_arch.py \
    --docker \
    --os centos8 \
    --architectures x86_64 \
    --individual-only

# 构建Ubuntu 24的多架构包
python3 tools/build_multi_arch.py \
    --docker \
    --os ubuntu24 \
    --architectures x86_64 aarch64 \
    --output dist/ubuntu24
```

## 构建环境

### 本地构建（默认）
- 使用当前系统环境
- 适合单架构构建
- 构建速度更快
- 无需额外依赖

**要求:**
- Python 3.10+
- pip, setuptools, wheel

### Docker构建
- 自动处理跨架构编译
- 确保环境一致性
- 支持特定Linux发行版
- 支持并行构建

**要求:**
- Docker已安装并运行
- 支持多架构构建 (`docker buildx`)

### 支持的操作系统（Docker构建）
- **ubuntu20**: Ubuntu 20.04 LTS
- **ubuntu22**: Ubuntu 22.04 LTS（默认）
- **ubuntu24**: Ubuntu 24.04 LTS
- **centos7**: CentOS 7
- **centos8**: CentOS Stream 8
- **rocky8**: Rocky Linux 8
- **rocky9**: Rocky Linux 9

## 输出结构

### 单架构包结构
```
audio-processing-system-offline/
├── src/                    # 应用源代码
├── config/                 # 配置文件
├── static/                 # 静态文件
├── python_packages/        # Python包
│   └── {arch}/            # 架构特定的包
├── scripts/               # 安装脚本
│   ├── install_offline.sh # 主安装脚本
│   └── install_system_deps.sh # 系统依赖脚本
├── requirements.txt       # 依赖列表
├── manifest.json         # 包清单
└── README.md             # 说明文档
```

### 多架构包结构
```
audio-processing-system-multi-arch/
├── src/                    # 应用源代码
├── config/                 # 配置文件
├── static/                 # 静态文件
├── packages/              # 多架构Python包
│   ├── x86_64/           # x86_64架构包
│   ├── aarch64/          # ARM64架构包
│   └── armv7l/           # ARMv7架构包
├── install_multi_arch.sh  # 多架构安装脚本
├── requirements.txt       # 依赖列表
├── manifest.json         # 包清单
└── README.md             # 说明文档
```

## 安装方法

### 单架构包安装

```bash
# 1. 选择对应架构的包
tar -xzf audio-processing-system-offline-1.0.0-linux-x86_64.tar.gz

# 2. 进入目录
cd audio-processing-system-offline

# 3. 运行安装脚本
sudo ./scripts/install_offline.sh
```

### 多架构包安装

```bash
# 1. 解压统一包
tar -xzf audio-processing-system-multi-arch-offline-1.0.0-linux.tar.gz

# 2. 进入目录
cd audio-processing-system-multi-arch

# 3. 运行安装脚本（自动检测架构）
sudo ./install_multi_arch.sh
```

## 包验证

### 校验和验证
```bash
# 验证单架构包
sha256sum -c audio-processing-system-offline-1.0.0-linux-x86_64.tar.gz.sha256

# 验证多架构包
sha256sum -c audio-processing-system-multi-arch-offline-1.0.0-linux.tar.gz.sha256
```

### 清单验证
```bash
# 解压后验证包完整性
python3 scripts/verify_dependencies.py manifest.json
```

## 构建示例

### 示例1: 生产环境构建
```bash
# 为生产环境构建所有架构的包
python3 tools/build_multi_arch.py \
    --architectures x86_64 aarch64 armv7l \
    --output dist/production \
    --verbose

# 输出:
# - audio-processing-system-offline-1.0.0-linux-x86_64.tar.gz
# - audio-processing-system-offline-1.0.0-linux-aarch64.tar.gz  
# - audio-processing-system-offline-1.0.0-linux-armv7l.tar.gz
# - audio-processing-system-multi-arch-offline-1.0.0-linux.tar.gz
```

### 示例2: 快速本地测试
```bash
# 只为当前架构构建，用于快速测试
python3 tools/build_multi_arch.py \
    --architectures aarch64 \
    --individual-only \
    --no-docker

# 输出:
# - audio-processing-system-offline-1.0.0-darwin-aarch64.tar.gz
```

### 示例3: ARM设备专用
```bash
# 为ARM设备构建优化包
python3 tools/build_multi_arch.py \
    --architectures aarch64 armv7l \
    --output dist/arm-devices

# 输出:
# - audio-processing-system-offline-1.0.0-linux-aarch64.tar.gz
# - audio-processing-system-offline-1.0.0-linux-armv7l.tar.gz
# - audio-processing-system-multi-arch-offline-1.0.0-linux.tar.gz
```

## 故障排除

### Docker相关问题

**问题**: Docker不可用
```
WARNING - Docker不可用，将使用本地环境构建
```

**解决方案**:
1. 确保Docker已安装: `docker --version`
2. 确保Docker服务运行: `sudo systemctl start docker`
3. 或使用 `--no-docker` 选项进行本地构建

### 架构兼容性问题

**问题**: 包下载失败
```
ERROR: Could not find a version that satisfies the requirement
```

**解决方案**:
1. 使用Docker构建以获得更好的跨架构支持
2. 检查依赖是否支持目标架构
3. 考虑使用源码包而非二进制包

### 权限问题

**问题**: 无法创建输出目录
```
PermissionError: [Errno 13] Permission denied
```

**解决方案**:
1. 确保对输出目录有写权限
2. 使用 `--output` 指定可写目录
3. 必要时使用 `sudo` 运行

## 与单架构工具的对比

| 特性 | offline_packager.py | build_multi_arch.py |
|------|-------------------|-------------------|
| 架构支持 | 单架构 | 多架构 |
| 包命名 | 基础命名 | 优化命名（含平台/架构） |
| 并行构建 | 否 | 是（Docker模式） |
| 跨架构构建 | 否 | 是（Docker支持） |
| 包类型 | 单一包 | 单架构包 + 统一包 |
| 安装复杂度 | 简单 | 中等 |

## 最佳实践

1. **生产环境**: 使用Docker构建，生成所有架构的包
2. **开发测试**: 使用本地构建，只构建当前架构
3. **分发策略**: 提供单架构包供精确匹配，统一包供自动选择
4. **验证流程**: 始终验证校验和和清单完整性
5. **版本管理**: 使用语义化版本号，包含在包名中

## 技术细节

### 包命名算法
```python
# 单架构包
package_name = f"audio-processing-system-offline-{version}-{platform}-{arch}.tar.gz"

# 多架构包  
package_name = f"audio-processing-system-multi-arch-offline-{version}-{platform}.tar.gz"
```

### 架构检测逻辑
```python
arch_mapping = {
    "x86_64": "x86_64", "amd64": "x86_64",
    "aarch64": "aarch64", "arm64": "aarch64", 
    "armv7l": "armv7l", "armhf": "armv7l"
}
```

### 平台检测
- Linux: `linux`
- macOS: `darwin` 
- Windows: `windows`

这个多架构构建工具为音频处理系统提供了完整的跨平台部署解决方案，支持灵活的构建选项和优化的包命名规则。