#!/usr/bin/env python3
"""
远程故障诊断和日志收集工具
Remote Diagnostics and Log Collection Tool

提供远程设备诊断、日志收集和故障分析功能
"""

import sys
import json
import time
import tarfile
from pathlib import Path
from typing import Dict, List, Any
import argparse
import logging
from datetime import datetime
from dataclasses import dataclass, asdict
import paramiko

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class DiagnosticResult:
    """诊断结果"""
    test_name: str
    status: str  # pass/fail/warning
    message: str
    details: Dict[str, Any]
    timestamp: str

@dataclass
class LogCollectionResult:
    """日志收集结果"""
    device_id: str
    log_files: List[str]
    collection_time: str
    archive_path: str
    size_mb: float

class RemoteDiagnostics:
    """远程诊断工具"""
    
    def __init__(self, output_dir: str = "diagnostics"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 诊断测试定义
        self.diagnostic_tests = {
            "system_health": self._test_system_health,
            "audio_services": self._test_audio_services,
            "network_connectivity": self._test_network_connectivity,
            "disk_space": self._test_disk_space,
            "audio_devices": self._test_audio_devices,
            "configuration": self._test_configuration,
            "performance": self._test_performance
        }
        
        # 日志文件路径
        self.log_paths = [
            "/opt/audio-processing-system/logs/",
            "/var/log/audio-processing/",
            "/var/log/syslog",
            "/var/log/messages",
            "/var/log/kern.log",
            "/var/log/nginx/",
            "/home/*/audio-processing-system/logs/"
        ]
    
    def run_remote_diagnostics(self, host: str, username: str = "root", 
                             key_file: str = None, password: str = None) -> List[DiagnosticResult]:
        """运行远程诊断"""
        logger.info(f"开始远程诊断: {host}")
        
        results = []
        ssh = None
        
        try:
            # 建立SSH连接
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            if key_file:
                ssh.connect(host, username=username, key_filename=key_file, timeout=30)
            elif password:
                ssh.connect(host, username=username, password=password, timeout=30)
            else:
                raise ValueError("需要提供SSH密钥或密码")
            
            # 运行所有诊断测试
            for test_name, test_func in self.diagnostic_tests.items():
                try:
                    logger.info(f"运行测试: {test_name}")
                    result = test_func(ssh)
                    results.append(result)
                except Exception as e:
                    logger.error(f"测试 {test_name} 失败: {e}")
                    results.append(DiagnosticResult(
                        test_name=test_name,
                        status="fail",
                        message=f"测试执行失败: {str(e)}",
                        details={},
                        timestamp=datetime.now().isoformat()
                    ))
            
            logger.info(f"远程诊断完成: {host}")
            
        except Exception as e:
            logger.error(f"远程诊断失败: {e}")
            results.append(DiagnosticResult(
                test_name="connection",
                status="fail",
                message=f"连接失败: {str(e)}",
                details={},
                timestamp=datetime.now().isoformat()
            ))
        
        finally:
            if ssh:
                ssh.close()
        
        return results
    
    def _execute_remote_command(self, ssh: paramiko.SSHClient, 
                              command: str) -> tuple[str, str, int]:
        """执行远程命令"""
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode('utf-8')
        error = stderr.read().decode('utf-8')
        exit_code = stdout.channel.recv_exit_status()
        return output, error, exit_code
    
    def _test_system_health(self, ssh: paramiko.SSHClient) -> DiagnosticResult:
        """测试系统健康状态"""
        details = {}
        
        # CPU使用率
        output, _, _ = self._execute_remote_command(ssh, "top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1")
        cpu_usage = float(output.strip()) if output.strip() else 0.0
        details["cpu_usage"] = cpu_usage
        
        # 内存使用率
        output, _, _ = self._execute_remote_command(ssh, "free | grep Mem | awk '{printf \"%.1f\", $3/$2 * 100.0}'")
        memory_usage = float(output.strip()) if output.strip() else 0.0
        details["memory_usage"] = memory_usage
        
        # 系统负载
        output, _, _ = self._execute_remote_command(ssh, "uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//'")
        load_avg = float(output.strip()) if output.strip() else 0.0
        details["load_average"] = load_avg
        
        # 判断状态
        if cpu_usage > 90 or memory_usage > 95 or load_avg > 4.0:
            status = "fail"
            message = "系统资源使用率过高"
        elif cpu_usage > 70 or memory_usage > 80 or load_avg > 2.0:
            status = "warning"
            message = "系统资源使用率较高"
        else:
            status = "pass"
            message = "系统健康状态良好"
        
        return DiagnosticResult(
            test_name="system_health",
            status=status,
            message=message,
            details=details,
            timestamp=datetime.now().isoformat()
        )
    
    def _test_audio_services(self, ssh: paramiko.SSHClient) -> DiagnosticResult:
        """测试音频服务状态"""
        details = {}
        services = ["audio-processing", "audio-processing-web", "nginx"]
        
        all_running = True
        for service in services:
            output, _, exit_code = self._execute_remote_command(ssh, f"systemctl is-active {service}")
            is_active = output.strip() == "active"
            details[service] = "running" if is_active else "stopped"
            if not is_active:
                all_running = False
        
        if all_running:
            status = "pass"
            message = "所有音频服务正常运行"
        else:
            status = "fail"
            message = "部分音频服务未运行"
        
        return DiagnosticResult(
            test_name="audio_services",
            status=status,
            message=message,
            details=details,
            timestamp=datetime.now().isoformat()
        )
    
    def _test_network_connectivity(self, ssh: paramiko.SSHClient) -> DiagnosticResult:
        """测试网络连接"""
        details = {}
        
        # 测试本地网络
        output, _, exit_code = self._execute_remote_command(ssh, "ping -c 3 127.0.0.1")
        details["localhost"] = exit_code == 0
        
        # 测试网关连接
        output, _, exit_code = self._execute_remote_command(ssh, "ping -c 3 $(ip route | grep default | awk '{print $3}' | head -1)")
        details["gateway"] = exit_code == 0
        
        # 测试DNS解析
        output, _, exit_code = self._execute_remote_command(ssh, "nslookup google.com")
        details["dns"] = exit_code == 0
        
        # 测试Web服务端口
        output, _, exit_code = self._execute_remote_command(ssh, "curl -f http://localhost/health")
        details["web_service"] = exit_code == 0
        
        if all(details.values()):
            status = "pass"
            message = "网络连接正常"
        elif details["localhost"] and details["gateway"]:
            status = "warning"
            message = "本地网络正常，但外网或服务可能有问题"
        else:
            status = "fail"
            message = "网络连接存在问题"
        
        return DiagnosticResult(
            test_name="network_connectivity",
            status=status,
            message=message,
            details=details,
            timestamp=datetime.now().isoformat()
        )
    
    def _test_disk_space(self, ssh: paramiko.SSHClient) -> DiagnosticResult:
        """测试磁盘空间"""
        details = {}
        
        # 检查根分区
        output, _, _ = self._execute_remote_command(ssh, "df -h / | tail -1 | awk '{print $5}' | sed 's/%//'")
        root_usage = int(output.strip()) if output.strip().isdigit() else 0
        details["root_partition"] = root_usage
        
        # 检查音频系统目录
        output, _, _ = self._execute_remote_command(ssh, "du -sh /opt/audio-processing-system 2>/dev/null | awk '{print $1}' || echo '0'")
        details["audio_system_size"] = output.strip()
        
        # 检查日志目录大小
        output, _, _ = self._execute_remote_command(ssh, "du -sh /opt/audio-processing-system/logs 2>/dev/null | awk '{print $1}' || echo '0'")
        details["logs_size"] = output.strip()
        
        if root_usage > 95:
            status = "fail"
            message = f"磁盘空间严重不足: {root_usage}%"
        elif root_usage > 85:
            status = "warning"
            message = f"磁盘空间不足: {root_usage}%"
        else:
            status = "pass"
            message = f"磁盘空间充足: {root_usage}%"
        
        return DiagnosticResult(
            test_name="disk_space",
            status=status,
            message=message,
            details=details,
            timestamp=datetime.now().isoformat()
        )
    
    def _test_audio_devices(self, ssh: paramiko.SSHClient) -> DiagnosticResult:
        """测试音频设备"""
        details = {}
        
        # 检查ALSA设备
        output, _, exit_code = self._execute_remote_command(ssh, "arecord -l 2>/dev/null | grep card || echo 'no devices'")
        audio_devices = output.strip().split('\n') if output.strip() != 'no devices' else []
        details["alsa_devices"] = len(audio_devices)
        details["device_list"] = audio_devices
        
        # 检查音频服务配置
        output, _, _ = self._execute_remote_command(ssh, "ls -la /opt/audio-processing-system/config/audio_system.json 2>/dev/null || echo 'not found'")
        details["config_exists"] = "not found" not in output
        
        if details["alsa_devices"] > 0 and details["config_exists"]:
            status = "pass"
            message = f"检测到 {details['alsa_devices']} 个音频设备"
        elif details["alsa_devices"] > 0:
            status = "warning"
            message = "检测到音频设备但配置文件缺失"
        else:
            status = "fail"
            message = "未检测到音频设备"
        
        return DiagnosticResult(
            test_name="audio_devices",
            status=status,
            message=message,
            details=details,
            timestamp=datetime.now().isoformat()
        )
    
    def _test_configuration(self, ssh: paramiko.SSHClient) -> DiagnosticResult:
        """测试配置文件"""
        details = {}
        
        config_files = [
            "/opt/audio-processing-system/config/audio_system.json",
            "/etc/systemd/system/audio-processing.service",
            "/etc/nginx/sites-enabled/audio-processing"
        ]
        
        all_exist = True
        for config_file in config_files:
            output, _, exit_code = self._execute_remote_command(ssh, f"test -f {config_file} && echo 'exists' || echo 'missing'")
            exists = output.strip() == "exists"
            details[config_file] = exists
            if not exists:
                all_exist = False
        
        # 检查配置文件语法
        output, _, exit_code = self._execute_remote_command(ssh, "python3 -c 'import json; json.load(open(\"/opt/audio-processing-system/config/audio_system.json\"))' 2>/dev/null && echo 'valid' || echo 'invalid'")
        details["json_syntax"] = output.strip() == "valid"
        
        if all_exist and details["json_syntax"]:
            status = "pass"
            message = "配置文件完整且格式正确"
        elif all_exist:
            status = "warning"
            message = "配置文件存在但格式可能有问题"
        else:
            status = "fail"
            message = "配置文件缺失"
        
        return DiagnosticResult(
            test_name="configuration",
            status=status,
            message=message,
            details=details,
            timestamp=datetime.now().isoformat()
        )
    
    def _test_performance(self, ssh: paramiko.SSHClient) -> DiagnosticResult:
        """测试性能指标"""
        details = {}
        
        # 测试音频延迟（模拟）
        output, _, _ = self._execute_remote_command(ssh, "python3 -c 'import json; config=json.load(open(\"/opt/audio-processing-system/config/audio_system.json\")); print(config.get(\"audio\", {}).get(\"buffer_size\", 2048))' 2>/dev/null || echo '2048'")
        buffer_size = int(output.strip()) if output.strip().isdigit() else 2048
        estimated_latency = buffer_size / 48000 * 1000  # 估算延迟（毫秒）
        details["estimated_latency_ms"] = estimated_latency
        details["buffer_size"] = buffer_size
        
        # 检查系统性能
        output, _, _ = self._execute_remote_command(ssh, "cat /proc/cpuinfo | grep 'cpu MHz' | head -1 | awk '{print $4}' || echo '0'")
        cpu_freq = float(output.strip()) if output.strip() else 0.0
        details["cpu_frequency_mhz"] = cpu_freq
        
        if estimated_latency <= 20:
            status = "pass"
            message = f"性能良好，估算延迟: {estimated_latency:.1f}ms"
        elif estimated_latency <= 40:
            status = "warning"
            message = f"性能一般，估算延迟: {estimated_latency:.1f}ms"
        else:
            status = "fail"
            message = f"性能不佳，估算延迟: {estimated_latency:.1f}ms"
        
        return DiagnosticResult(
            test_name="performance",
            status=status,
            message=message,
            details=details,
            timestamp=datetime.now().isoformat()
        )
    
    def collect_remote_logs(self, host: str, username: str = "root", 
                          key_file: str = None, password: str = None,
                          days: int = 7) -> LogCollectionResult:
        """收集远程日志"""
        logger.info(f"开始收集远程日志: {host}")
        
        device_id = f"{host}_{int(time.time())}"
        collection_time = datetime.now().isoformat()
        
        ssh = None
        sftp = None
        collected_files = []
        
        try:
            # 建立SSH连接
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            if key_file:
                ssh.connect(host, username=username, key_filename=key_file, timeout=30)
            elif password:
                ssh.connect(host, username=username, password=password, timeout=30)
            else:
                raise ValueError("需要提供SSH密钥或密码")
            
            sftp = ssh.open_sftp()
            
            # 创建本地收集目录
            local_dir = self.output_dir / f"logs_{device_id}"
            local_dir.mkdir(exist_ok=True)
            
            # 收集日志文件
            for log_path in self.log_paths:
                try:
                    # 检查路径是否存在
                    output, _, exit_code = self._execute_remote_command(ssh, f"test -e {log_path} && echo 'exists' || echo 'missing'")
                    if output.strip() != "exists":
                        continue
                    
                    # 如果是目录，列出文件
                    if log_path.endswith('/'):
                        output, _, _ = self._execute_remote_command(ssh, f"find {log_path} -name '*.log' -mtime -{days} -type f")
                        files = [f.strip() for f in output.split('\n') if f.strip()]
                    else:
                        files = [log_path]
                    
                    # 下载文件
                    for remote_file in files:
                        try:
                            local_file = local_dir / Path(remote_file).name
                            sftp.get(remote_file, str(local_file))
                            collected_files.append(str(local_file))
                            logger.debug(f"已收集: {remote_file}")
                        except Exception as e:
                            logger.warning(f"收集文件失败 {remote_file}: {e}")
                
                except Exception as e:
                    logger.warning(f"处理日志路径失败 {log_path}: {e}")
            
            # 创建压缩包
            archive_path = self.output_dir / f"logs_{device_id}.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(local_dir, arcname=f"logs_{device_id}")
            
            # 计算大小
            size_mb = archive_path.stat().st_size / (1024 * 1024)
            
            # 清理临时目录
            import shutil
            shutil.rmtree(local_dir)
            
            logger.info(f"日志收集完成: {len(collected_files)} 个文件, {size_mb:.1f}MB")
            
            return LogCollectionResult(
                device_id=device_id,
                log_files=collected_files,
                collection_time=collection_time,
                archive_path=str(archive_path),
                size_mb=size_mb
            )
            
        except Exception as e:
            logger.error(f"日志收集失败: {e}")
            raise
        
        finally:
            if sftp:
                sftp.close()
            if ssh:
                ssh.close()
    
    def generate_diagnostic_report(self, host: str, results: List[DiagnosticResult], 
                                 log_result: LogCollectionResult = None) -> str:
        """生成诊断报告"""
        report_data = {
            "host": host,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": len(results),
                "passed": len([r for r in results if r.status == "pass"]),
                "warnings": len([r for r in results if r.status == "warning"]),
                "failed": len([r for r in results if r.status == "fail"])
            },
            "test_results": [asdict(result) for result in results],
            "log_collection": asdict(log_result) if log_result else None
        }
        
        report_file = self.output_dir / f"diagnostic_report_{host}_{int(time.time())}.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"诊断报告已生成: {report_file}")
        return str(report_file)

def main():
    parser = argparse.ArgumentParser(description="远程故障诊断和日志收集工具")
    parser.add_argument("host", help="目标主机地址")
    parser.add_argument("--username", "-u", default="root", help="SSH用户名")
    parser.add_argument("--key-file", "-k", help="SSH私钥文件")
    parser.add_argument("--password", "-p", help="SSH密码")
    parser.add_argument("--collect-logs", "-l", action="store_true", help="收集日志文件")
    parser.add_argument("--log-days", type=int, default=7, help="收集最近几天的日志")
    parser.add_argument("--output", "-o", default="diagnostics", help="输出目录")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    diagnostics = RemoteDiagnostics(args.output)
    
    try:
        # 运行诊断测试
        print(f"开始远程诊断: {args.host}")
        results = diagnostics.run_remote_diagnostics(
            args.host, args.username, args.key_file, args.password
        )
        
        # 收集日志（如果需要）
        log_result = None
        if args.collect_logs:
            print("收集远程日志...")
            log_result = diagnostics.collect_remote_logs(
                args.host, args.username, args.key_file, args.password, args.log_days
            )
        
        # 生成报告
        report_path = diagnostics.generate_diagnostic_report(args.host, results, log_result)
        
        # 显示摘要
        passed = len([r for r in results if r.status == "pass"])
        warnings = len([r for r in results if r.status == "warning"])
        failed = len([r for r in results if r.status == "fail"])
        
        print(f"\n诊断完成!")
        print(f"通过: {passed}, 警告: {warnings}, 失败: {failed}")
        print(f"报告: {report_path}")
        
        if log_result:
            print(f"日志: {log_result.archive_path} ({log_result.size_mb:.1f}MB)")
        
        # 显示失败的测试
        if failed > 0:
            print("\n失败的测试:")
            for result in results:
                if result.status == "fail":
                    print(f"  - {result.test_name}: {result.message}")
    
    except Exception as e:
        logger.error(f"远程诊断失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()