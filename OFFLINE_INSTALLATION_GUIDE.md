# 音频处理系统离线安装指南

## 概述

本指南介绍如何使用离线包在无网络环境中安装音频处理系统。

## 构建离线包

### 1. 基本构建

```bash
# 构建当前架构的离线包
python3 tools/offline_packager.py

# 指定输出目录
python3 tools/offline_packager.py --output dist/my-offline

# 详细输出
python3 tools/offline_packager.py --verbose
```

### 2. 多架构构建

```bash
# 构建多个架构的离线包
python3 tools/offline_packager.py --architectures x86_64 aarch64 armv7l
```

### 3. 构建输出

构建完成后，会在输出目录生成：
- `audio-processing-system-offline-{version}-{platform}-{arch}.tar.gz` - 离线安装包
- `audio-processing-system-offline-{version}-{platform}-{arch}.tar.gz.sha256` - 校验和文件

## 离线安装

### 1. 传输文件

将离线包传输到目标设备：

```bash
# 使用scp传输
scp audio-processing-system-offline-*.tar.gz user@target-host:/tmp/

# 使用USB设备
cp audio-processing-system-offline-*.tar.gz /media/usb/
```

### 2. 验证完整性

```bash
# 验证校验和
sha256sum -c audio-processing-system-offline-*.tar.gz.sha256
```

### 3. 解压安装包

```bash
# 解压到当前目录
tar -xzf audio-processing-system-offline-*.tar.gz

# 进入解压目录
cd audio-processing-system-offline
```

### 4. 执行安装

**Linux系统：**
```bash
# 运行离线安装器（需要root权限）
sudo ./scripts/install_offline.sh
```

**macOS系统：**
```bash
# 运行离线安装器（不需要sudo）
./scripts/install_offline.sh
```

**Windows系统：**
```bash
# 在管理员权限的PowerShell中运行
.\scripts\install_offline.sh
```

## 安装过程说明

### 1. 系统依赖安装

安装器会自动检测操作系统并安装相应的系统依赖：

**Ubuntu/Debian:**
```bash
sudo apt-get install python3-dev portaudio19-dev libasound2-dev \
    libsndfile1-dev libfftw3-dev ffmpeg gcc g++ make pkg-config
```

**CentOS/RHEL:**
```bash
sudo yum install python3-devel portaudio-devel alsa-lib-devel \
    libsndfile-devel fftw-devel ffmpeg gcc gcc-c++ make pkgconfig
```

### 2. Python环境设置

- 创建虚拟环境：`/opt/audio-processing-system/venv`
- 安装离线Python包
- 配置应用程序文件

### 3. 系统服务配置

- 创建systemd服务文件
- 设置自动启动
- 配置用户权限

## 故障排除

### 问题：系统依赖安装失败

**现象：**
```
[ERROR] 无法检测操作系统
```
或
```
[WARNING] 未找到系统依赖安装脚本，请手动安装
```

**解决方案：**

1. **检查文件完整性：**
   ```bash
   # 验证离线包完整性
   python3 scripts/verify_dependencies.py manifest.json
   ```

2. **手动安装系统依赖：**
   
   **Ubuntu/Debian:**
   ```bash
   sudo apt-get update
   sudo apt-get install python3-dev portaudio19-dev libasound2-dev \
       libsndfile1-dev libfftw3-dev ffmpeg gcc g++ make pkg-config
   ```
   
   **CentOS/RHEL:**
   ```bash
   sudo yum update
   sudo yum groupinstall "Development Tools"
   sudo yum install python3-devel portaudio-devel alsa-lib-devel \
       libsndfile-devel fftw-devel ffmpeg
   ```
   
   **macOS:**
   ```bash
   # 安装Homebrew（如果尚未安装）
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   
   # 安装系统依赖
   brew install portaudio libsndfile fftw ffmpeg python@3.10
   
   # 安装开发工具
   xcode-select --install
   ```

3. **重新运行安装：**
   ```bash
   # Linux
   sudo ./scripts/install_offline.sh
   
   # macOS
   ./scripts/install_offline.sh
   ```

### 问题：Python包安装失败

**现象：**
```
ERROR: 未找到架构 xxx 的Python包目录
```

**解决方案：**

1. **检查架构匹配：**
   ```bash
   uname -m  # 查看当前架构
   ls python_packages/  # 查看可用架构
   ```

2. **使用通用包目录：**
   ```bash
   # 如果有python_packages目录但没有架构子目录
   mkdir -p python_packages/$(uname -m)
   mv python_packages/*.whl python_packages/$(uname -m)/
   ```

### 问题：权限错误

**现象：**
```
Permission denied
```

**解决方案：**

1. **Linux系统使用sudo运行：**
   ```bash
   sudo ./scripts/install_offline.sh
   ```

2. **macOS系统直接运行：**
   ```bash
   ./scripts/install_offline.sh
   ```

3. **检查文件权限：**
   ```bash
   chmod +x scripts/install_offline.sh
   chmod +x scripts/install_system_deps.sh
   ```

4. **macOS特殊情况：**
   如果遇到"无法验证开发者"的错误：
   ```bash
   # 允许执行未签名的脚本
   sudo spctl --master-disable
   # 或者在系统偏好设置 > 安全性与隐私中允许
   ```

## macOS特殊说明

### 安装目录
- **Linux**: `/opt/audio-processing-system`
- **macOS**: `/usr/local/audio-processing-system`

### 数据目录
- **Linux**: `/var/lib/audio-processing`
- **macOS**: `~/Library/Application Support/audio-processing`

### 服务管理
macOS不使用systemd，需要手动启动服务：

```bash
# 进入安装目录
cd /usr/local/audio-processing-system

# 激活虚拟环境
source venv/bin/activate

# 启动服务
python3 src/main.py
```

### 自动启动（可选）
创建LaunchAgent配置文件：

```bash
# 创建配置文件
cat > ~/Library/LaunchAgents/com.audio-processing.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.audio-processing</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/audio-processing-system/venv/bin/python3</string>
        <string>/usr/local/audio-processing-system/src/main.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

# 加载服务
launchctl load ~/Library/LaunchAgents/com.audio-processing.plist
```

## 验证安装

### 1. 检查服务状态

**Linux系统：**
```bash
# 检查服务状态
sudo systemctl status audio-processing

# 启动服务
sudo systemctl start audio-processing

# 查看日志
sudo journalctl -u audio-processing -f
```

**macOS系统：**
```bash
# 检查LaunchAgent状态
launchctl list | grep audio-processing

# 手动启动服务
cd /usr/local/audio-processing-system
source venv/bin/activate
python3 src/main.py
```

### 2. 测试功能

**Linux系统：**
```bash
# 进入安装目录
cd /opt/audio-processing-system

# 激活虚拟环境
source venv/bin/activate

# 测试导入
python3 -c "
import sys
sys.path.insert(0, 'src')
import audio_processing
print('✓ 系统安装成功')
"
```

**macOS系统：**
```bash
# 进入安装目录
cd /usr/local/audio-processing-system

# 激活虚拟环境
source venv/bin/activate

# 测试导入
python3 -c "
import sys
sys.path.insert(0, 'src')
import audio_processing
print('✓ 系统安装成功')
"
```

### 3. Web界面访问

打开浏览器访问：`http://localhost` 或 `http://服务器IP`

## 卸载

**Linux系统：**
```bash
# 停止服务
sudo systemctl stop audio-processing
sudo systemctl disable audio-processing

# 删除服务文件
sudo rm /etc/systemd/system/audio-processing.service
sudo systemctl daemon-reload

# 删除安装目录
sudo rm -rf /opt/audio-processing-system
sudo rm -rf /var/lib/audio-processing
sudo rm -rf /var/run/audio-processing
```

**macOS系统：**
```bash
# 停止LaunchAgent服务
launchctl unload ~/Library/LaunchAgents/com.audio-processing.plist
rm ~/Library/LaunchAgents/com.audio-processing.plist

# 删除安装目录
rm -rf /usr/local/audio-processing-system
rm -rf ~/Library/Application\ Support/audio-processing
rm -rf /tmp/audio-processing
```

## 技术支持

如果遇到其他问题，请：

1. 查看安装日志：`/opt/audio-processing-system/logs/`
2. 检查系统日志：`sudo journalctl -u audio-processing`
3. 验证依赖完整性：`python3 scripts/verify_dependencies.py manifest.json`

## 更新说明

- **v1.0.0**: 初始版本，支持基本离线安装
- 修复了系统依赖脚本查找逻辑
- 改进了Python包目录查找机制
- 增强了错误处理和用户提示