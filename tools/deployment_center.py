#!/usr/bin/env python3
"""
部署管理中心
Deployment Management Center

统一的批量部署和设备管理工具
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
import argparse
import logging
from dataclasses import dataclass, asdict
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class DeploymentTarget:
    """部署目标"""
    device_id: str
    hostname: str
    ip_address: str
    location: str
    device_type: str = "classroom_terminal"
    ssh_user: str = "root"
    ssh_key: Optional[str] = None

@dataclass
class DeploymentResult:
    """部署结果"""
    device_id: str
    success: bool
    start_time: str
    end_time: str
    duration: float
    message: str
    error: Optional[str] = None

class DeploymentCenter:
    """部署管理中心"""
    
    def __init__(self, config_dir: str = "deployment_center"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 子目录
        self.templates_dir = self.config_dir / "templates"
        self.scripts_dir = self.config_dir / "scripts"
        self.reports_dir = self.config_dir / "reports"
        self.logs_dir = self.config_dir / "logs"
        
        for dir_path in [self.templates_dir, self.scripts_dir, self.reports_dir, self.logs_dir]:
            dir_path.mkdir(exist_ok=True)
        
        # 设备注册表
        self.devices_file = self.config_dir / "devices.json"
        self.devices = self._load_devices()
    
    def _load_devices(self) -> Dict[str, DeploymentTarget]:
        """加载设备列表"""
        if self.devices_file.exists():
            try:
                with open(self.devices_file, 'r', encoding='utf-8') as f:
                    devices_data = json.load(f)
                return {
                    device_id: DeploymentTarget(**device_info)
                    for device_id, device_info in devices_data.items()
                }
            except Exception as e:
                logger.warning(f"加载设备列表失败: {e}")
        
        return {}
    
    def _save_devices(self):
        """保存设备列表"""
        devices_data = {
            device_id: asdict(device)
            for device_id, device in self.devices.items()
        }
        
        with open(self.devices_file, 'w', encoding='utf-8') as f:
            json.dump(devices_data, f, indent=2, ensure_ascii=False)
    
    def register_device(self, device: DeploymentTarget):
        """注册设备"""
        self.devices[device.device_id] = device
        self._save_devices()
        logger.info(f"设备已注册: {device.device_id} ({device.hostname})")
    
    def create_deployment_script(self, script_name: str, 
                               template_type: str = "audio_system") -> str:
        """创建部署脚本"""
        if template_type == "audio_system":
            script_content = '''#!/bin/bash
# 音频处理系统部署脚本

set -e

echo "开始音频系统部署..."

# 检查系统状态
systemctl stop audio-processing || true
systemctl stop audio-processing-web || true

# 备份配置
mkdir -p /opt/audio-processing-system/backups
cp -r /opt/audio-processing-system/config /opt/audio-processing-system/backups/config_$(date +%Y%m%d_%H%M%S) 2>/dev/null || true

# 硬件检测和配置
cd /opt/audio-processing-system
python3 tools/hardware_detector.py --output device_profiles --power-profile balanced
python3 tools/terminal_device_adapter.py --classroom auto --power auto

# 重启服务
systemctl daemon-reload
systemctl enable audio-processing
systemctl start audio-processing
systemctl enable audio-processing-web
systemctl start audio-processing-web

# 验证部署
sleep 5
if systemctl is-active --quiet audio-processing; then
    echo "✓ 音频处理服务启动成功"
else
    echo "✗ 音频处理服务启动失败"
    exit 1
fi

if curl -f http://localhost/health >/dev/null 2>&1; then
    echo "✓ Web界面可访问"
else
    echo "⚠ Web界面暂时不可访问"
fi

echo "音频系统部署完成"
'''
        elif template_type == "system_update":
            script_content = '''#!/bin/bash
# 系统更新脚本

set -e

echo "开始系统更新..."

# 更新系统包
if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get upgrade -y
elif command -v yum >/dev/null 2>&1; then
    yum update -y
fi

# 更新Python依赖
cd /opt/audio-processing-system
source venv/bin/activate
pip install --upgrade -r requirements.txt

echo "系统更新完成"
'''
        else:
            script_content = '''#!/bin/bash
# 通用部署脚本

set -e

echo "开始部署..."
echo "部署完成"
'''
        
        script_file = self.scripts_dir / f"{script_name}.sh"
        with open(script_file, 'w') as f:
            f.write(script_content)
        
        script_file.chmod(0o755)
        
        logger.info(f"部署脚本已创建: {script_file}")
        return str(script_file)
    
    def deploy_to_device(self, device_id: str, script_path: str) -> DeploymentResult:
        """部署到单个设备"""
        if device_id not in self.devices:
            return DeploymentResult(
                device_id=device_id,
                success=False,
                start_time=datetime.now().isoformat(),
                end_time=datetime.now().isoformat(),
                duration=0.0,
                message="设备未注册",
                error="Device not found in registry"
            )
        
        device = self.devices[device_id]
        start_time = datetime.now()
        
        try:
            logger.info(f"开始部署到设备: {device_id} ({device.ip_address})")
            
            # 构建SSH命令
            ssh_cmd = [
                "ssh",
                "-o", "ConnectTimeout=30",
                "-o", "StrictHostKeyChecking=no"
            ]
            
            if device.ssh_key:
                ssh_cmd.extend(["-i", device.ssh_key])
            
            ssh_cmd.append(f"{device.ssh_user}@{device.ip_address}")
            
            # 上传脚本
            scp_cmd = ["scp", "-o", "StrictHostKeyChecking=no"]
            if device.ssh_key:
                scp_cmd.extend(["-i", device.ssh_key])
            
            remote_script = f"/tmp/deploy_{int(time.time())}.sh"
            scp_cmd.extend([script_path, f"{device.ssh_user}@{device.ip_address}:{remote_script}"])
            
            # 执行上传
            result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                raise Exception(f"脚本上传失败: {result.stderr}")
            
            # 执行脚本
            exec_cmd = ssh_cmd + [f"chmod +x {remote_script} && {remote_script} && rm -f {remote_script}"]
            result = subprocess.run(exec_cmd, capture_output=True, text=True, timeout=300)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            if result.returncode == 0:
                logger.info(f"设备部署成功: {device_id} ({duration:.1f}s)")
                return DeploymentResult(
                    device_id=device_id,
                    success=True,
                    start_time=start_time.isoformat(),
                    end_time=end_time.isoformat(),
                    duration=duration,
                    message=result.stdout,
                    error=None
                )
            else:
                logger.error(f"设备部署失败: {device_id}")
                return DeploymentResult(
                    device_id=device_id,
                    success=False,
                    start_time=start_time.isoformat(),
                    end_time=end_time.isoformat(),
                    duration=duration,
                    message=result.stdout,
                    error=result.stderr
                )
        
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.error(f"设备部署异常: {device_id} - {e}")
            return DeploymentResult(
                device_id=device_id,
                success=False,
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
                duration=duration,
                message="",
                error=str(e)
            )
    
    def batch_deploy(self, device_ids: List[str], script_path: str) -> Dict[str, DeploymentResult]:
        """批量部署"""
        logger.info(f"开始批量部署到 {len(device_ids)} 个设备")
        
        results = {}
        
        for device_id in device_ids:
            result = self.deploy_to_device(device_id, script_path)
            results[device_id] = result
        
        # 统计结果
        success_count = sum(1 for r in results.values() if r.success)
        logger.info(f"批量部署完成: {success_count}/{len(device_ids)} 成功")
        
        return results
    
    def generate_deployment_report(self, results: Dict[str, DeploymentResult]) -> str:
        """生成部署报告"""
        report_data = {
            "deployment_summary": {
                "total_devices": len(results),
                "successful_deployments": sum(1 for r in results.values() if r.success),
                "failed_deployments": sum(1 for r in results.values() if not r.success),
                "total_duration": sum(r.duration for r in results.values()),
                "generated_at": datetime.now().isoformat()
            },
            "results": [asdict(result) for result in results.values()]
        }
        
        report_file = self.reports_dir / f"deployment_report_{int(time.time())}.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"部署报告已生成: {report_file}")
        return str(report_file)
    
    def list_devices(self) -> List[Dict[str, Any]]:
        """列出所有设备"""
        return [
            {
                "device_id": device.device_id,
                "hostname": device.hostname,
                "ip_address": device.ip_address,
                "location": device.location,
                "device_type": device.device_type
            }
            for device in self.devices.values()
        ]
    
    def get_device_status(self, device_id: str) -> Dict[str, Any]:
        """获取设备状态"""
        if device_id not in self.devices:
            return {"error": "Device not found"}
        
        device = self.devices[device_id]
        
        try:
            # 简单的ping测试
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "3", device.ip_address],
                capture_output=True, text=True, timeout=10
            )
            
            online = result.returncode == 0
            
            return {
                "device_id": device_id,
                "hostname": device.hostname,
                "ip_address": device.ip_address,
                "online": online,
                "last_check": datetime.now().isoformat()
            }
        
        except Exception as e:
            return {
                "device_id": device_id,
                "online": False,
                "error": str(e),
                "last_check": datetime.now().isoformat()
            }

def main():
    parser = argparse.ArgumentParser(description="部署管理中心")
    parser.add_argument("--register", action="store_true",
                       help="注册新设备")
    parser.add_argument("--device-id", help="设备ID")
    parser.add_argument("--hostname", help="主机名")
    parser.add_argument("--ip", help="IP地址")
    parser.add_argument("--location", help="位置")
    parser.add_argument("--ssh-key", help="SSH密钥文件")
    
    parser.add_argument("--deploy", action="store_true",
                       help="执行部署")
    parser.add_argument("--script-type", default="audio_system",
                       choices=["audio_system", "system_update", "custom"],
                       help="脚本类型")
    parser.add_argument("--script-path", help="自定义脚本路径")
    parser.add_argument("--targets", help="目标设备ID列表（逗号分隔）")
    
    parser.add_argument("--list-devices", action="store_true",
                       help="列出所有设备")
    parser.add_argument("--status", help="查看设备状态")
    
    parser.add_argument("--config-dir", default="deployment_center",
                       help="配置目录")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    center = DeploymentCenter(args.config_dir)
    
    try:
        if args.register:
            # 注册设备
            if not all([args.device_id, args.hostname, args.ip]):
                print("注册设备需要提供: --device-id, --hostname, --ip")
                sys.exit(1)
            
            device = DeploymentTarget(
                device_id=args.device_id,
                hostname=args.hostname,
                ip_address=args.ip,
                location=args.location or "",
                ssh_key=args.ssh_key
            )
            
            center.register_device(device)
            print(f"✓ 设备已注册: {args.device_id}")
        
        elif args.deploy:
            # 执行部署
            if not args.targets:
                print("请指定目标设备: --targets device1,device2,...")
                sys.exit(1)
            
            device_ids = [d.strip() for d in args.targets.split(',')]
            
            # 创建或使用脚本
            if args.script_path:
                script_path = args.script_path
            else:
                script_path = center.create_deployment_script(
                    f"deploy_{int(time.time())}", 
                    args.script_type
                )
            
            print(f"开始部署到 {len(device_ids)} 个设备...")
            results = center.batch_deploy(device_ids, script_path)
            
            # 生成报告
            report_path = center.generate_deployment_report(results)
            
            # 显示结果
            success_count = sum(1 for r in results.values() if r.success)
            print(f"\n部署完成: {success_count}/{len(device_ids)} 成功")
            print(f"报告: {report_path}")
        
        elif args.list_devices:
            # 列出设备
            devices = center.list_devices()
            if devices:
                print(f"已注册设备 ({len(devices)} 个):")
                for device in devices:
                    print(f"  {device['device_id']}: {device['hostname']} ({device['ip_address']}) - {device['location']}")
            else:
                print("没有已注册的设备")
        
        elif args.status:
            # 查看设备状态
            status = center.get_device_status(args.status)
            print(json.dumps(status, indent=2, ensure_ascii=False))
        
        else:
            parser.print_help()
    
    except Exception as e:
        logger.error(f"操作失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()