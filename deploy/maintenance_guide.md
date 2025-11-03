# 音频处理系统维护指南
# Audio Processing System Maintenance Guide

## 概述

本文档提供音频处理系统的日常维护、故障排除和性能优化指南，确保系统在教室环境中稳定运行。

## 系统架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    监控层 (Monitoring)                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────┐ │
│  │ Prometheus  │ │  Grafana    │ │   Kibana    │ │ Alerts │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └────────┘ │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                    应用层 (Application)                     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────┐ │
│  │ Web UI      │ │ REST API    │ │ WebSocket   │ │ Control│ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └────────┘ │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                    服务层 (Services)                        │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────┐ │
│  │ Audio Proc  │ │ SSL Service │ │ AEC Service │ │ Others │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └────────┘ │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                    基础设施层 (Infrastructure)               │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────┐ │
│  │ Docker      │ │ Nginx       │ │ PostgreSQL  │ │ Redis  │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 日常维护任务

### 1. 系统健康检查

#### 每日检查清单

```bash
#!/bin/bash
# 每日健康检查脚本

echo "=== 音频处理系统健康检查 $(date) ==="

# 1. 检查服务状态
echo "1. 服务状态检查:"
services=("audio-processing" "audio-processing-web" "nginx" "redis" "postgresql")
for service in "${services[@]}"; do
    if systemctl is-active --quiet "$service"; then
        echo "  ✓ $service: 运行正常"
    else
        echo "  ✗ $service: 服务异常"
        systemctl status "$service" --no-pager
    fi
done

# 2. 检查端口监听
echo "2. 端口监听检查:"
ports=("80:Nginx" "8000:Web API" "6379:Redis" "5432:PostgreSQL")
for port_info in "${ports[@]}"; do
    port=$(echo "$port_info" | cut -d: -f1)
    name=$(echo "$port_info" | cut -d: -f2)
    if netstat -tlnp | grep -q ":$port "; then
        echo "  ✓ $name (端口 $port): 正常监听"
    else
        echo "  ✗ $name (端口 $port): 未监听"
    fi
done

# 3. 检查磁盘空间
echo "3. 磁盘空间检查:"
df -h | grep -E "(/$|/opt|/var)" | while read line; do
    usage=$(echo "$line" | awk '{print $5}' | sed 's/%//')
    mount=$(echo "$line" | awk '{print $6}')
    if [ "$usage" -gt 80 ]; then
        echo "  ⚠ $mount: 使用率 ${usage}% (警告)"
    else
        echo "  ✓ $mount: 使用率 ${usage}% (正常)"
    fi
done

# 4. 检查内存使用
echo "4. 内存使用检查:"
memory_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
if (( $(echo "$memory_usage > 80" | bc -l) )); then
    echo "  ⚠ 内存使用率: ${memory_usage}% (警告)"
else
    echo "  ✓ 内存使用率: ${memory_usage}% (正常)"
fi

# 5. 检查CPU负载
echo "5. CPU负载检查:"
load_avg=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')
cpu_cores=$(nproc)
if (( $(echo "$load_avg > $cpu_cores" | bc -l) )); then
    echo "  ⚠ CPU负载: $load_avg (警告，超过核心数 $cpu_cores)"
else
    echo "  ✓ CPU负载: $load_avg (正常，核心数 $cpu_cores)"
fi

# 6. 检查音频设备
echo "6. 音频设备检查:"
if command -v arecord &> /dev/null; then
    device_count=$(arecord -l 2>/dev/null | grep -c "card")
    if [ "$device_count" -gt 0 ]; then
        echo "  ✓ 检测到 $device_count 个音频输入设备"
    else
        echo "  ✗ 未检测到音频输入设备"
    fi
else
    echo "  ⚠ 无法检查音频设备 (arecord 未安装)"
fi

# 7. 检查日志错误
echo "7. 日志错误检查:"
log_files=("/opt/audio-processing-system/logs/application.log" "/var/log/nginx/error.log")
for log_file in "${log_files[@]}"; do
    if [ -f "$log_file" ]; then
        error_count=$(grep -c "ERROR\|CRITICAL" "$log_file" 2>/dev/null || echo "0")
        if [ "$error_count" -gt 0 ]; then
            echo "  ⚠ $log_file: 发现 $error_count 个错误"
        else
            echo "  ✓ $log_file: 无错误记录"
        fi
    fi
done

echo "=== 健康检查完成 ==="
```

#### 每周维护任务

```bash
#!/bin/bash
# 每周维护脚本

echo "=== 音频处理系统每周维护 $(date) ==="

# 1. 清理日志文件
echo "1. 清理旧日志文件..."
find /opt/audio-processing-system/logs -name "*.log.*" -mtime +7 -delete
find /var/log/nginx -name "*.log.*" -mtime +7 -delete
echo "  ✓ 日志清理完成"

# 2. 清理录音文件
echo "2. 清理旧录音文件..."
find /opt/audio-processing-system/recordings -name "*.wav" -mtime +30 -delete
find /opt/audio-processing-system/recordings -name "*.mp3" -mtime +30 -delete
echo "  ✓ 录音文件清理完成"

# 3. 数据库维护
echo "3. 数据库维护..."
sudo -u postgres psql -d audioprocessing -c "VACUUM ANALYZE;"
echo "  ✓ 数据库优化完成"

# 4. 系统更新检查
echo "4. 检查系统更新..."
if command -v apt &> /dev/null; then
    apt list --upgradable 2>/dev/null | grep -v "WARNING" | wc -l
elif command -v yum &> /dev/null; then
    yum check-update --quiet | wc -l
fi
echo "  ✓ 更新检查完成"

# 5. 配置备份
echo "5. 备份配置文件..."
backup_dir="/opt/audio-processing-system/backups/$(date +%Y%m%d)"
mkdir -p "$backup_dir"
cp -r /opt/audio-processing-system/config "$backup_dir/"
cp /etc/nginx/sites-available/audio-processing "$backup_dir/"
cp /etc/systemd/system/audio-processing*.service "$backup_dir/"
echo "  ✓ 配置备份完成: $backup_dir"

echo "=== 每周维护完成 ==="
```

### 2. 性能监控

#### 关键性能指标 (KPIs)

| 指标 | 正常范围 | 警告阈值 | 严重阈值 |
|------|----------|----------|----------|
| 端到端延迟 | < 40ms | > 50ms | > 80ms |
| CPU使用率 | < 60% | > 80% | > 90% |
| 内存使用率 | < 70% | > 85% | > 95% |
| 磁盘使用率 | < 80% | > 90% | > 95% |
| 回声抑制(ERLE) | > 15dB | < 10dB | < 5dB |
| 信噪比(SNR) | > 15dB | < 10dB | < 5dB |

#### 性能监控脚本

```python
#!/usr/bin/env python3
"""
音频系统性能监控脚本
"""

import psutil
import requests
import json
import time
import logging
from datetime import datetime

class PerformanceMonitor:
    def __init__(self):
        self.api_base = "http://localhost:8000"
        self.thresholds = {
            'cpu_warning': 80,
            'cpu_critical': 90,
            'memory_warning': 85,
            'memory_critical': 95,
            'disk_warning': 90,
            'disk_critical': 95,
            'latency_warning': 50,
            'latency_critical': 80
        }
    
    def check_system_resources(self):
        """检查系统资源使用情况"""
        metrics = {}
        
        # CPU使用率
        metrics['cpu_percent'] = psutil.cpu_percent(interval=1)
        
        # 内存使用率
        memory = psutil.virtual_memory()
        metrics['memory_percent'] = memory.percent
        
        # 磁盘使用率
        disk = psutil.disk_usage('/')
        metrics['disk_percent'] = (disk.used / disk.total) * 100
        
        # 网络IO
        net_io = psutil.net_io_counters()
        metrics['network_bytes_sent'] = net_io.bytes_sent
        metrics['network_bytes_recv'] = net_io.bytes_recv
        
        return metrics
    
    def check_audio_metrics(self):
        """检查音频处理指标"""
        try:
            response = requests.get(f"{self.api_base}/metrics", timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logging.error(f"获取音频指标失败: {e}")
        return {}
    
    def check_service_health(self):
        """检查服务健康状态"""
        try:
            response = requests.get(f"{self.api_base}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def generate_alert(self, metric, value, threshold_type):
        """生成告警"""
        timestamp = datetime.now().isoformat()
        alert = {
            'timestamp': timestamp,
            'metric': metric,
            'value': value,
            'threshold_type': threshold_type,
            'message': f"{metric} 达到 {threshold_type} 阈值: {value}"
        }
        
        # 记录到日志
        logging.warning(f"ALERT: {alert['message']}")
        
        # 可以在这里添加邮件、短信等告警通知
        return alert
    
    def monitor(self):
        """执行监控检查"""
        print(f"=== 性能监控检查 {datetime.now()} ===")
        
        # 检查系统资源
        system_metrics = self.check_system_resources()
        print(f"CPU使用率: {system_metrics['cpu_percent']:.1f}%")
        print(f"内存使用率: {system_metrics['memory_percent']:.1f}%")
        print(f"磁盘使用率: {system_metrics['disk_percent']:.1f}%")
        
        # 检查阈值
        alerts = []
        
        if system_metrics['cpu_percent'] > self.thresholds['cpu_critical']:
            alerts.append(self.generate_alert('CPU', system_metrics['cpu_percent'], 'critical'))
        elif system_metrics['cpu_percent'] > self.thresholds['cpu_warning']:
            alerts.append(self.generate_alert('CPU', system_metrics['cpu_percent'], 'warning'))
        
        if system_metrics['memory_percent'] > self.thresholds['memory_critical']:
            alerts.append(self.generate_alert('Memory', system_metrics['memory_percent'], 'critical'))
        elif system_metrics['memory_percent'] > self.thresholds['memory_warning']:
            alerts.append(self.generate_alert('Memory', system_metrics['memory_percent'], 'warning'))
        
        # 检查服务健康
        if self.check_service_health():
            print("✓ 服务健康检查通过")
        else:
            print("✗ 服务健康检查失败")
            alerts.append(self.generate_alert('Service', 'DOWN', 'critical'))
        
        # 检查音频指标
        audio_metrics = self.check_audio_metrics()
        if audio_metrics:
            latency = audio_metrics.get('latency_ms', 0)
            print(f"音频延迟: {latency:.1f}ms")
            
            if latency > self.thresholds['latency_critical']:
                alerts.append(self.generate_alert('Latency', latency, 'critical'))
            elif latency > self.thresholds['latency_warning']:
                alerts.append(self.generate_alert('Latency', latency, 'warning'))
        
        if alerts:
            print(f"⚠ 发现 {len(alerts)} 个告警")
        else:
            print("✓ 所有指标正常")
        
        return alerts

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    monitor = PerformanceMonitor()
    monitor.monitor()
```

## 故障排除指南

### 常见问题及解决方案

#### 1. 服务启动失败

**症状**: systemctl status 显示服务失败
**排查步骤**:

```bash
# 查看服务状态
sudo systemctl status audio-processing

# 查看详细日志
sudo journalctl -u audio-processing -f

# 检查配置文件
python3 -c "import json; json.load(open('/opt/audio-processing-system/config/production.json'))"

# 检查端口占用
sudo netstat -tlnp | grep 8000

# 手动启动测试
cd /opt/audio-processing-system
source venv/bin/activate
python -m audio_processing.main
```

**常见解决方案**:
- 配置文件语法错误: 修复JSON格式
- 端口被占用: 更改端口或停止占用进程
- 权限问题: 检查文件所有权和权限
- 依赖缺失: 重新安装Python依赖

#### 2. 音频设备无法访问

**症状**: 无法检测到音频输入设备
**排查步骤**:

```bash
# 检查音频设备
arecord -l
aplay -l

# 检查ALSA配置
cat /proc/asound/cards

# 检查设备权限
ls -l /dev/snd/

# 检查用户组
groups audiouser
```

**解决方案**:
```bash
# 添加用户到audio组
sudo usermod -a -G audio audiouser

# 重启音频服务
sudo systemctl restart alsa-state
sudo systemctl restart pulseaudio

# 检查设备配置
sudo alsamixer
```

#### 3. 高延迟问题

**症状**: 音频延迟超过50ms
**排查步骤**:

```bash
# 检查系统负载
top
htop

# 检查音频缓冲区设置
cat /opt/audio-processing-system/config/production.json | grep -A5 -B5 buffer

# 检查实时优先级
ps -eo pid,pri,ni,comm | grep audio
```

**优化方案**:
```json
{
  "audio": {
    "frame_size": 240,
    "buffer_size": 1024
  },
  "performance": {
    "optimization_mode": "low_latency"
  }
}
```

#### 4. 回声问题

**症状**: 扬声器声音被麦克风拾取造成回声
**排查步骤**:

```bash
# 检查AEC服务状态
curl http://localhost:8000/services/aec/status

# 查看AEC指标
curl http://localhost:8000/metrics | grep erle

# 检查音频路由
curl http://localhost:8000/audio/routing
```

**解决方案**:
1. 调整AEC参数:
```json
{
  "services": {
    "aec": {
      "config": {
        "filter_length": 512,
        "adaptation_rate": 0.05,
        "erle_target_db": 25.0
      }
    }
  }
}
```

2. 重新校准房间声学:
```bash
curl -X POST http://localhost:8000/calibration/room
```

#### 5. Web界面无法访问

**症状**: 浏览器无法打开Web控制界面
**排查步骤**:

```bash
# 检查Nginx状态
sudo systemctl status nginx

# 检查Nginx配置
sudo nginx -t

# 检查端口监听
sudo netstat -tlnp | grep :80

# 查看Nginx日志
sudo tail -f /var/log/nginx/error.log
```

**解决方案**:
```bash
# 重启Nginx
sudo systemctl restart nginx

# 检查防火墙
sudo ufw status
sudo firewall-cmd --list-all

# 修复权限
sudo chown -R www-data:www-data /var/www/
```

### 紧急恢复程序

#### 系统完全故障恢复

```bash
#!/bin/bash
# 紧急恢复脚本

echo "=== 音频处理系统紧急恢复 ==="

# 1. 停止所有服务
echo "停止所有服务..."
sudo systemctl stop audio-processing-web
sudo systemctl stop audio-processing
sudo systemctl stop nginx

# 2. 检查并修复文件系统
echo "检查文件系统..."
sudo fsck -f /

# 3. 恢复配置文件
echo "恢复配置文件..."
BACKUP_DIR=$(ls -t /opt/audio-processing-system/backups/ | head -1)
if [ -n "$BACKUP_DIR" ]; then
    sudo cp -r "/opt/audio-processing-system/backups/$BACKUP_DIR/config" /opt/audio-processing-system/
    echo "配置文件已从 $BACKUP_DIR 恢复"
fi

# 4. 重置权限
echo "重置文件权限..."
sudo chown -R audiouser:audiouser /opt/audio-processing-system
sudo chmod -R 755 /opt/audio-processing-system

# 5. 重启服务
echo "重启服务..."
sudo systemctl start audio-processing
sleep 5
sudo systemctl start audio-processing-web
sleep 3
sudo systemctl start nginx

# 6. 验证恢复
echo "验证系统恢复..."
if curl -f http://localhost/health &> /dev/null; then
    echo "✓ 系统恢复成功"
else
    echo "✗ 系统恢复失败，需要手动干预"
fi
```

## 性能优化

### 系统级优化

#### 1. 内核参数调优

```bash
# /etc/sysctl.d/99-audio-processing.conf

# 网络优化
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216

# 实时性能优化
kernel.sched_rt_runtime_us = 950000
kernel.sched_rt_period_us = 1000000

# 内存管理
vm.swappiness = 10
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5
```

#### 2. 音频系统优化

```bash
# /etc/security/limits.d/99-audio.conf

@audio - rtprio 95
@audio - memlock unlimited
@audio - nice -10
audiouser - rtprio 95
audiouser - memlock unlimited
audiouser - nice -10
```

#### 3. CPU调度优化

```bash
# 设置CPU调度策略
sudo chrt -f -p 50 $(pgrep -f "audio_processing.main")

# 设置CPU亲和性
sudo taskset -cp 0,1 $(pgrep -f "audio_processing.main")
```

### 应用级优化

#### 1. 配置优化

```json
{
  "performance": {
    "optimization_mode": "low_latency",
    "cpu_limit_percent": 70,
    "memory_limit_mb": 1024,
    "thread_pool_size": 4,
    "async_buffer_size": 1024
  },
  "audio": {
    "frame_size": 240,
    "buffer_size": 1024,
    "sample_rate": 48000,
    "optimization": {
      "use_simd": true,
      "parallel_processing": true,
      "memory_pool": true
    }
  }
}
```

#### 2. 算法优化

```python
# 性能优化配置示例
OPTIMIZATION_CONFIGS = {
    "low_latency": {
        "beamformer": {"algorithm": "DAS", "update_rate": 0.1},
        "aec": {"filter_length": 128, "adaptation_rate": 0.05},
        "denoise": {"strength": "light", "frame_lookahead": 1}
    },
    "high_quality": {
        "beamformer": {"algorithm": "MVDR", "update_rate": 0.01},
        "aec": {"filter_length": 512, "adaptation_rate": 0.01},
        "denoise": {"strength": "aggressive", "frame_lookahead": 3}
    },
    "balanced": {
        "beamformer": {"algorithm": "MVDR", "update_rate": 0.05},
        "aec": {"filter_length": 256, "adaptation_rate": 0.03},
        "denoise": {"strength": "moderate", "frame_lookahead": 2}
    }
}
```

## 安全维护

### 1. 系统安全

```bash
# 定期安全检查脚本
#!/bin/bash

echo "=== 系统安全检查 ==="

# 检查系统更新
echo "1. 检查安全更新..."
if command -v apt &> /dev/null; then
    apt list --upgradable 2>/dev/null | grep -i security
elif command -v yum &> /dev/null; then
    yum --security check-update
fi

# 检查开放端口
echo "2. 检查开放端口..."
nmap -sT -O localhost

# 检查用户登录
echo "3. 检查用户登录..."
last | head -10

# 检查系统日志
echo "4. 检查安全日志..."
grep -i "failed\|error\|denied" /var/log/auth.log | tail -10

# 检查文件权限
echo "5. 检查关键文件权限..."
ls -la /opt/audio-processing-system/config/
ls -la /etc/nginx/sites-available/audio-processing
```

### 2. 应用安全

```bash
# 应用安全检查
#!/bin/bash

echo "=== 应用安全检查 ==="

# 检查API访问日志
echo "1. 检查API访问..."
tail -100 /var/log/nginx/access.log | grep -E "(POST|PUT|DELETE)" | head -10

# 检查异常请求
echo "2. 检查异常请求..."
tail -100 /var/log/nginx/access.log | grep -E "(40[0-9]|50[0-9])" | head -10

# 检查配置文件权限
echo "3. 检查配置文件安全..."
find /opt/audio-processing-system/config -type f -exec ls -la {} \;

# 检查进程权限
echo "4. 检查进程权限..."
ps aux | grep audio-processing
```

## 备份和恢复

### 自动备份脚本

```bash
#!/bin/bash
# 自动备份脚本

BACKUP_BASE="/opt/audio-processing-system/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_BASE/backup_$DATE"

echo "=== 开始备份 $DATE ==="

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 备份配置文件
echo "备份配置文件..."
cp -r /opt/audio-processing-system/config "$BACKUP_DIR/"

# 备份数据库
echo "备份数据库..."
sudo -u postgres pg_dump audioprocessing > "$BACKUP_DIR/database.sql"

# 备份系统配置
echo "备份系统配置..."
mkdir -p "$BACKUP_DIR/system"
cp /etc/nginx/sites-available/audio-processing "$BACKUP_DIR/system/"
cp /etc/systemd/system/audio-processing*.service "$BACKUP_DIR/system/"

# 压缩备份
echo "压缩备份文件..."
tar -czf "$BACKUP_DIR.tar.gz" -C "$BACKUP_BASE" "backup_$DATE"
rm -rf "$BACKUP_DIR"

# 清理旧备份
echo "清理旧备份..."
find "$BACKUP_BASE" -name "backup_*.tar.gz" -mtime +30 -delete

echo "✓ 备份完成: $BACKUP_DIR.tar.gz"
```

### 恢复脚本

```bash
#!/bin/bash
# 系统恢复脚本

if [ $# -ne 1 ]; then
    echo "用法: $0 <备份文件>"
    exit 1
fi

BACKUP_FILE="$1"
RESTORE_DIR="/tmp/restore_$(date +%Y%m%d_%H%M%S)"

echo "=== 开始恢复 ==="

# 解压备份文件
echo "解压备份文件..."
mkdir -p "$RESTORE_DIR"
tar -xzf "$BACKUP_FILE" -C "$RESTORE_DIR"

BACKUP_CONTENT=$(ls "$RESTORE_DIR")

# 停止服务
echo "停止服务..."
sudo systemctl stop audio-processing-web
sudo systemctl stop audio-processing

# 恢复配置文件
echo "恢复配置文件..."
sudo cp -r "$RESTORE_DIR/$BACKUP_CONTENT/config"/* /opt/audio-processing-system/config/

# 恢复数据库
echo "恢复数据库..."
if [ -f "$RESTORE_DIR/$BACKUP_CONTENT/database.sql" ]; then
    sudo -u postgres psql audioprocessing < "$RESTORE_DIR/$BACKUP_CONTENT/database.sql"
fi

# 恢复系统配置
echo "恢复系统配置..."
if [ -d "$RESTORE_DIR/$BACKUP_CONTENT/system" ]; then
    sudo cp "$RESTORE_DIR/$BACKUP_CONTENT/system/audio-processing" /etc/nginx/sites-available/
    sudo cp "$RESTORE_DIR/$BACKUP_CONTENT/system/"*.service /etc/systemd/system/
    sudo systemctl daemon-reload
fi

# 重启服务
echo "重启服务..."
sudo systemctl start audio-processing
sleep 5
sudo systemctl start audio-processing-web

# 清理临时文件
rm -rf "$RESTORE_DIR"

echo "✓ 恢复完成"
```

## 联系支持

### 技术支持信息

- **技术支持邮箱**: support@audio-processing-system.com
- **紧急联系电话**: +86-xxx-xxxx-xxxx
- **在线文档**: https://docs.audio-processing-system.com
- **问题跟踪**: https://github.com/audio-processing-system/issues

### 提交问题时请包含

1. 系统版本信息
2. 错误日志文件
3. 系统配置文件
4. 问题复现步骤
5. 环境信息 (操作系统、硬件配置等)

### 日志收集脚本

```bash
#!/bin/bash
# 日志收集脚本，用于技术支持

SUPPORT_DIR="/tmp/audio-system-support-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SUPPORT_DIR"

echo "收集系统信息用于技术支持..."

# 系统信息
uname -a > "$SUPPORT_DIR/system_info.txt"
lsb_release -a >> "$SUPPORT_DIR/system_info.txt" 2>/dev/null
free -h >> "$SUPPORT_DIR/system_info.txt"
df -h >> "$SUPPORT_DIR/system_info.txt"

# 服务状态
systemctl status audio-processing > "$SUPPORT_DIR/service_status.txt"
systemctl status audio-processing-web >> "$SUPPORT_DIR/service_status.txt"
systemctl status nginx >> "$SUPPORT_DIR/service_status.txt"

# 配置文件
cp -r /opt/audio-processing-system/config "$SUPPORT_DIR/"

# 日志文件
cp /opt/audio-processing-system/logs/*.log "$SUPPORT_DIR/" 2>/dev/null
cp /var/log/nginx/error.log "$SUPPORT_DIR/" 2>/dev/null

# 网络信息
netstat -tlnp > "$SUPPORT_DIR/network_info.txt"

# 音频设备信息
arecord -l > "$SUPPORT_DIR/audio_devices.txt" 2>/dev/null
aplay -l >> "$SUPPORT_DIR/audio_devices.txt" 2>/dev/null

# 打包
tar -czf "$SUPPORT_DIR.tar.gz" -C /tmp "$(basename $SUPPORT_DIR)"
rm -rf "$SUPPORT_DIR"

echo "支持信息已收集到: $SUPPORT_DIR.tar.gz"
echo "请将此文件发送给技术支持团队"
```

---

**注意**: 本维护指南应定期更新，确保与系统版本保持同步。建议每季度审查一次维护程序的有效性。