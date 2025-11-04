#!/bin/bash
# macOS离线安装测试脚本

set -e

echo "=========================================="
echo "    macOS音频处理系统安装测试"
echo "=========================================="

# 检查安装目录
INSTALL_DIR="/usr/local/audio-processing-system"
if [[ -d "$INSTALL_DIR" ]]; then
    echo "✓ 安装目录存在: $INSTALL_DIR"
else
    echo "✗ 安装目录不存在: $INSTALL_DIR"
    exit 1
fi

# 检查虚拟环境
if [[ -f "$INSTALL_DIR/venv/bin/activate" ]]; then
    echo "✓ Python虚拟环境存在"
else
    echo "✗ Python虚拟环境不存在"
    exit 1
fi

# 检查源代码
if [[ -d "$INSTALL_DIR/src" ]]; then
    echo "✓ 源代码目录存在"
else
    echo "✗ 源代码目录不存在"
    exit 1
fi

# 测试Python环境
echo
echo "测试Python环境..."
cd "$INSTALL_DIR"
source venv/bin/activate

# 检查Python版本
PYTHON_VERSION=$(python3 --version)
echo "✓ Python版本: $PYTHON_VERSION"

# 测试关键依赖
echo "测试关键依赖..."
python3 -c "import numpy; print('✓ numpy:', numpy.__version__)" || echo "✗ numpy导入失败"
python3 -c "import scipy; print('✓ scipy:', scipy.__version__)" || echo "✗ scipy导入失败"
python3 -c "import fastapi; print('✓ fastapi:', fastapi.__version__)" || echo "✗ fastapi导入失败"

# 测试核心模块（如果存在）
if [[ -f "src/audio_processing/__init__.py" ]]; then
    python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    import audio_processing
    print('✓ 核心模块导入成功')
except ImportError as e:
    print('✗ 核心模块导入失败:', e)
"
else
    echo "ℹ 核心模块文件不存在，跳过测试"
fi

# 检查数据目录
DATA_DIR="$HOME/Library/Application Support/audio-processing"
if [[ -d "$DATA_DIR" ]]; then
    echo "✓ 数据目录存在: $DATA_DIR"
else
    echo "ℹ 数据目录不存在，将在首次运行时创建"
fi

echo
echo "=========================================="
echo "✓ macOS安装测试完成！"
echo "=========================================="
echo
echo "启动服务："
echo "cd $INSTALL_DIR"
echo "source venv/bin/activate"
echo "python3 src/main.py"
echo