#!/usr/bin/env python3
"""
批量部署管理器
Batch Deployment Manager

管理多设备的批量配置部署和更新
"""

import os
import sys
import json
import time
import asyncio
import threading
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
import argparse
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
import concurrent.futures
import paramiko
import socket

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
    ssh_port: int = 22
    username: str = "root"
    auth_method: str = "key"  # key/password
    key_file: Optional[str] = None
    password: Optional[str] = None

@dataclass
class DeploymentResult:
    """部署结果"""
    device_id: str
    success: bool
    start_time: str
    end_time: str
    duration: float
    output: str
    error: Optional[str] = None
    exit_code: int = 0

class BatchDeploymentManager:
    """批量部署管理器"""
    
    def __init__(self, config_dir: str = "deployment_config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 部署脚本目录
        self.scripts_dir = self.config_dir / "scripts"
        self.scripts_dir.mkdir(exist_ok=True)
        
        # 日志目录
        self.logs_dir = self.config_dir / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        # 部署任务
        self.active_deployments = {}
        
        # SSH连接池
        self.ssh_connections = {}
    
    def create_deployment_script(self, script_name: str, 
                               commands: List[str]) -> str:
        """创建部署脚本"""
        script_content = f'''#!/bin/bash
# 自动生成的部署脚本: {script_name}
# 生成时间: {datetime.now().isoformat()}

set -e

# 颜色定义
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
NC='\\033[0m'

log_info() {{
    echo -e "${{BLUE}}[INFO]${{NC}} $1"
}}

log_success() {{
    echo -e "${{GREEN}}[SUCCESS]${{NC}} $1"
}}

log_warning() {{
    echo -e "${{YELLOW}}[WARNING]${{NC}} $1"
}}

log_error() {{
    echo -e "${{RED}}[ERROR]${{NC}} $1"
}}

# 部署开始
log_info "开始执行部署脚本: {script_name}"
log_info "目标主机: $(hostname)"
log_info "执行时间: $(date)"

# 执行部署命令
'''
        
        for i, command in enumerate(commands, 1):
            script_content += f'''
log_info "步骤 {i}: {command.split()[0] if command.split() else 'unknown'}"
{command}
if [ $? -eq 0 ]; then
    log_success "步骤 {i} 完成"
else
    log_error "步骤 {i} 失败"
    exit 1
fi
'''
        
        script_content += '''
log_success "部署脚本执行完成"
'''
        
        script_file = self.scripts_dir / f"{script_name}.sh"
        with open(script_file, 'w') as f:
            f.write(script_content)
        
        script_file.chmod(0o755)
        
        logger.info(f"部署脚本已创建: {script_file}")
        return str(script_file)
    
    def create_audio_system_deployment_script(self, config_template: str) -> str:
        """创建音频系统部署脚本"""
        commands = [
            # 系统准备
            "systemctl stop audio-processing || true",
            "systemctl stop audio-processing-web || true",
            
            # 备份当前配置
            "mkdir -p /opt/audio-processing-system/backups",
            "cp -r /opt/audio-processing-system/config /opt/audio-processing-system/backups/config_$(date +%Y%m%d_%H%M%S) || true",
            
            # 应用新配置
            f"cp {config_template} /opt/audio-processing-system/config/audio_system.json",
            
            # 硬件检测和优化
            "cd /opt/audio-processing-system",
            "python3 tools/hardware_detector.py --output device_profiles",
            "python3 tools/terminal_device_adapter.py --classroom auto --power auto",
            
            # 重启服务
            "systemctl daemon-reload",
            "systemctl start audio-processing",
            "systemctl start audio-processing-web",
            
            # 验证部署
            "sleep 10",
            "systemctl is-active audio-processing",
            "curl -f http://localhost/health || echo 'Web interface not ready yet'",
            
            # 清理
            "find /opt/audio-processing-system/backups -name 'config_*' -mtime +7 -delete || true"
        ]
        
        return self.create_deployment_script("audio_system_deploy", commands)
    
    def get_ssh_connection(self, target: DeploymentTarget) -> paramiko.SSHClient:
        """获取SSH连接"""
        connection_key = f"{target.ip_address}:{target.ssh_port}"
        
        if connection_key in self.ssh_connections:
            # 测试现有连接
            try:
                transport = self.ssh_connections[connection_key].get_transport()
                if transport and transport.is_active():
                    return self.ssh_connections[connection_key]
            except Exception:
                pass
        
        # 创建新连接
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            if target.auth_method == "key" and target.key_file:
                ssh.connect(
                    hostname=target.ip_address,
                    port=target.ssh_port,
                    username=target.username,
                    key_filename=target.key_file,
                    timeout=30
                )
            elif target.auth_method == "password" and target.password:
                ssh.connect(
                    hostname=target.ip_address,
                    port=target.ssh_port,
                    username=target.username,
                    password=target.password,
                    timeout=30
                )
            else:
                raise ValueError("无效的认证方法或缺少认证信息")
            
            self.ssh_connections[connection_key] = ssh
            return ssh
            
        except Exception as e:
            logger.error(f"SSH连接失败 {target.ip_address}: {e}")
            raise
    
    def deploy_to_single_device(self, target: DeploymentTarget, 
                              script_path: str) -> DeploymentResult:
        """部署到单个设备"""
        start_time = datetime.now()
        
        try:
            logger.info(f"开始部署到设备: {target.device_id} ({target.ip_address})")
            
            # 获取SSH连接
            ssh = self.get_ssh_connection(target)
            
            # 上传脚本
            sftp = ssh.open_sftp()
            remote_script = f"/tmp/deploy_{int(time.time())}.sh"
            sftp.put(script_path, remote_script)
            sftp.close()
            
            # 执行脚本
            stdin, stdout, stderr = ssh.exec_command(f"chmod +x {remote_script} && {remote_script}")
            
            # 读取输出
            output = stdout.read().decode('utf-8')
            error_output = stderr.read().decode('utf-8')
            exit_code = stdout.channel.recv_exit_status()
            
            # 清理远程脚本
            ssh.exec_command(f"rm -f {remote_script}")
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            result = DeploymentResult(
                device_id=target.device_id,
                success=exit_code == 0,
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
                duration=duration,
                output=output,
                error=error_output if error_output else None,
                exit_code=exit_code
            )
            
            if result.success:
                logger.info(f"设备部署成功: {target.device_id} ({duration:.1f}s)")
            else:
                logger.error(f"设备部署失败: {target.device_id} (退出码: {exit_code})")
            
            return result
            
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.error(f"设备部署异常: {target.device_id} - {e}")
            
            return DeploymentResult(
                device_id=target.device_id,
                success=False,
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
                duration=duration,
                output="",
                error=str(e),
                exit_code=-1
            )
    
    def batch_deploy(self, targets: List[DeploymentTarget], 
                    script_path: str, max_parallel: int = 5) -> Dict[str, DeploymentResult]:
        """批量部署"""
        logger.info(f"开始批量部署到 {len(targets)} 个设备")
        
        results = {}
        
        # 使用线程池并行部署
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel) as executor:
            # 提交所有部署任务
            future_to_target = {
                executor.submit(self.deploy_to_single_device, target, script_path): target
                for target in targets
            }
            
            # 收集结果
            for future in concurrent.futures.as_completed(future_to_target):
                target = future_to_target[future]
                try:
                    result = future.result()
                    results[target.device_id] = result
                except Exception as e:
                    logger.error(f"部署任务异常: {target.device_id} - {e}")
                    results[target.device_id] = DeploymentResult(
                        device_id=target.device_id,
                        success=False,
                        start_time=datetime.now().isoformat(),
                        end_time=datetime.now().isoformat(),
                        duration=0.0,
                        output="",
                        error=str(e),
                        exit_code=-1
                    )
        
        # 统计结果
        success_count = sum(1 for r in results.values() if r.success)
        total_count = len(results)
        
        logger.info(f"批量部署完成: {success_count}/{total_count} 成功")
        
        return results
    
    def create_deployment_report(self, results: Dict[str, DeploymentResult], 
                               output_path: str) -> str:
        """创建部署报告"""
        report_data = {
            "deployment_summary": {
                "total_devices": len(results),
                "successful_deployments": sum(1 for r in results.values() if r.success),
                "failed_deployments": sum(1 for r in results.values() if not r.success),
                "total_duration": sum(r.duration for r in results.values()),
                "average_duration": sum(r.duration for r in results.values()) / len(results) if results else 0,
                "generated_at": datetime.now().isoformat()
            },
            "device_results": [asdict(result) for result in results.values()]
        }
        
        report_file = Path(output_path) / f"deployment_report_{int(time.time())}.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        # 创建HTML报告
        html_report = self._generate_html_report(report_data)
        html_file = report_file.with_suffix('.html')
        
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_report)
        
        logger.info(f"部署报告已生成: {report_file}")
        logger.info(f"HTML报告: {html_file}")
        
        return str(report_file)
    
    def _generate_html_report(self, report_data: Dict[str, Any]) -> str:
        """生成HTML报告"""
        summary = report_data["deployment_summary"]
        results = report_data["device_results"]
        
        html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>批量部署报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #f4f4f4; padding: 20px; border-radius: 5px; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
        .metric {{ background: #e9ecef; padding: 15px; border-radius: 5px; text-align: center; }}
        .metric h3 {{ margin: 0; color: #495057; }}
        .metric .value {{ font-size: 24px; font-weight: bold; color: #007bff; }}
        .success {{ color: #28a745; }}
        .failure {{ color: #dc3545; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f8f9fa; }}
        .status-success {{ color: #28a745; font-weight: bold; }}
        .status-failure {{ color: #dc3545; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>批量部署报告</h1>
        <p>生成时间: {summary["generated_at"]}</p>
    </div>
    
    <div class="summary">
        <div class="metric">
            <h3>总设备数</h3>
            <div class="value">{summary["total_devices"]}</div>
        </div>
        <div class="metric">
            <h3>成功部署</h3>
            <div class="value success">{summary["successful_deployments"]}</div>
        </div>
        <div class="metric">
            <h3>失败部署</h3>
            <div class="value failure">{summary["failed_deployments"]}</div>
        </div>
        <div class="metric">
            <h3>平均耗时</h3>
            <div class="value">{summary["average_duration"]:.1f}s</div>
        </div>
    </div>
    
    <h2>详细结果</h2>
    <table>
        <thead>
            <tr>
                <th>设备ID</th>
                <th>状态</th>
                <th>开始时间</th>
                <th>耗时(秒)</th>
                <th>退出码</th>
                <th>错误信息</th>
            </tr>
        </thead>
        <tbody>
'''
        
        for result in results:
            status_class = "status-success" if result["success"] else "status-failure"
            status_text = "成功" if result["success"] else "失败"
            error_text = result.get("error", "") or ""
            
            html_content += f'''
            <tr>
                <td>{result["device_id"]}</td>
                <td class="{status_class}">{status_text}</td>
                <td>{result["start_time"]}</td>
                <td>{result["duration"]:.1f}</td>
                <td>{result["exit_code"]}</td>
                <td>{error_text}</td>
            </tr>
'''
        
        html_content += '''
        </tbody>
    </table>
</body>
</html>
'''
        
        return html_content
    
    def cleanup_connections(self):
        """清理SSH连接"""
        for connection in self.ssh_connections.values():
            try:
                connection.close()
            except Exception:
                pass
        self.ssh_connections.clear()

def main():
    parser = argparse.ArgumentParser(description="批量部署管理器")
    parser.add_argument("--targets", "-t", required=True,
                       help="目标设备列表文件 (JSON格式)")
    parser.add_argument("--script", "-s", 
                       help="部署脚本路径")
    parser.add_argument("--config-template", "-c",
                       help="配置模板文件")
    parser.add_argument("--parallel", "-p", type=int, default=5,
                       help="并行部署数量")
    parser.add_argument("--output", "-o", default="deployment_reports",
                       help="报告输出目录")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    manager = BatchDeploymentManager()
    
    try:
        # 加载目标设备列表
        with open(args.targets, 'r', encoding='utf-8') as f:
            targets_data = json.load(f)
        
        targets = [DeploymentTarget(**target) for target in targets_data]
        
        # 创建或使用部署脚本
        if args.config_template:
            script_path = manager.create_audio_system_deployment_script(args.config_template)
        elif args.script:
            script_path = args.script
        else:
            raise ValueError("必须指定配置模板或部署脚本")
        
        print(f"开始批量部署到 {len(targets)} 个设备...")
        print(f"使用脚本: {script_path}")
        print(f"并行数量: {args.parallel}")
        
        # 执行批量部署
        results = manager.batch_deploy(targets, script_path, args.parallel)
        
        # 生成报告
        report_path = manager.create_deployment_report(results, args.output)
        
        # 显示摘要
        success_count = sum(1 for r in results.values() if r.success)
        total_count = len(results)
        
        print(f"\n批量部署完成!")
        print(f"成功: {success_count}/{total_count}")
        print(f"报告: {report_path}")
        
        if success_count < total_count:
            print("\n失败的设备:")
            for device_id, result in results.items():
                if not result.success:
                    print(f"  - {device_id}: {result.error}")
    
    except Exception as e:
        logger.error(f"批量部署失败: {e}")
        sys.exit(1)
    
    finally:
        manager.cleanup_connections()

if __name__ == "__main__":
    main()