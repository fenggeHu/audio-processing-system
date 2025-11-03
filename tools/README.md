# 离线部署工具说明
# Offline Deployment Tools Documentation

本目录包含音频处理系统的离线部署工具，支持在无网络环境下构建和部署系统。

## 工具概览

### 1. 离线包构建工具

#### `offline_packager.py` - 单架构离线包构建器
构建包含所有依赖的单架构离线安装包。

**使用方法:**
```bash
# 构建当前架构的离线包
python3 tools/offline_packager.py

# 指定输出目录
python3 tools/offline_packager.py --output dist/my-offline

# 指定目标架构
python3 tools/offline_packager.py --architectures x86_64

# 详细输出
python3 tools/offline_packager.py --verbose
```

#### `build_multi_arch.py` - 多架构离线包构建器
构建支持多种架构的统一离线安装包。

**使用方法:**
```bash
# 构建多架构包（默认: x86_64, aarch64）
python3 tools/build_multi_arch.py

# 指定架构
python3 tools/build_multi_arch.py --architectures x86_64 aarch64 armv7l

# 不使用Docker构建
python3 tools/build_multi_arch.py --no-docker

# 指定输出目录
python3 tools/build_multi_arch.py --output dist/multi-arch
```

#### `build_offline.sh` - 统一构建脚本
提供交互式的构建体验，支持单架构和多架构构建。

**使用方法:**
```bash
# 交互式构建
./build_offline.sh

# 构建单架构包
./build_offline.sh --single-arch

# 构建多架构包
./build_offline.sh --multi-arch

# 指定架构和输出目录
./build_offline.sh --arch x86_64 --output /tmp/offline

# 不使用Docker
./build_offline.sh --multi-arch --no-docker
```

### 2. 离线包验证工具

#### `verify_offline_package.py` - 离线包完整性验证
验证离线包的完整性、依赖关系和文件结构。

**使用方法:**
```bash
# 验证离线包
python3 tools/verify_offline_package.py package.tar.gz

# 详细输出
python3 tools/verify_offline_package.py package.tar.gz --verbose
```

## 构建流程

### 1. 准备环境

确保系统已安装必要的依赖：

```bash
# Ubuntu/Debian
sudo apt-get install python3 python3-pip python3-venv

# CentOS/RHEL
sudo yum install python3 python3-pip

# 安装构建依赖
pip3 install tomli wheel setuptools
```

### 2. 构建离线包

#### 方式一：使用统一脚本（推荐）

```bash
# 运行构建脚本
./build_offline.sh

# 选择构建类型
# 1) 单架构包（当前架构）
# 2) 多架构包（x86_64 + aarch64）
```

#### 方式二：直接使用Python工具

```bash
# 单架构构建
python3 tools/offline_packager.py --output dist/single

# 多架构构建
python3 tools/build_multi_arch.py --output dist/multi
```

### 3. 验证构建结果

```bash
# 验证生成的离线包
python3 tools/verify_offline_package.py dist/audio-processing-system-*.tar.gz
```

## 离线包结构

### 单架构包结构
```
audio-processing-system-offline/
├── src/                          # 源代码
├── config/                       # 配置文件
├── static/                       # 静态文件
├── python_packages/              # Python依赖包
│   └── x86_64/                   # 架构特定包
│       ├── numpy-1.24.0-*.whl
│       ├── scipy-1.10.0-*.whl
│       └── ...
├── scripts/                      # 安装脚本
│   ├── install_offline.sh        # 离线安装器
│   ├── install_system_deps.sh    # 系统依赖安装
│   └── verify_dependencies.py    # 依赖验证
├── requirements-offline.txt      # 依赖列表
├── manifest.json                 # 包清单
└── README.md                     # 说明文档
```

### 多架构包结构
```
audio-processing-system-multi-arch/
├── src/                          # 源代码
├── config/                       # 配置文件
├── static/                       # 静态文件
├── packages/                     # 多架构Python包
│   ├── x86_64/                   # x86_64架构包
│   ├── aarch64/                  # ARM64架构包
│   └── armv7l/                   # ARMv7架构包
├── install_multi_arch.sh         # 多架构安装器
├── requirements-offline.txt      # 依赖列表
└── README.md                     # 说明文档
```

## 部署流程

### 1. 传输离线包

将构建好的离线包传输到目标设备：

```bash
# 使用scp
scp audio-processing-system-*.tar.gz user@target-device:/tmp/

# 使用USB存储设备
cp audio-processing-system-*.tar.gz /media/usb/
```

### 2. 解压和安装

在目标设备上：

```bash
# 解压离线包
tar -xzf audio-processing-system-*.tar.gz

# 进入目录
cd audio-processing-system-*

# 运行安装器（需要sudo权限）
sudo ./install_offline.sh          # 单架构包
# 或
sudo ./install_multi_arch.sh       # 多架构包
```

### 3. 验证安装

```bash
# 检查服务状态
systemctl status audio-processing

# 访问Web界面
curl http://localhost/health

# 查看日志
journalctl -u audio-processing -f
```

## 高级用法

### 自定义依赖

如果需要添加额外的Python依赖：

1. 编辑 `requirements-offline.txt` 文件
2. 添加新的依赖包
3. 重新构建离线包

```bash
# 编辑依赖文件
echo "your-package>=1.0.0" >> requirements-offline.txt

# 重新构建
./build_offline.sh
```

### Docker构建

使用Docker可以为不同架构构建包：

```bash
# 确保Docker支持多架构
docker buildx create --use

# 构建多架构包
python3 tools/build_multi_arch.py --architectures x86_64 aarch64 armv7l
```

### 批量部署

对于多设备部署，可以使用配置管理工具：

```bash
# 使用Ansible批量部署
ansible-playbook -i inventory deploy-offline.yml

# 使用脚本批量部署
for host in host1 host2 host3; do
    scp package.tar.gz $host:/tmp/
    ssh $host "cd /tmp && tar -xzf package.tar.gz && sudo ./install_offline.sh"
done
```

## 故障排除

### 常见问题

1. **构建失败：缺少系统依赖**
   ```bash
   # Ubuntu/Debian
   sudo apt-get install build-essential python3-dev
   
   # CentOS/RHEL
   sudo yum groupinstall "Development Tools"
   ```

2. **Docker构建失败**
   ```bash
   # 检查Docker状态
   docker --version
   docker buildx ls
   
   # 启用多架构支持
   docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
   ```

3. **包验证失败**
   ```bash
   # 重新构建包
   rm -rf dist/
   ./build_offline.sh
   
   # 检查依赖完整性
   python3 tools/verify_offline_package.py package.tar.gz --verbose
   ```

4. **安装失败：权限问题**
   ```bash
   # 确保使用sudo运行安装器
   sudo ./install_offline.sh
   
   # 检查文件权限
   ls -la install_offline.sh
   chmod +x install_offline.sh
   ```

### 日志和调试

```bash
# 构建时启用详细输出
./build_offline.sh --verbose

# 验证时查看详细信息
python3 tools/verify_offline_package.py package.tar.gz --verbose

# 安装时查看日志
sudo ./install_offline.sh 2>&1 | tee install.log
```

## 最佳实践

1. **构建前验证环境**
   - 确保Python版本 >= 3.10
   - 检查磁盘空间（至少2GB）
   - 验证网络连接（构建时需要）

2. **选择合适的构建方式**
   - 单一架构部署：使用单架构包
   - 多种设备部署：使用多架构包
   - 资源受限环境：使用轻量级配置

3. **验证构建结果**
   - 始终验证构建的离线包
   - 在测试环境中验证安装过程
   - 检查所有依赖是否完整

4. **安全考虑**
   - 验证包的完整性和校验和
   - 在隔离环境中测试安装
   - 定期更新离线包

## 支持和反馈

如果在使用过程中遇到问题：

1. 查看详细日志输出
2. 检查系统兼容性
3. 验证包的完整性
4. 提交Issue并附上日志信息

---

**版本**: v1.0.0  
**更新日期**: 2024年1月  
**维护者**: Audio Processing System Team