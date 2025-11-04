# 离线包构建示例

## 快速开始

### 1. 构建当前环境的包（推荐）

```bash
# 使用单架构工具（更简单）
python3 tools/offline_packager.py

# 或使用多架构工具
python3 tools/build_multi_arch.py
```

**输出**: 当前架构的离线包，适合在相同环境下部署

### 2. 构建特定架构的包

```bash
# 构建x86_64架构的包
python3 tools/build_multi_arch.py --architectures x86_64

# 构建ARM64架构的包
python3 tools/build_multi_arch.py --architectures aarch64
```

### 3. 构建多架构包

```bash
# 构建包含x86_64和ARM64的统一包
python3 tools/build_multi_arch.py --architectures x86_64 aarch64
```

## Docker构建示例

### 构建Ubuntu 24.04的包

```bash
# 构建Ubuntu 24.04 x86_64包
python3 tools/build_multi_arch.py \
    --docker \
    --os ubuntu24 \
    --architectures x86_64 \
    --individual-only

# 输出: audio-processing-system-offline-1.0.0-ubuntu24.04-x86_64.tar.gz
```

### 构建CentOS 8的包

```bash
# 构建CentOS 8 x86_64包
python3 tools/build_multi_arch.py \
    --docker \
    --os centos8 \
    --architectures x86_64 \
    --individual-only

# 输出: audio-processing-system-offline-1.0.0-centos8-x86_64.tar.gz
```

### 构建多个发行版的包

```bash
# 为不同发行版构建包
for os in ubuntu22 ubuntu24 centos8; do
    python3 tools/build_multi_arch.py \
        --docker \
        --os $os \
        --architectures x86_64 \
        --individual-only \
        --output "dist/$os"
done
```

## 实际使用场景

### 场景1: 开发环境快速测试

```bash
# 在macOS上开发，构建当前环境的包进行测试
python3 tools/offline_packager.py --verbose

# 输出: audio-processing-system-offline-1.0.0-darwin-aarch64.tar.gz
```

### 场景2: 生产环境部署

```bash
# 为生产环境的Ubuntu 22.04服务器构建包
python3 tools/build_multi_arch.py \
    --docker \
    --os ubuntu22 \
    --architectures x86_64 \
    --individual-only \
    --output dist/production

# 输出: dist/production/audio-processing-system-offline-1.0.0-ubuntu22.04-x86_64.tar.gz
```

### 场景3: 多架构支持

```bash
# 构建支持多种架构的统一包
python3 tools/build_multi_arch.py \
    --docker \
    --os ubuntu22 \
    --architectures x86_64 aarch64 armv7l \
    --output dist/multi-arch

# 输出:
# - 单架构包: audio-processing-system-offline-1.0.0-ubuntu22.04-{arch}.tar.gz
# - 统一包: audio-processing-system-multi-arch-offline-1.0.0-ubuntu22.04.tar.gz
```

### 场景4: ARM设备部署

```bash
# 为树莓派等ARM设备构建包
python3 tools/build_multi_arch.py \
    --docker \
    --os ubuntu22 \
    --architectures aarch64 armv7l \
    --output dist/arm-devices

# 输出:
# - audio-processing-system-offline-1.0.0-ubuntu22.04-aarch64.tar.gz
# - audio-processing-system-offline-1.0.0-ubuntu22.04-armv7l.tar.gz
# - audio-processing-system-multi-arch-offline-1.0.0-ubuntu22.04.tar.gz
```

## 构建选项说明

### 工具选择

| 工具 | 适用场景 | 特点 |
|------|----------|------|
| `offline_packager.py` | 单架构构建 | 简单、快速、适合开发测试 |
| `build_multi_arch.py` | 多架构构建 | 功能完整、支持Docker、适合生产 |

### 构建模式

| 模式 | 命令 | 特点 |
|------|------|------|
| 本地构建 | 默认 | 快速、使用当前环境 |
| Docker构建 | `--docker` | 跨平台、环境一致 |

### 包类型

| 类型 | 选项 | 说明 |
|------|------|------|
| 单架构包 | `--individual-only` | 每个架构独立的包 |
| 统一包 | `--unified-only` | 包含多个架构的包 |
| 混合 | 默认 | 同时生成两种包 |

## 常见问题

### Q: 如何选择构建工具？

**A**: 
- 开发测试: 使用 `offline_packager.py`
- 生产部署: 使用 `build_multi_arch.py --docker`
- 多架构支持: 使用 `build_multi_arch.py`

### Q: Docker构建失败怎么办？

**A**: 
1. 确保Docker已安装并运行
2. 使用 `--verbose` 查看详细错误
3. 尝试本地构建: 去掉 `--docker` 选项

### Q: 如何验证构建的包？

**A**:
```bash
# 验证校验和
sha256sum -c audio-processing-system-offline-*.tar.gz.sha256

# 解压并检查内容
tar -tzf audio-processing-system-offline-*.tar.gz | head -20
```

### Q: 包太大怎么办？

**A**:
- 单架构包比多架构包小
- 使用 `--individual-only` 只生成单架构包
- 检查依赖列表，移除不必要的包

## 最佳实践

1. **开发阶段**: 使用本地构建，快速迭代
2. **测试阶段**: 使用Docker构建，确保环境一致
3. **生产部署**: 构建特定操作系统的包
4. **版本管理**: 使用语义化版本号
5. **验证流程**: 始终验证校验和
6. **文档记录**: 记录构建参数和目标环境