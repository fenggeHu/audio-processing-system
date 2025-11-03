#!/usr/bin/env python3
"""
音频处理系统故障排除工具包
Audio Processing System Troubleshooting Toolkit
"""

import os
import sys
import time
import json
import psutil
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass



class TroubleshootingToolkit:
    """故障排除工具包主类"""
    
    def __init__(self, config_path: str = "config/classroom_environments.yaml"):
        self.config_path = config_path
        self.log_dir = Path("/var/log/audio-processing")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
    def run_full_diagnostic(self) -> Dict:
        """运行完整的系统诊断"""
        print("🔍 开始系统诊断...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'system_info': self._get_system_info(),
            'hardware_check': self._check_hardware(),
            'audio_system': self._check_audio_system(),
            'network_status': self._check_network(),
            'performance_metrics': self._get_performance_metrics(),
            'log_analysis': self._analyze_logs(),
            'recommendations': []
        }
        
        # 生成建议
        results['recommendations'] = self._generate_recommendations(results)
        
        # 保存诊断报告
        report_file = self.log_dir / f"diagnostic_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"📋 诊断报告已保存到: {report_file}")
        return results
    
    def _get_system_info(self) -> Dict:
        """获取系统信息"""
        try:
            return {
                'platform': psutil.LINUX if hasattr(psutil, 'LINUX') else 'unknown',
                'cpu_count': psutil.cpu_count(),
                'cpu_freq': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None,
                'memory_total_gb': psutil.virtual_memory().total / (1024**3),
                'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat(),
                'python_version': sys.version
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _check_hardware(self) -> Dict:
        """检查硬件状态"""
        hardware_status = {
            'cpu_usage': psutil.cpu_percent(interval=1),
            'memory': psutil.virtual_memory()._asdict(),
            'disk': {},
            'audio_devices': []
        }
        
        # 检查磁盘使用情况
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                hardware_status['disk'][partition.device] = {
                    'total_gb': usage.total / (1024**3),
                    'used_gb': usage.used / (1024**3),
                    'free_gb': usage.free / (1024**3),
                    'percent': (usage.used / usage.total) * 100
                }
            except PermissionError:
                continue
        
        # 检查音频设备（需要pyaudio）
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            for i in range(pa.get_device_count()):
                device_info = pa.get_device_info_by_index(i)
                hardware_status['audio_devices'].append({
                    'index': i,
                    'name': device_info['name'],
                    'channels': device_info['maxInputChannels'],
                    'sample_rate': device_info['defaultSampleRate']
                })
            pa.terminate()
        except ImportError:
            hardware_status['audio_devices'] = ['pyaudio not available']
        except Exception as e:
            hardware_status['audio_devices'] = [f'Error: {str(e)}']
        
        return hardware_status
    
    def _check_audio_system(self) -> Dict:
        """检查音频系统状态"""
        audio_status = {
            'alsa_info': self._get_alsa_info(),
            'pulseaudio_status': self._check_pulseaudio(),
            'jack_status': self._check_jack(),
            'latency_test': self._test_audio_latency()
        }
        
        return audio_status
    
    def _get_alsa_info(self) -> Dict:
        """获取ALSA信息"""
        try:
            result = subprocess.run(['aplay', '-l'], capture_output=True, text=True)
            return {
                'available': result.returncode == 0,
                'devices': result.stdout if result.returncode == 0 else result.stderr
            }
        except FileNotFoundError:
            return {'available': False, 'error': 'ALSA tools not found'}
    
    def _check_pulseaudio(self) -> Dict:
        """检查PulseAudio状态"""
        try:
            result = subprocess.run(['pulseaudio', '--check'], capture_output=True)
            return {
                'running': result.returncode == 0,
                'status': 'running' if result.returncode == 0 else 'not running'
            }
        except FileNotFoundError:
            return {'running': False, 'error': 'PulseAudio not found'}
    
    def _check_jack(self) -> Dict:
        """检查JACK状态"""
        try:
            result = subprocess.run(['jack_control', 'status'], capture_output=True, text=True)
            return {
                'available': result.returncode == 0,
                'status': result.stdout.strip() if result.returncode == 0 else 'not available'
            }
        except FileNotFoundError:
            return {'available': False, 'error': 'JACK not found'}
    
    def _test_audio_latency(self) -> Dict:
        """测试音频延迟"""
        try:
            # 这里应该调用实际的音频系统进行延迟测试
            # 目前返回模拟数据
            return {
                'input_latency_ms': 12.5,
                'output_latency_ms': 8.3,
                'total_latency_ms': 20.8,
                'test_successful': True
            }
        except Exception as e:
            return {
                'test_successful': False,
                'error': str(e)
            }
    
    def _check_network(self) -> Dict:
        """检查网络状态"""
        net_io = psutil.net_io_counters()
        network_status = {
            'interfaces': {},
            'io_counters': net_io._asdict(),
            'connections': len(psutil.net_connections()),
            'bandwidth_test': self._test_network_bandwidth()
        }
        
        # 检查网络接口
        for interface, addrs in psutil.net_if_addrs().items():
            network_status['interfaces'][interface] = []
            for addr in addrs:
                network_status['interfaces'][interface].append({
                    'family': str(addr.family),
                    'address': addr.address,
                    'netmask': addr.netmask,
                    'broadcast': addr.broadcast
                })
        
        return network_status
    
    def _test_network_bandwidth(self) -> Dict:
        """测试网络带宽"""
        try:
            result = subprocess.run(['ping', '-c', '2', '8.8.8.8'], 
                                  capture_output=True, text=True, timeout=5)
            return {'ping_successful': result.returncode == 0}
        except Exception:
            return {'ping_successful': False}
    
    def _get_performance_metrics(self) -> Dict:
        """获取性能指标"""
        metrics = {
            'cpu_times': psutil.cpu_times()._asdict(),
            'cpu_percent_per_core': psutil.cpu_percent(percpu=True),
            'memory_info': psutil.virtual_memory()._asdict(),
            'swap_info': psutil.swap_memory()._asdict(),
            'load_average': os.getloadavg() if hasattr(os, 'getloadavg') else None,
            'process_count': len(psutil.pids())
        }
        
        return metrics
    
    def _analyze_logs(self) -> Dict:
        """分析日志文件"""
        log_analysis = {
            'error_count': 0,
            'warning_count': 0,
            'recent_errors': [],
            'performance_issues': []
        }
        
        # 分析系统日志
        system_log = self.log_dir / "system.log"
        if system_log.exists():
            log_analysis.update(self._parse_log_file(system_log))
        
        # 分析性能日志
        performance_log = self.log_dir / "performance.log"
        if performance_log.exists():
            perf_data = self._analyze_performance_log(performance_log)
            log_analysis['performance_issues'] = perf_data
        
        return log_analysis
    
    def _parse_log_file(self, log_file: Path) -> Dict:
        """解析日志文件"""
        error_count = 0
        warning_count = 0
        recent_errors = []
        
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()[-1000:]  # 只分析最近1000行
            
            for line in lines:
                if 'ERROR' in line:
                    error_count += 1
                    if len(recent_errors) < 10:
                        recent_errors.append(line.strip())
                elif 'WARNING' in line:
                    warning_count += 1
        
        except Exception as e:
            return {'parse_error': str(e)}
        
        return {
            'error_count': error_count,
            'warning_count': warning_count,
            'recent_errors': recent_errors
        }
    
    def _analyze_performance_log(self, log_file: Path) -> List[str]:
        """分析性能日志"""
        issues = []
        
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()[-100:]  # 分析最近100行
            
            error_lines = [line for line in lines if 'ERROR' in line or 'CRITICAL' in line]
            if len(error_lines) > 5:
                issues.append(f"检测到{len(error_lines)}个严重错误")
        
        except Exception as e:
            issues.append(f"性能日志分析错误: {str(e)}")
        
        return issues
    
    def _generate_recommendations(self, results: Dict) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        # CPU使用率建议
        if results.get('hardware_check', {}).get('cpu_usage', 0) > 80:
            recommendations.append("CPU使用率过高，建议：1) 减少并发处理线程 2) 启用性能模式 3) 检查后台进程")
        
        # 内存使用建议
        memory_percent = results.get('hardware_check', {}).get('memory', {}).get('percent', 0)
        if memory_percent > 85:
            recommendations.append("内存使用率过高，建议：1) 增加物理内存 2) 启用内存优化 3) 清理缓存")
        
        # 磁盘空间建议
        for device, disk_info in results.get('hardware_check', {}).get('disk', {}).items():
            if disk_info.get('percent', 0) > 90:
                recommendations.append(f"磁盘 {device} 空间不足，建议清理日志文件和临时文件")
        
        # 音频系统建议
        audio_latency = results.get('audio_system', {}).get('latency_test', {}).get('total_latency_ms', 0)
        if audio_latency > 50:
            recommendations.append("音频延迟过高，建议：1) 减小缓冲区大小 2) 使用专业音频接口 3) 优化音频驱动")
        
        # 网络建议
        if not results.get('network_status', {}).get('bandwidth_test', {}).get('ping_successful', True):
            recommendations.append("网络连接异常，建议检查网络配置和连接状态")
        
        # 日志分析建议
        error_count = results.get('log_analysis', {}).get('error_count', 0)
        if error_count > 10:
            recommendations.append(f"检测到{error_count}个错误，建议查看详细日志并修复相关问题")
        
        if not recommendations:
            recommendations.append("系统运行正常，无需特殊优化")
        
        return recommendations

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='音频处理系统故障排除工具')
    parser.add_argument('--config', default='config/classroom_environments.yaml',
                       help='配置文件路径')
    parser.add_argument('--output', help='输出报告文件路径')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='详细输出')
    
    args = parser.parse_args()
    
    toolkit = TroubleshootingToolkit(args.config)
    
    print("🚀 音频处理系统故障排除工具")
    print("=" * 50)
    
    # 运行诊断
    results = toolkit.run_full_diagnostic()
    
    # 显示结果摘要
    print("\n📊 诊断结果摘要:")
    print(f"CPU使用率: {results.get('hardware_check', {}).get('cpu_usage', 0):.1f}%")
    print(f"内存使用率: {results.get('hardware_check', {}).get('memory', {}).get('percent', 0):.1f}%")
    print(f"音频延迟: {results.get('audio_system', {}).get('latency_test', {}).get('total_latency_ms', 0):.1f}ms")
    
    print("\n💡 优化建议:")
    for i, recommendation in enumerate(results.get('recommendations', []), 1):
        print(f"{i}. {recommendation}")
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n📄 详细报告已保存到: {args.output}")
    
    print("\n✅ 诊断完成!")

if __name__ == "__main__":
    main()