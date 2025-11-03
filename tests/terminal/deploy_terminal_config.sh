#!/bin/bash
# 终端设备自动配置脚本
# 生成时间: 2025-11-03 11:32:11
# 设备: HuMBP16.local (LOW)

set -e

echo "开始终端设备配置..."

# 设备信息
DEVICE_ID="HuMBP16.local_arm64_1762140730"
DEVICE_NAME="HuMBP16.local (LOW)"
PERFORMANCE_CLASS="low"

echo "设备ID: $DEVICE_ID"
echo "设备名称: $DEVICE_NAME"
echo "性能等级: $PERFORMANCE_CLASS"

# 应用电源配置
echo "应用电源配置..."
python3 /opt/audio-processing-system/tools/power_manager.py \
    --profile classroom \
    --optimize

# 配置音频系统
echo "配置音频系统..."
python3 /opt/audio-processing-system/tools/audio_device_manager.py \
    --classroom-type standard_classroom \
    --target-latency 20.0

# 启动监控
echo "启动设备监控..."
python3 /opt/audio-processing-system/tools/device_monitor.py \
    --monitor &

# 启动音频处理服务
echo "启动音频处理服务..."
systemctl enable audio-processing
systemctl start audio-processing

echo "终端设备配置完成！"
echo "Web界面: http://localhost"
echo "监控状态: systemctl status audio-processing"
