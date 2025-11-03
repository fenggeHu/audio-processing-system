#!/usr/bin/env python3
"""
设备状态监控和远程管理工具
Device Status Monitoring and Remote Management Tool

提供实时设备状态监控、远程管理和故障诊断功能
"""

import os
import sys
import json
import time
import socket
import threading
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import argparse
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import psutil

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class DeviceStatus:
    """设备状态"""
    device_id: str
    hostname: str
    ip_address: str
    status: str  # online/offline/warning/error
    last_seen: str
    uptime: float
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    audio_status: str
    service_status: Dict[str, str]
    alerts: List[str]

@dataclass
class AudioSystemStatus:
    """音频系统状态"""
    is_running: bool
    latency_ms: float
    dropout_count: int
    input_level_db: float
    output_level_db: float
    processing_load: float
    active_services: List[str]
    error_count: int
    last_error: Optional[str]

@dataclass
class SystemAlert:
    """系统告警"""
    alert_id: str
    device_id: str
    severity: str  # info/warning/error/critical
    category: str  # system/audio/network/storage
    message: str
    timestamp: str
    acknowledged: bool = False

class DeviceMonitor:
    """设备监控器"""
    
    def __init__(self, config_file: str = None):
        self.devices = {}
        self.alerts = []
        self.monitoring_active = False
        self.alert_handlers = []
        
        # 加载配置
        self.config = self._load_config(config_file)
        
        # 监控阈值
        self.thresholds = {
            "cpu_warning": 70.0,
            "cpu_critical": 90.0,
            "memory_warning": 80.0,
            "memory_critical": 95.0,
            "disk_warning": 85.0,
            "disk_critical": 95.0,
            "latency_warning": 50.0,
            "latency_critical": 100.0,
            "dropout_warning": 5,
            "dropout_critical": 20
        }
    
    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """加载监控配置"""
        default_config = {
            "monitoring_interval": 30,
            "alert_retention_hours": 24,
            "auto_recovery": True,
            "remote_management": {
                "enabled": True,
                "port": 8080,
                "auth_required": False
            },
            "notifications": {
                "email": {"enabled": False},
                "webhook": {"enabled": False, "url": ""},
                "log": {"enabled": True}
            }
        }
        
        if config_file and Path(config_file).exists():
            try:
                with open(config_file) as f:
                    user_config = json.load(f)
                default_config.update(user_config)
            except Exception as e:
                logger.warning(f"加载配置文件失败: {e}")
        
        return default_config
    
    def register_device(self, device_id: str, hostname: str, ip_address: str):
        """注册设备"""
        logger.info(f"注册设备: {device_id} ({hostname})")
        
        self.devices[device_id] = DeviceStatus(
            device_id=device_id,
            hostname=hostname,
            ip_address=ip_address,
            status="unknown",
            last_seen=datetime.now().isoformat(),
            uptime=0.0,
            cpu_usage=0.0,
            memory_usage=0.0,
            disk_usage=0.0,
            audio_status="unknown",
            service_status={},
            alerts=[]
        )
    
    def update_device_status(self, device_id: str, status_data: Dict[str, Any]):
        """更新设备状态"""
        if device_id not in self.devices:
            logger.warning(f"未知设备: {device_id}")
            return
        
        device = self.devices[device_id]
        
        # 更新基本状态
        device.status = status_data.get("status", "unknown")
        device.last_seen = datetime.now().isoformat()
        device.uptime = status_data.get("uptime", 0.0)
        device.cpu_usage = status_data.get("cpu_usage", 0.0)
        device.memory_usage = status_data.get("memory_usage", 0.0)
        device.disk_usage = status_data.get("disk_usage", 0.0)
        device.audio_status = status_data.get("audio_status", "unknown")
        device.service_status = status_data.get("service_status", {})
        
        # 检查告警条件
        self._check_device_alerts(device)
    
    def _check_device_alerts(self, device: DeviceStatus):
        """检查设备告警条件"""
        alerts = []
        
        # CPU使用率告警
        if device.cpu_usage >= self.thresholds["cpu_critical"]:
            alerts.append(self._create_alert(
                device.device_id, "critical", "system",
                f"CPU使用率过高: {device.cpu_usage:.1f}%"
            ))
        elif device.cpu_usage >= self.thresholds["cpu_warning"]:
            alerts.append(self._create_alert(
                device.device_id, "warning", "system",
                f"CPU使用率较高: {device.cpu_usage:.1f}%"
            ))
        
        # 内存使用率告警
        if device.memory_usage >= self.thresholds["memory_critical"]:
            alerts.append(self._create_alert(
                device.device_id, "critical", "system",
                f"内存使用率过高: {device.memory_usage:.1f}%"
            ))
        elif device.memory_usage >= self.thresholds["memory_warning"]:
            alerts.append(self._create_alert(
                device.device_id, "warning", "system",
                f"内存使用率较高: {device.memory_usage:.1f}%"
            ))
        
        # 磁盘使用率告警
        if device.disk_usage >= self.thresholds["disk_critical"]:
            alerts.append(self._create_alert(
                device.device_id, "critical", "storage",
                f"磁盘使用率过高: {device.disk_usage:.1f}%"
            ))
        elif device.disk_usage >= self.thresholds["disk_warning"]:
            alerts.append(self._create_alert(
                device.device_id, "warning", "storage",
                f"磁盘使用率较高: {device.disk_usage:.1f}%"
            ))
        
        # 服务状态告警
        for service, status in device.service_status.items():
            if status != "running":
                alerts.append(self._create_alert(
                    device.device_id, "error", "audio",
                    f"服务 {service} 状态异常: {status}"
                ))
        
        # 处理新告警
        for alert in alerts:
            self._handle_alert(alert)
    
    def _create_alert(self, device_id: str, severity: str, 
                     category: str, message: str) -> SystemAlert:
        """创建系统告警"""
        alert_id = f"{device_id}_{category}_{int(time.time())}"
        
        return SystemAlert(
            alert_id=alert_id,
            device_id=device_id,
            severity=severity,
            category=category,
            message=message,
            timestamp=datetime.now().isoformat()
        )
    
    def _handle_alert(self, alert: SystemAlert):
        """处理告警"""
        # 检查是否是重复告警
        existing_alerts = [a for a in self.alerts 
                          if a.device_id == alert.device_id 
                          and a.category == alert.category 
                          and a.message == alert.message]
        
        if existing_alerts:
            return  # 避免重复告警
        
        self.alerts.append(alert)
        logger.warning(f"新告警: [{alert.severity}] {alert.device_id} - {alert.message}")
        
        # 发送通知
        self._send_notification(alert)
        
        # 自动恢复尝试
        if self.config.get("auto_recovery", False):
            self._attempt_auto_recovery(alert)
    
    def _send_notification(self, alert: SystemAlert):
        """发送告警通知"""
        notifications = self.config.get("notifications", {})
        
        # 日志通知
        if notifications.get("log", {}).get("enabled", True):
            logger.error(f"ALERT: {alert.message}")
        
        # 邮件通知
        if notifications.get("email", {}).get("enabled", False):
            self._send_email_notification(alert)
        
        # Webhook通知
        if notifications.get("webhook", {}).get("enabled", False):
            self._send_webhook_notification(alert)
    
    def _send_email_notification(self, alert: SystemAlert):
        """发送邮件通知"""
        # 邮件通知实现
        pass
    
    def _send_webhook_notification(self, alert: SystemAlert):
        """发送Webhook通知"""
        # Webhook通知实现
        pass
    
    def _attempt_auto_recovery(self, alert: SystemAlert):
        """尝试自动恢复"""
        logger.info(f"尝试自动恢复: {alert.device_id} - {alert.category}")
        
        if alert.category == "audio":
            # 音频服务恢复
            self._recover_audio_service(alert.device_id)
        elif alert.category == "system":
            # 系统资源恢复
            self._recover_system_resources(alert.device_id)
    
    def _recover_audio_service(self, device_id: str):
        """恢复音频服务"""
        try:
            # 重启音频处理服务
            result = subprocess.run(
                ["systemctl", "restart", "audio-processing"],
                capture_output=True, text=True
            )
            
            if result.returncode == 0:
                logger.info(f"音频服务重启成功: {device_id}")
            else:
                logger.error(f"音频服务重启失败: {device_id}")
        except Exception as e:
            logger.error(f"音频服务恢复失败: {e}")
    
    def _recover_system_resources(self, device_id: str):
        """恢复系统资源"""
        try:
            # 清理系统缓存
            subprocess.run(["sync"], check=True)
            subprocess.run(["echo", "3", ">", "/proc/sys/vm/drop_caches"], shell=True)
            
            logger.info(f"系统资源清理完成: {device_id}")
        except Exception as e:
            logger.error(f"系统资源恢复失败: {e}")
    
    def get_local_device_status(self) -> Dict[str, Any]:
        """获取本地设备状态"""
        try:
            # 系统信息
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # 网络信息
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)
            
            # 系统运行时间
            uptime = time.time() - psutil.boot_time()
            
            # 音频系统状态
            audio_status = self._get_audio_system_status()
            
            # 服务状态
            service_status = self._get_service_status()
            
            return {
                "hostname": hostname,
                "ip_address": ip_address,
                "status": "online",
                "uptime": uptime,
                "cpu_usage": cpu_percent,
                "memory_usage": memory.percent,
                "disk_usage": disk.percent,
                "audio_status": audio_status,
                "service_status": service_status,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"获取本地设备状态失败: {e}")
            return {"status": "error", "error": str(e)}
    
    def _get_audio_system_status(self) -> str:
        """获取音频系统状态"""
        try:
            # 检查音频处理服务
            result = subprocess.run(
                ["systemctl", "is-active", "audio-processing"],
                capture_output=True, text=True
            )
            
            if result.returncode == 0 and result.stdout.strip() == "active":
                return "running"
            else:
                return "stopped"
        except Exception:
            return "unknown"
    
    def _get_service_status(self) -> Dict[str, str]:
        """获取服务状态"""
        services = [
            "audio-processing",
            "audio-processing-web",
            "nginx"
        ]
        
        status = {}
        
        for service in services:
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True, text=True
                )
                
                if result.returncode == 0:
                    status[service] = result.stdout.strip()
                else:
                    status[service] = "inactive"
            except Exception:
                status[service] = "unknown"
        
        return status
    
    def start_monitoring(self):
        """开始监控"""
        logger.info("开始设备监控...")
        self.monitoring_active = True
        
        # 注册本地设备
        local_status = self.get_local_device_status()
        device_id = f"{local_status['hostname']}_{local_status['ip_address']}"
        self.register_device(device_id, local_status['hostname'], local_status['ip_address'])
        
        # 监控循环
        while self.monitoring_active:
            try:
                # 更新本地设备状态
                status = self.get_local_device_status()
                self.update_device_status(device_id, status)
                
                # 清理过期告警
                self._cleanup_old_alerts()
                
                # 等待下一次监控
                time.sleep(self.config.get("monitoring_interval", 30))
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                time.sleep(10)
        
        logger.info("设备监控已停止")
    
    def _cleanup_old_alerts(self):
        """清理过期告警"""
        retention_hours = self.config.get("alert_retention_hours", 24)
        cutoff_time = datetime.now() - timedelta(hours=retention_hours)
        
        old_count = len(self.alerts)
        self.alerts = [
            alert for alert in self.alerts
            if datetime.fromisoformat(alert.timestamp) > cutoff_time
        ]
        
        if len(self.alerts) < old_count:
            logger.debug(f"清理了 {old_count - len(self.alerts)} 个过期告警")
    
    def get_monitoring_summary(self) -> Dict[str, Any]:
        """获取监控摘要"""
        active_alerts = [a for a in self.alerts if not a.acknowledged]
        
        alert_counts = {
            "critical": len([a for a in active_alerts if a.severity == "critical"]),
            "error": len([a for a in active_alerts if a.severity == "error"]),
            "warning": len([a for a in active_alerts if a.severity == "warning"]),
            "info": len([a for a in active_alerts if a.severity == "info"])
        }
        
        device_summary = {}
        for device_id, device in self.devices.items():
            device_summary[device_id] = {
                "status": device.status,
                "last_seen": device.last_seen,
                "cpu_usage": device.cpu_usage,
                "memory_usage": device.memory_usage,
                "audio_status": device.audio_status
            }
        
        return {
            "monitoring_active": self.monitoring_active,
            "device_count": len(self.devices),
            "alert_counts": alert_counts,
            "devices": device_summary,
            "generated_at": datetime.now().isoformat()
        }
    
    def export_monitoring_data(self, output_path: str) -> str:
        """导出监控数据"""
        data = {
            "devices": {k: asdict(v) for k, v in self.devices.items()},
            "alerts": [asdict(a) for a in self.alerts],
            "summary": self.get_monitoring_summary(),
            "config": self.config
        }
        
        output_file = Path(output_path) / f"monitoring_data_{int(time.time())}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"监控数据已导出: {output_file}")
        return str(output_file)

def main():
    parser = argparse.ArgumentParser(description="设备状态监控和远程管理工具")
    parser.add_argument("--config", "-c", help="配置文件路径")
    parser.add_argument("--monitor", "-m", action="store_true",
                       help="启动监控模式")
    parser.add_argument("--status", "-s", action="store_true",
                       help="显示当前状态")
    parser.add_argument("--export", "-e", help="导出监控数据到指定目录")
    parser.add_argument("--interval", "-i", type=int, default=30,
                       help="监控间隔（秒）")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    monitor = DeviceMonitor(args.config)
    
    try:
        if args.status:
            # 显示当前状态
            status = monitor.get_local_device_status()
            print(json.dumps(status, indent=2, ensure_ascii=False))
        
        elif args.export:
            # 导出监控数据
            export_path = monitor.export_monitoring_data(args.export)
            print(f"✓ 监控数据已导出: {export_path}")
        
        elif args.monitor:
            # 启动监控
            print("启动设备监控 (Ctrl+C 停止)...")
            monitor.start_monitoring()
        
        else:
            # 显示摘要信息
            summary = monitor.get_monitoring_summary()
            print("设备监控摘要:")
            print(f"  设备数量: {summary['device_count']}")
            print(f"  告警统计: {summary['alert_counts']}")
            print("\n使用 --monitor 启动监控，--status 查看详细状态")
    
    except KeyboardInterrupt:
        print("\n监控已停止")
    except Exception as e:
        logger.error(f"监控失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()