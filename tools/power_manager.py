#!/usr/bin/env python3
"""
电源管理和资源优化工具
Power Management and Resource Optimization Tool

为终端设备提供低功耗模式和资源优化功能
"""

import os
import sys
import json
import psutil
import time
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
class PowerProfile:
    """电源配置文件"""
    name: str
    description: str
    cpu_governor: str
    cpu_max_freq: Optional[int]
    cpu_cores_enabled: List[int]
    memory_limit_mb: Optional[int]
    audio_buffer_multiplier: float
    processing_priority: str
    service_configs: Dict[str, Any]

@dataclass
class ResourceUsage:
    """资源使用情况"""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_mb: int
    disk_io_read: int
    disk_io_write: int
    network_io_sent: int
    network_io_recv: int
    audio_dropouts: int = 0
    processing_latency: float = 0.0

class PowerManager:
    """电源管理器"""
    
    def __init__(self):
        self.current_profile = None
        self.resource_history = []
        self.monitoring_active = False
        
        # 预定义的电源配置文件
        self.power_profiles = {
            "performance": PowerProfile(
                name="performance",
                description="高性能模式 - 最佳音频质量和最低延迟",
                cpu_governor="performance",
                cpu_max_freq=None,  # 不限制
                cpu_cores_enabled=list(range(psutil.cpu_count())),
                memory_limit_mb=None,
                audio_buffer_multiplier=0.5,  # 减小缓冲区
                processing_priority="high",
                service_configs={
                    "ssl": {"update_interval_ms": 50},
                    "beamformer": {"algorithm": "MVDR"},
                    "denoise": {"strength": "aggressive"},
                    "aec": {"filter_length": 512}
                }
            ),
            "balanced": PowerProfile(
                name="balanced",
                description="平衡模式 - 性能和功耗的平衡",
                cpu_governor="ondemand",
                cpu_max_freq=None,
                cpu_cores_enabled=list(range(min(8, psutil.cpu_count()))),
                memory_limit_mb=None,
                audio_buffer_multiplier=1.0,  # 标准缓冲区
                processing_priority="normal",
                service_configs={
                    "ssl": {"update_interval_ms": 100},
                    "beamformer": {"algorithm": "DAS"},
                    "denoise": {"strength": "moderate"},
                    "aec": {"filter_length": 256}
                }
            ),
            "power_save": PowerProfile(
                name="power_save",
                description="节能模式 - 最低功耗，适合电池供电",
                cpu_governor="powersave",
                cpu_max_freq=1000000,  # 1GHz
                cpu_cores_enabled=list(range(min(4, psutil.cpu_count()))),
                memory_limit_mb=2048,  # 2GB限制
                audio_buffer_multiplier=2.0,  # 增大缓冲区
                processing_priority="low",
                service_configs={
                    "ssl": {"update_interval_ms": 200, "enabled": False},
                    "beamformer": {"algorithm": "DAS"},
                    "denoise": {"strength": "light"},
                    "aec": {"filter_length": 128}
                }
            ),
            "classroom": PowerProfile(
                name="classroom",
                description="教室模式 - 针对教室环境优化",
                cpu_governor="ondemand",
                cpu_max_freq=None,
                cpu_cores_enabled=list(range(min(6, psutil.cpu_count()))),
                memory_limit_mb=None,
                audio_buffer_multiplier=1.2,
                processing_priority="normal",
                service_configs={
                    "ssl": {"update_interval_ms": 100},
                    "beamformer": {"algorithm": "DAS"},
                    "denoise": {"strength": "moderate"},
                    "aec": {"filter_length": 256, "double_talk_detection": True}
                }
            )
        }
    
    def get_current_resource_usage(self) -> ResourceUsage:
        """获取当前资源使用情况"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk_io = psutil.disk_io_counters()
        network_io = psutil.net_io_counters()
        
        return ResourceUsage(
            timestamp=time.time(),
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_mb=memory.used // (1024 * 1024),
            disk_io_read=disk_io.read_bytes if disk_io else 0,
            disk_io_write=disk_io.write_bytes if disk_io else 0,
            network_io_sent=network_io.bytes_sent if network_io else 0,
            network_io_recv=network_io.bytes_recv if network_io else 0
        )
    
    def apply_power_profile(self, profile_name: str) -> bool:
        """应用电源配置文件"""
        if profile_name not in self.power_profiles:
            logger.error(f"未知的电源配置文件: {profile_name}")
            return False
        
        profile = self.power_profiles[profile_name]
        logger.info(f"应用电源配置文件: {profile.name} - {profile.description}")
        
        try:
            # 设置CPU调频策略
            self._set_cpu_governor(profile.cpu_governor)
            
            # 设置CPU最大频率
            if profile.cpu_max_freq:
                self._set_cpu_max_frequency(profile.cpu_max_freq)
            
            # 设置CPU核心
            self._set_cpu_cores(profile.cpu_cores_enabled)
            
            # 设置内存限制
            if profile.memory_limit_mb:
                self._set_memory_limit(profile.memory_limit_mb)
            
            # 设置进程优先级
            self._set_process_priority(profile.processing_priority)
            
            self.current_profile = profile
            logger.info(f"电源配置文件 {profile_name} 应用成功")
            return True
            
        except Exception as e:
            logger.error(f"应用电源配置文件失败: {e}")
            return False
    
    def _set_cpu_governor(self, governor: str):
        """设置CPU调频策略"""
        try:
            if sys.platform.startswith('linux'):
                # Linux系统
                cpu_count = psutil.cpu_count()
                for i in range(cpu_count):
                    governor_file = f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_governor"
                    if os.path.exists(governor_file):
                        with open(governor_file, 'w') as f:
                            f.write(governor)
                logger.info(f"CPU调频策略设置为: {governor}")
            else:
                logger.warning(f"当前平台不支持CPU调频策略设置: {sys.platform}")
        except Exception as e:
            logger.warning(f"设置CPU调频策略失败: {e}")
    
    def _set_cpu_max_frequency(self, max_freq: int):
        """设置CPU最大频率"""
        try:
            if sys.platform.startswith('linux'):
                cpu_count = psutil.cpu_count()
                for i in range(cpu_count):
                    max_freq_file = f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_max_freq"
                    if os.path.exists(max_freq_file):
                        with open(max_freq_file, 'w') as f:
                            f.write(str(max_freq))
                logger.info(f"CPU最大频率设置为: {max_freq/1000000:.1f}GHz")
            else:
                logger.warning(f"当前平台不支持CPU频率设置: {sys.platform}")
        except Exception as e:
            logger.warning(f"设置CPU最大频率失败: {e}")
    
    def _set_cpu_cores(self, enabled_cores: List[int]):
        """设置启用的CPU核心"""
        try:
            if sys.platform.startswith('linux'):
                total_cores = psutil.cpu_count()
                for i in range(total_cores):
                    online_file = f"/sys/devices/system/cpu/cpu{i}/online"
                    if os.path.exists(online_file) and i > 0:  # CPU0通常不能禁用
                        status = "1" if i in enabled_cores else "0"
                        with open(online_file, 'w') as f:
                            f.write(status)
                logger.info(f"启用CPU核心: {enabled_cores}")
            else:
                logger.warning(f"当前平台不支持CPU核心控制: {sys.platform}")
        except Exception as e:
            logger.warning(f"设置CPU核心失败: {e}")
    
    def _set_memory_limit(self, limit_mb: int):
        """设置内存限制"""
        try:
            # 使用cgroups设置内存限制（需要root权限）
            if sys.platform.startswith('linux'):
                cgroup_path = "/sys/fs/cgroup/memory/audio-processing"
                if os.path.exists("/sys/fs/cgroup/memory"):
                    os.makedirs(cgroup_path, exist_ok=True)
                    
                    limit_file = f"{cgroup_path}/memory.limit_in_bytes"
                    with open(limit_file, 'w') as f:
                        f.write(str(limit_mb * 1024 * 1024))
                    
                    # 将当前进程加入cgroup
                    procs_file = f"{cgroup_path}/cgroup.procs"
                    with open(procs_file, 'w') as f:
                        f.write(str(os.getpid()))
                    
                    logger.info(f"内存限制设置为: {limit_mb}MB")
            else:
                logger.warning(f"当前平台不支持内存限制: {sys.platform}")
        except Exception as e:
            logger.warning(f"设置内存限制失败: {e}")
    
    def _set_process_priority(self, priority: str):
        """设置进程优先级"""
        try:
            current_process = psutil.Process()
            
            if priority == "high":
                if sys.platform.startswith('linux'):
                    os.nice(-10)  # 提高优先级
                elif sys.platform == 'win32':
                    current_process.nice(psutil.HIGH_PRIORITY_CLASS)
            elif priority == "low":
                if sys.platform.startswith('linux'):
                    os.nice(10)  # 降低优先级
                elif sys.platform == 'win32':
                    current_process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            # normal优先级不需要特殊设置
            
            logger.info(f"进程优先级设置为: {priority}")
        except Exception as e:
            logger.warning(f"设置进程优先级失败: {e}")
    
    def optimize_for_audio_processing(self) -> Dict[str, Any]:
        """针对音频处理进行系统优化"""
        logger.info("优化系统以进行音频处理...")
        
        optimizations = {
            "applied": [],
            "failed": [],
            "recommendations": []
        }
        
        try:
            # 1. 禁用CPU节能功能
            if self._disable_cpu_idle_states():
                optimizations["applied"].append("禁用CPU空闲状态")
            else:
                optimizations["failed"].append("禁用CPU空闲状态")
            
            # 2. 设置音频相关的内核参数
            if self._tune_kernel_parameters():
                optimizations["applied"].append("调整内核参数")
            else:
                optimizations["failed"].append("调整内核参数")
            
            # 3. 设置实时调度优先级
            if self._set_realtime_priority():
                optimizations["applied"].append("设置实时优先级")
            else:
                optimizations["failed"].append("设置实时优先级")
            
            # 4. 优化网络设置
            if self._optimize_network_settings():
                optimizations["applied"].append("优化网络设置")
            else:
                optimizations["failed"].append("优化网络设置")
            
        except Exception as e:
            logger.error(f"系统优化过程中发生错误: {e}")
        
        # 添加建议
        optimizations["recommendations"] = [
            "定期监控系统资源使用情况",
            "根据实际负载调整电源配置文件",
            "确保音频设备驱动程序是最新版本",
            "考虑使用SSD存储以减少I/O延迟"
        ]
        
        return optimizations
    
    def _disable_cpu_idle_states(self) -> bool:
        """禁用CPU空闲状态以减少延迟"""
        try:
            if sys.platform.startswith('linux'):
                # 禁用C-states
                idle_file = "/dev/cpu_dma_latency"
                if os.path.exists(idle_file):
                    # 写入0以禁用深度睡眠状态
                    with open(idle_file, 'wb') as f:
                        f.write(b'\x00\x00\x00\x00')
                    return True
            return False
        except Exception:
            return False
    
    def _tune_kernel_parameters(self) -> bool:
        """调整内核参数"""
        try:
            if sys.platform.startswith('linux'):
                # 音频相关的内核参数
                params = {
                    "/proc/sys/kernel/sched_rt_runtime_us": "950000",  # 实时调度时间
                    "/proc/sys/kernel/sched_rt_period_us": "1000000",
                    "/proc/sys/vm/swappiness": "1",  # 减少交换
                }
                
                for param_file, value in params.items():
                    if os.path.exists(param_file):
                        with open(param_file, 'w') as f:
                            f.write(value)
                return True
            return False
        except Exception:
            return False
    
    def _set_realtime_priority(self) -> bool:
        """设置实时调度优先级"""
        try:
            if sys.platform.startswith('linux'):
                import ctypes
                libc = ctypes.CDLL("libc.so.6")
                
                # 设置SCHED_FIFO调度策略
                SCHED_FIFO = 1
                class SchedParam(ctypes.Structure):
                    _fields_ = [("sched_priority", ctypes.c_int)]
                
                param = SchedParam()
                param.sched_priority = 50  # 中等实时优先级
                
                result = libc.sched_setscheduler(0, SCHED_FIFO, ctypes.byref(param))
                return result == 0
            return False
        except Exception:
            return False
    
    def _optimize_network_settings(self) -> bool:
        """优化网络设置"""
        try:
            if sys.platform.startswith('linux'):
                # 网络相关优化
                net_params = {
                    "/proc/sys/net/core/rmem_max": "16777216",
                    "/proc/sys/net/core/wmem_max": "16777216",
                    "/proc/sys/net/core/netdev_max_backlog": "5000",
                }
                
                for param_file, value in net_params.items():
                    if os.path.exists(param_file):
                        with open(param_file, 'w') as f:
                            f.write(value)
                return True
            return False
        except Exception:
            return False
    
    def start_resource_monitoring(self, interval: float = 5.0):
        """开始资源监控"""
        logger.info(f"开始资源监控，间隔: {interval}秒")
        self.monitoring_active = True
        
        while self.monitoring_active:
            try:
                usage = self.get_current_resource_usage()
                self.resource_history.append(usage)
                
                # 保持历史记录在合理范围内
                if len(self.resource_history) > 1000:
                    self.resource_history = self.resource_history[-500:]
                
                # 检查资源使用情况并给出建议
                self._check_resource_thresholds(usage)
                
                time.sleep(interval)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"资源监控错误: {e}")
                time.sleep(interval)
        
        logger.info("资源监控已停止")
    
    def _check_resource_thresholds(self, usage: ResourceUsage):
        """检查资源使用阈值并给出建议"""
        warnings = []
        
        if usage.cpu_percent > 80:
            warnings.append(f"CPU使用率过高: {usage.cpu_percent:.1f}%")
        
        if usage.memory_percent > 85:
            warnings.append(f"内存使用率过高: {usage.memory_percent:.1f}%")
        
        if warnings:
            logger.warning("资源使用警告: " + ", ".join(warnings))
            
            # 自动建议切换到更节能的配置文件
            if self.current_profile and self.current_profile.name == "performance":
                logger.info("建议切换到 'balanced' 配置文件以减少资源使用")
    
    def get_resource_statistics(self) -> Dict[str, Any]:
        """获取资源使用统计"""
        if not self.resource_history:
            return {}
        
        cpu_values = [r.cpu_percent for r in self.resource_history]
        memory_values = [r.memory_percent for r in self.resource_history]
        
        return {
            "monitoring_duration": len(self.resource_history) * 5.0,  # 假设5秒间隔
            "cpu_usage": {
                "average": sum(cpu_values) / len(cpu_values),
                "max": max(cpu_values),
                "min": min(cpu_values)
            },
            "memory_usage": {
                "average": sum(memory_values) / len(memory_values),
                "max": max(memory_values),
                "min": min(memory_values)
            },
            "current_profile": self.current_profile.name if self.current_profile else None
        }
    
    def generate_power_config(self, target_mode: str = "balanced") -> Dict[str, Any]:
        """生成电源配置"""
        if target_mode not in self.power_profiles:
            target_mode = "balanced"
        
        profile = self.power_profiles[target_mode]
        current_usage = self.get_current_resource_usage()
        
        config = {
            "power_profile": asdict(profile),
            "current_usage": asdict(current_usage),
            "optimizations": self.optimize_for_audio_processing(),
            "recommendations": self._generate_recommendations(profile, current_usage),
            "generated_at": datetime.now().isoformat()
        }
        
        return config
    
    def _generate_recommendations(self, profile: PowerProfile, 
                                usage: ResourceUsage) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        if usage.cpu_percent > 70:
            recommendations.append("考虑升级到更强的CPU或减少并发处理")
        
        if usage.memory_percent > 80:
            recommendations.append("考虑增加内存或启用内存压缩")
        
        if profile.name == "power_save":
            recommendations.append("在电池供电时定期检查电量状态")
            recommendations.append("考虑降低音频质量以延长电池寿命")
        
        if profile.name == "performance":
            recommendations.append("确保散热良好以维持高性能")
            recommendations.append("监控温度以防止过热降频")
        
        return recommendations

def main():
    parser = argparse.ArgumentParser(description="电源管理和资源优化工具")
    parser.add_argument("--profile", "-p",
                       choices=["performance", "balanced", "power_save", "classroom"],
                       default="balanced",
                       help="电源配置文件")
    parser.add_argument("--monitor", "-m", action="store_true",
                       help="启动资源监控")
    parser.add_argument("--optimize", "-opt", action="store_true",
                       help="执行系统优化")
    parser.add_argument("--output", "-o", default="power_config",
                       help="输出目录")
    parser.add_argument("--interval", "-i", type=float, default=5.0,
                       help="监控间隔（秒）")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    manager = PowerManager()
    
    try:
        # 应用电源配置文件
        if manager.apply_power_profile(args.profile):
            print(f"✓ 已应用电源配置文件: {args.profile}")
        
        # 执行系统优化
        if args.optimize:
            optimizations = manager.optimize_for_audio_processing()
            print(f"✓ 系统优化完成")
            print(f"  成功: {len(optimizations['applied'])} 项")
            print(f"  失败: {len(optimizations['failed'])} 项")
        
        # 生成配置文件
        config = manager.generate_power_config(args.profile)
        
        # 保存配置
        config_file = Path(args.output) / "power_config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"✓ 电源配置已保存: {config_file}")
        
        # 显示当前状态
        current_usage = manager.get_current_resource_usage()
        print(f"\n当前资源使用:")
        print(f"  CPU: {current_usage.cpu_percent:.1f}%")
        print(f"  内存: {current_usage.memory_percent:.1f}% ({current_usage.memory_mb}MB)")
        
        # 启动监控
        if args.monitor:
            print(f"\n开始资源监控 (Ctrl+C 停止)...")
            manager.start_resource_monitoring(args.interval)
    
    except KeyboardInterrupt:
        print("\n监控已停止")
    except Exception as e:
        logger.error(f"电源管理失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()