# 离线包构建故障排除指南

## 常见错误及解决方案

### 1. 包下载失败

#### 错误信息
```
ERROR: Could not find a version that satisfies the requirement psutil>=5.9.0
ERROR: No matching distribution found for psutil>=5.9.0
```

#### 原因分析
- pip无法找到满足版本要求的包
- 网络连接问题
- 平台兼容性问题

#### 解决方案

**方案1: 检查网络连接**
```bash
# 测试网络连接
ping pypi.org

# 测试pip连接
pip install --dry-run requests
```

**方案2: 更新pip和工具**
```bash
# 更新pip
python3 -m pip install --upgrade pip

# 更新setuptools和wheel
python3 -m pip install --upgrade setuptools wheel
```

**方案3: 使用国内镜像源**
```bash
# 临时使用清华镜像
python3 tools/offline_packager.py --verbose \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple/

# 或配置pip使用镜像
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple/
```

**方案4: 放宽版本要求**
编辑 `pyproject.toml`，放宽依赖版本要求：
```toml
dependencies = [
    "psutil>=5.8.0",  # 从5.9.0降低到5.8.0
    # ... 其他依赖
]
```

### 2. Docker构建失败

#### 错误信息
```
docker: command not found
```

#### 解决方案
```bash
# 安装Docker (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install docker.io

# 安装Docker (macOS)
brew install --cask docker

# 启动Docker服务
sudo systemctl start docker

# 验证Docker安装
docker --version
```

#### 错误信息
```
permission denied while trying to connect to the Docker daemon socket
```

#### 解决方案
```bash
# 将用户添加到docker组
sudo usermod -aG docker $USER

# 重新登录或运行
newgrp docker

# 或使用sudo运行
sudo python3 tools/build_multi_arch.py --docker
```

### 3. 架构不匹配

#### 错误信息
```
不支持的架构: arm64
```

#### 解决方案
使用标准架构名称：
```bash
# 错误的架构名称
python3 tools/build_multi_arch.py --architectures arm64

# 正确的架构名称
python3 tools/build_multi_arch.py --architectures aarch64
```

**支持的架构名称：**
- `x86_64` - Intel/AMD 64位
- `aarch64` - ARM 64位
- `armv7l` - ARM 32位

### 4. 磁盘空间不足

#### 错误信息
```
No space left on device
```

#### 解决方案
```bash
# 检查磁盘空间
df -h

# 清理pip缓存
pip cache purge

# 清理Docker镜像
docker system prune -a

# 指定其他输出目录
python3 tools/offline_packager.py --output /path/to/large/disk/offline
```

### 5. Python版本不兼容

#### 错误信息
```
This package requires Python >=3.10
```

#### 解决方案
```bash
# 检查Python版本
python3 --version

# 使用pyenv安装Python 3.10+
pyenv install 3.10.12
pyenv local 3.10.12

# 或使用系统包管理器
sudo apt-get install python3.10 python3.10-venv python3.10-dev
```

### 6. 依赖冲突

#### 错误信息
```
ERROR: pip's dependency resolver does not currently take into account all the packages that are installed
```

#### 解决方案
```bash
# 创建新的虚拟环境
python3 -m venv fresh_env
source fresh_env/bin/activate

# 在新环境中构建
python3 tools/offline_packager.py
```

### 7. 系统依赖缺失

#### 错误信息
```
error: Microsoft Visual C++ 14.0 is required
```

#### 解决方案

**Linux:**
```bash
# Ubuntu/Debian
sudo apt-get install build-essential python3-dev

# CentOS/RHEL
sudo yum groupinstall "Development Tools"
sudo yum install python3-devel
```

**macOS:**
```bash
# 安装Xcode命令行工具
xcode-select --install

# 使用Homebrew安装依赖
brew install portaudio libsndfile fftw ffmpeg
```

**Windows:**
```bash
# 安装Visual Studio Build Tools
# 或使用预编译的wheel包
pip install --only-binary=all psutil
```

## 调试技巧

### 1. 启用详细输出
```bash
# 使用--verbose查看详细信息
python3 tools/offline_packager.py --verbose

# 查看pip的详细输出
pip install --verbose package_name
```

### 2. 检查生成的包
```bash
# 列出包内容
tar -tzf audio-processing-system-offline-*.tar.gz

# 验证校验和
sha256sum -c audio-processing-system-offline-*.tar.gz.sha256

# 检查Python包
ls -la dist/offline/*/python_packages/*/
```

### 3. 测试单个包下载
```bash
# 测试下载单个包
pip download psutil --dest /tmp/test

# 测试特定版本
pip download "psutil>=5.9.0" --dest /tmp/test

# 测试特定平台
pip download psutil --platform linux_x86_64 --dest /tmp/test
```

### 4. 检查依赖树
```bash
# 安装pipdeptree
pip install pipdeptree

# 查看依赖关系
pipdeptree

# 查看特定包的依赖
pipdeptree -p psutil
```

## 环境检查清单

在构建前，请确认以下环境要求：

### 基本要求
- [ ] Python 3.10 或更高版本
- [ ] pip 23.0 或更高版本
- [ ] 足够的磁盘空间（至少1GB）
- [ ] 稳定的网络连接

### Docker构建要求
- [ ] Docker已安装并运行
- [ ] 用户有Docker权限
- [ ] Docker支持多架构构建

### 系统依赖
- [ ] 编译工具链（gcc, make等）
- [ ] Python开发头文件
- [ ] 音频库开发包

### 网络要求
- [ ] 可访问PyPI (pypi.org)
- [ ] 可访问Docker Hub (docker.io)
- [ ] 防火墙允许相关端口

## 获取帮助

如果以上解决方案都无法解决问题，请：

1. **收集信息：**
   ```bash
   # 系统信息
   uname -a
   python3 --version
   pip --version
   
   # 错误日志
   python3 tools/offline_packager.py --verbose 2>&1 | tee build.log
   ```

2. **检查已知问题：**
   - 查看项目README
   - 搜索相关错误信息
   - 检查依赖包的官方文档

3. **创建最小复现案例：**
   ```bash
   # 尝试最简单的构建
   python3 tools/offline_packager.py
   
   # 测试单个依赖
   pip download psutil
   ```

4. **提供详细信息：**
   - 操作系统和版本
   - Python版本
   - 完整的错误信息
   - 构建命令和参数
   - 相关的环境变量

记住：大多数构建问题都与环境配置、网络连接或依赖版本有关。按照上述步骤逐一排查，通常能够解决问题。