# 音频处理系统部署指南
# Audio Processing System Deployment Guide

## 概述

本目录包含音频处理系统的完整部署解决方案，支持多种部署方式和环境配置。

## 目录结构

```
deploy/
├── README.md                    # 本文件
├── install.sh                   # 自动安装脚本
├── docker-compose.yml           # Docker容器编排
├── maintenance_guide.md         # 系统维护和用户指南
├── docker/                     # Docker相关文件
│   └── Dockerfile              # 应用镜像
├── nginx/                      # Nginx配置
│   ├── nginx.conf              # 主配置文件
│   └── conf.d/                 # 站点配置
├── monitoring/                 # 监控配置
│   ├── prometheus.yml          # Prometheus配置
│   └── alert_rules.yml         # 告警规则

```

## 快速开始

### 方式1: 自动安装脚本 (推荐)

```bash
# 下载并运行安装脚本
curl -fsSL https://raw.githubusercontent.com/audio-processing-system/deploy/main/install.sh | bash

# 或者本地运行
chmod +x deploy/install.sh
sudo deploy/install.sh
```

### 方式2: Docker容器化部署

```bash
# 克隆项目
git clone https://github.com/audio-processing-system/audio-processing-system.git
cd audio-processing-system

# 启动所有服务
docker-compose -f deploy/docker-compose.yml up -d

# 检查服务状态
docker-compose -f deploy/docker-compose.yml ps
```



## 部署环境

### 系统要求

**最低要求**:
- CPU: 4核心 2.0GHz
- 内存: 4GB RAM
- 存储: 20GB 可用空间
- 操作系统: Ubuntu 20.04+ / CentOS 8+ / Debian 11+
- Python: 3.10+

**推荐配置**:
- CPU: 8核心 3.0GHz
- 内存: 8GB RAM
- 存储: 50GB SSD
- 网络: 千兆以太网

### 支持的部署环境

1. **生产环境 (Production)**
   - 高可用性配置
   - 完整监控和告警
   - 自动备份和恢复
   - 安全加固

2. **预发布环境 (Staging)**
   - 生产环境镜像
   - 用于测试和验证
   - 简化的监控配置

3. **开发环境 (Development)**
   - 轻量级配置
   - 调试功能启用
   - 快速迭代支持

## 配置说明

### 环境配置文件

系统使用统一的配置文件：

- `config/audio_system.json`: 主配置文件
- `config/classroom_environments.yaml`: 教室环境配置

### 主要配置项

```json
{
  "system": {
    "environment": "production",
    "debug": false
  },
  "audio": {
    "sample_rate": 48000,
    "channels": 8,
    "frame_size": 480
  },
  "services": {
    "capture": {"enabled": true},
    "ssl": {"enabled": true},
    "beamformer": {"enabled": true},
    "aec": {"enabled": true},
    "denoise": {"enabled": true},
    "agc": {"enabled": true}
  }
}
```

## 部署后验证

### 1. 服务状态检查

```bash
# 检查系统服务
systemctl status audio-processing
systemctl status audio-processing-web
systemctl status nginx

# 或检查Docker服务
docker-compose ps
```

### 2. 功能验证

```bash
# 健康检查
curl http://localhost/health

# API测试
curl http://localhost/api/status

# WebSocket连接测试
wscat -c ws://localhost/ws
```

### 3. 性能测试

```bash
# 运行性能测试
python3 deploy/scripts/performance_test.py

# 检查系统资源
htop
iotop
```

## 监控和维护

### 访问监控界面

- **Web控制界面**: http://localhost
- **Prometheus监控**: http://localhost:9090
- **Grafana仪表板**: http://localhost:3000
- **Kibana日志**: http://localhost:5601

### 日常维护任务

```bash
# 每日健康检查
/opt/audio-processing-system/scripts/daily_check.sh

# 每周维护
/opt/audio-processing-system/scripts/weekly_maintenance.sh

# 配置备份
/opt/audio-processing-system/scripts/backup_config.sh
```

## 故障排除

### 常见问题

1. **服务启动失败**
   ```bash
   # 查看日志
   journalctl -u audio-processing -f
   
   # 检查配置
   python3 -c "import json; json.load(open('/opt/audio-processing-system/config/audio_system.json'))"
   ```

2. **音频设备问题**
   ```bash
   # 检查音频设备
   arecord -l
   aplay -l
   
   # 测试音频
   arecord -D hw:0,0 -f S16_LE -r 48000 -c 2 -d 5 test.wav
   ```

3. **网络连接问题**
   ```bash
   # 检查端口
   netstat -tlnp | grep -E ':(80|8000)'
   
   # 检查防火墙
   ufw status
   ```

### 获取支持

- **技术文档**: 查看 `maintenance_guide.md`
- **日志收集**: 运行 `collect_logs.sh` 脚本
- **问题报告**: 提交到项目Issue页面

## 升级和更新

### 系统升级

```bash
# 备份当前配置
/opt/audio-processing-system/scripts/backup_config.sh

# 下载新版本
wget https://github.com/audio-processing-system/releases/latest/audio-processing-system.tar.gz

# 运行升级脚本
./upgrade.sh
```

### 配置更新

```bash
# 热更新配置
curl -X POST http://localhost/api/config/reload

# 重启服务更新
systemctl restart audio-processing
```

## 安全注意事项

### 网络安全

- 配置防火墙规则
- 启用HTTPS (生产环境)
- 限制API访问权限
- 定期更新系统补丁

### 数据安全

- 定期备份配置和数据
- 加密敏感配置信息
- 监控异常访问行为
- 实施访问控制策略

## 许可证

本部署方案遵循项目主许可证。详情请查看项目根目录的 LICENSE 文件。

## 贡献

欢迎提交部署相关的改进建议和问题报告。请遵循项目的贡献指南。

---

**版本**: v1.0.0  
**更新日期**: 2024年1月  
**维护者**: Audio Processing System Team