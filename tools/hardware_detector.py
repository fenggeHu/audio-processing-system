#!/usr/bin/env python3
"""
硬件检测和配置工具
Hardware Detection and Configuration Tool

自动检测终端设备硬件配置并生成优化的系统配置
"""

import os
import sys
import json
import subprocess
import platform
import psutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
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
class AudioDevice:
    """音频设备信息"""
    name: str
    device_id: str
    channels: int
    sample_rates: List[int]
    device_type: str  # input/output
    driver: str
    is_default: bool = False

@dataclass
class SystemInfo:
    """系统信息"""
    hostname: str
    os_name: str
    os_version: str
    architecture: str
    kernel_version: str
    python_version: str

@dataclass
class HardwareInfo:
    """硬件信息"""
    cpu_model: str
    cpu_cores: int
    cpu_threads: int
    cpu_frequency: float
    memory_total: int
    memory_available: int
    storage_total: int
    storage_available: int
    network_interfaces: List[Dict[str, str]]

@dataclass
class DeviceProfile:
    """设备配置文件"""
    device_id: str
    device_name: str
    system_info: SystemInfo
    hardware_info: HardwareInfo
    audio_devices: List[AudioDevice]
    performance_class: str  # high/medium/low
    power_profile: str  # performance/balanced/power_save
    recommended_config: Dict[str, Any]
    created_at: str

class HardwareDetector:
    """硬件检测器"""
    
    def __init__(self):
        self.audio_devices = []
        self.system_info = None
        self.hardware_info = None
        
        # 性能分类阈值
        self.performance_thresholds = {
            'high': {'cpu_cores': 8, 'memory_gb': 8, 'cpu_freq': 2.5},
            'medium': {'cpu_cores': 4, 'memory_gb': 4, 'cpu_freq': 2.0},
            'low': {'cpu_cores': 2, 'memory_gb': 2, 'cpu_freq': 1.5}
        }
    
    def detect_system_info(self) -> SystemInfo:
        """检测系统信息"""
        logger.info("检测系统信息...")
        
        try:
            # 获取主机名
            hostname = platform.node()
            
            # 获取操作系统信息
            os_info = platform.platform()
            os_name = platform.system()
            os_version = platform.release()
            
            # 获取架构信息
            architecture = platform.machine()
            
            # 获取内核版本
            kernel_version = platform.release()
            
            # 获取Python版本
            python_version = platform.python_version()
            
            self.system_info = SystemInfo(
                hostname=hostname,
                os_name=os_name,
                os_version=os_version,
                architecture=architecture,
                kernel_version=kernel_version,
                python_version=python_version
            )
            
            logger.info(f"系统: {os_name} {os_version} ({architecture})")
            logger.info(f"主机名: {hostname}")
            
            return self.system_info
            
        except Exception as e:
            logger.error(f"系统信息检测失败: {e}")
            raise
    
    def detect_hardware_info(self) -> HardwareInfo:
        """检测硬件信息"""
        logger.info("检测硬件信息...")
        
        try:
            # CPU信息
            cpu_model = self._get_cpu_model()
            cpu_cores = psutil.cpu_count(logical=False)
            cpu_threads = psutil.cpu_count(logical=True)
            cpu_frequency = psutil.cpu_freq().max if psutil.cpu_freq() else 0.0
            
            # 内存信息
            memory = psutil.virtual_memory()
            memory_total = memory.total
            memory_available = memory.available
            
            # 存储信息
            disk = psutil.disk_usage('/')
            storage_total = disk.total
            storage_available = disk.free
            
            # 网络接口
            network_interfaces = self._get_network_interfaces()
            
            self.hardware_info = HardwareInfo(
                cpu_model=cpu_model,
                cpu_cores=cpu_cores,
                cpu_threads=cpu_threads,
                cpu_frequency=cpu_frequency / 1000.0 if cpu_frequency else 0.0,  # 转换为GHz
                memory_total=memory_total,
                memory_available=memory_available,
                storage_total=storage_total,
                storage_available=storage_available,
                network_interfaces=network_interfaces
            )
            
            logger.info(f"CPU: {cpu_model} ({cpu_cores}核/{cpu_threads}线程)")
            logger.info(f"内存: {memory_total // (1024**3)}GB")
            logger.info(f"存储: {storage_total // (1024**3)}GB")
            
            return self.hardware_info
            
        except Exception as e:
            logger.error(f"硬件信息检测失败: {e}")
            raise
    
    def _get_cpu_model(self) -> str:
        """获取CPU型号"""
        try:
            if platform.system() == "Linux":
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if line.startswith('model name'):
                            return line.split(':')[1].strip()
            elif platform.system() == "Darwin":  # macOS
                result = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout.strip()
            elif platform.system() == "Windows":
                result = subprocess.run(['wmic', 'cpu', 'get', 'name'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) > 1:
                        return lines[1].strip()
        except Exception:
            pass
        
        return "Unknown CPU"
    
    def _get_network_interfaces(self) -> List[Dict[str, str]]:
        """获取网络接口信息"""
        interfaces = []
        
        try:
            net_if_addrs = psutil.net_if_addrs()
            net_if_stats = psutil.net_if_stats()
            
            for interface_name, addresses in net_if_addrs.items():
                if interface_name in net_if_stats:
                    stats = net_if_stats[interface_name]
                    
                    # 获取IP地址
                    ip_address = None
                    for addr in addresses:
                        if addr.family == 2:  # AF_INET (IPv4)
                            ip_address = addr.address
                            break
                    
                    if ip_address and stats.isup:
                        interfaces.append({
                            'name': interface_name,
                            'ip_address': ip_address,
                            'speed': f"{stats.speed}Mbps" if stats.speed > 0 else "Unknown",
                            'status': 'up' if stats.isup else 'down'
                        })
        except Exception as e:
            logger.warning(f"网络接口检测失败: {e}")
        
        return interfaces
    
    def detect_audio_devices(self) -> List[AudioDevice]:
        """检测音频设备"""
        logger.info("检测音频设备...")
        
        self.audio_devices = []
        
        try:
            # 尝试使用pyaudio检测
            self._detect_with_pyaudio()
        except ImportError:
            logger.warning("pyaudio未安装，尝试使用系统命令")
            self._detect_with_system_commands()
        except Exception as e:
            logger.warning(f"pyaudio检测失败: {e}，尝试使用系统命令")
            self._detect_with_system_commands()
        
        logger.info(f"检测到 {len(self.audio_devices)} 个音频设备")
        return self.audio_devices
    
    def _detect_with_pyaudio(self):
        """使用pyaudio检测音频设备"""
        try:
            import pyaudio
            
            pa = pyaudio.PyAudio()
            
            for i in range(pa.get_device_count()):
                device_info = pa.get_device_info_by_index(i)
                
                # 获取支持的采样率
                sample_rates = self._test_sample_rates(pa, i, device_info)
                
                # 确定设备类型
                device_type = []
                if device_info['maxInputChannels'] > 0:
                    device_type.append('input')
                if device_info['maxOutputChannels'] > 0:
                    device_type.append('output')
                
                for dtype in device_type:
                    channels = (device_info['maxInputChannels'] 
                              if dtype == 'input' 
                              else device_info['maxOutputChannels'])
                    
                    audio_device = AudioDevice(
                        name=device_info['name'],
                        device_id=str(i),
                        channels=channels,
                        sample_rates=sample_rates,
                        device_type=dtype,
                        driver=device_info.get('hostApi', 'unknown'),
                        is_default=(i == pa.get_default_input_device_info()['index'] 
                                  if dtype == 'input' 
                                  else i == pa.get_default_output_device_info()['index'])
                    )
                    
                    self.audio_devices.append(audio_device)
            
            pa.terminate()
            
        except Exception as e:
            logger.error(f"pyaudio检测失败: {e}")
            raise
    
    def _test_sample_rates(self, pa, device_index: int, device_info: dict) -> List[int]:
        """测试设备支持的采样率"""
        import pyaudio
        
        test_rates = [8000, 16000, 22050, 44100, 48000, 96000, 192000]
        supported_rates = []
        
        for rate in test_rates:
            try:
                # 测试输入
                if device_info['maxInputChannels'] > 0:
                    pa.is_format_supported(
                        rate,
                        input_device=device_index,
                        input_channels=1,
                        input_format=pyaudio.paInt16
                    )
                    supported_rates.append(rate)
                    continue
                
                # 测试输出
                if device_info['maxOutputChannels'] > 0:
                    pa.is_format_supported(
                        rate,
                        output_device=device_index,
                        output_channels=1,
                        output_format=pyaudio.paInt16
                    )
                    supported_rates.append(rate)
                    
            except Exception:
                continue
        
        return supported_rates if supported_rates else [44100]  # 默认采样率
    
    def _detect_with_system_commands(self):
        """使用系统命令检测音频设备"""
        if platform.system() == "Linux":
            self._detect_linux_audio_devices()
        elif platform.system() == "Darwin":
            self._detect_macos_audio_devices()
        elif platform.system() == "Windows":
            self._detect_windows_audio_devices()
    
    def _detect_linux_audio_devices(self):
        """检测Linux音频设备"""
        try:
            # 使用arecord和aplay检测
            input_devices = self._parse_alsa_devices('arecord')
            output_devices = self._parse_alsa_devices('aplay')
            
            self.audio_devices.extend(input_devices)
            self.audio_devices.extend(output_devices)
            
        except Exception as e:
            logger.warning(f"Linux音频设备检测失败: {e}")
    
    def _parse_alsa_devices(self, command: str) -> List[AudioDevice]:
        """解析ALSA设备列表"""
        devices = []
        device_type = 'input' if command == 'arecord' else 'output'
        
        try:
            result = subprocess.run([command, '-l'], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'card' in line and ':' in line:
                        # 解析设备信息
                        parts = line.split(':')
                        if len(parts) >= 2:
                            device_name = parts[1].strip()
                            device_id = parts[0].strip()
                            
                            audio_device = AudioDevice(
                                name=device_name,
                                device_id=device_id,
                                channels=2,  # 默认立体声
                                sample_rates=[44100, 48000],  # 常见采样率
                                device_type=device_type,
                                driver='ALSA'
                            )
                            
                            devices.append(audio_device)
        except Exception as e:
            logger.warning(f"ALSA设备解析失败: {e}")
        
        return devices
    
    def _detect_macos_audio_devices(self):
        """检测macOS音频设备"""
        # macOS音频设备检测实现
        pass
    
    def _detect_windows_audio_devices(self):
        """检测Windows音频设备"""
        # Windows音频设备检测实现
        pass
    
    def classify_performance(self) -> str:
        """分类设备性能等级"""
        if not self.hardware_info:
            return 'low'
        
        cpu_cores = self.hardware_info.cpu_cores
        memory_gb = self.hardware_info.memory_total // (1024**3)
        cpu_freq = self.hardware_info.cpu_frequency
        
        # 高性能设备
        if (cpu_cores >= self.performance_thresholds['high']['cpu_cores'] and
            memory_gb >= self.performance_thresholds['high']['memory_gb'] and
            cpu_freq >= self.performance_thresholds['high']['cpu_freq']):
            return 'high'
        
        # 中等性能设备
        elif (cpu_cores >= self.performance_thresholds['medium']['cpu_cores'] and
              memory_gb >= self.performance_thresholds['medium']['memory_gb'] and
              cpu_freq >= self.performance_thresholds['medium']['cpu_freq']):
            return 'medium'
        
        # 低性能设备
        else:
            return 'low'
    
    def generate_recommended_config(self, performance_class: str, 
                                  power_profile: str = 'balanced') -> Dict[str, Any]:
        """生成推荐配置"""
        logger.info(f"生成推荐配置: {performance_class} 性能, {power_profile} 功耗")
        
        # 基础配置
        config = {
            "system": {
                "performance_class": performance_class,
                "power_profile": power_profile,
                "auto_optimization": True
            },
            "audio": {
                "sample_rate": 48000,
                "frame_size": 480,
                "channels": 8,
                "buffer_size": 2048
            },
            "processing": {
                "thread_count": min(self.hardware_info.cpu_cores, 8),
                "enable_simd": True,
                "memory_pool_size": "auto"
            },
            "services": {
                "capture": {"enabled": True},
                "ssl": {"enabled": True},
                "beamformer": {"enabled": True},
                "aec": {"enabled": True},
                "denoise": {"enabled": True},
                "agc": {"enabled": True}
            }
        }
        
        # 根据性能等级调整配置
        if performance_class == 'high':
            config["audio"]["buffer_size"] = 4096
            config["audio"]["frame_size"] = 240  # 5ms低延迟
            config["services"]["beamformer"]["algorithm"] = "MVDR"
            config["services"]["denoise"]["strength"] = "aggressive"
            config["processing"]["enable_gpu"] = True
            
        elif performance_class == 'medium':
            config["audio"]["buffer_size"] = 2048
            config["audio"]["frame_size"] = 480  # 10ms标准延迟
            config["services"]["beamformer"]["algorithm"] = "DAS"
            config["services"]["denoise"]["strength"] = "moderate"
            
        elif performance_class == 'low':
            config["audio"]["buffer_size"] = 1024
            config["audio"]["frame_size"] = 960  # 20ms高延迟
            config["audio"]["channels"] = 4  # 减少通道数
            config["services"]["beamformer"]["algorithm"] = "DAS"
            config["services"]["denoise"]["strength"] = "light"
            config["processing"]["thread_count"] = 2
            
            # 禁用一些高级功能
            config["services"]["ssl"]["enabled"] = False
        
        # 根据功耗配置调整
        if power_profile == 'power_save':
            config["processing"]["cpu_affinity"] = [0, 1]  # 限制CPU核心
            config["audio"]["buffer_size"] *= 2  # 增大缓冲区减少唤醒
            config["services"]["ssl"]["update_interval_ms"] = 200  # 降低更新频率
            
        elif power_profile == 'performance':
            config["processing"]["cpu_priority"] = "high"
            config["processing"]["memory_lock"] = True
            config["audio"]["buffer_size"] = max(config["audio"]["buffer_size"] // 2, 512)
        
        # 音频设备配置
        if self.audio_devices:
            # 选择最佳输入设备
            input_devices = [d for d in self.audio_devices if d.device_type == 'input']
            if input_devices:
                best_input = max(input_devices, key=lambda x: x.channels)
                config["audio"]["input_device"] = best_input.device_id
                config["audio"]["channels"] = min(best_input.channels, config["audio"]["channels"])
            
            # 选择最佳输出设备
            output_devices = [d for d in self.audio_devices if d.device_type == 'output']
            if output_devices:
                best_output = max(output_devices, key=lambda x: x.channels)
                config["audio"]["output_device"] = best_output.device_id
        
        return config
    
    def create_device_profile(self, power_profile: str = 'balanced') -> DeviceProfile:
        """创建设备配置文件"""
        logger.info("创建设备配置文件...")
        
        # 检测所有信息
        system_info = self.detect_system_info()
        hardware_info = self.detect_hardware_info()
        audio_devices = self.detect_audio_devices()
        
        # 分类性能等级
        performance_class = self.classify_performance()
        
        # 生成推荐配置
        recommended_config = self.generate_recommended_config(performance_class, power_profile)
        
        # 生成设备ID
        device_id = f"{system_info.hostname}_{system_info.architecture}_{int(time.time())}"
        
        # 创建设备名称
        device_name = f"{system_info.hostname} ({performance_class.upper()})"
        
        profile = DeviceProfile(
            device_id=device_id,
            device_name=device_name,
            system_info=system_info,
            hardware_info=hardware_info,
            audio_devices=audio_devices,
            performance_class=performance_class,
            power_profile=power_profile,
            recommended_config=recommended_config,
            created_at=datetime.now().isoformat()
        )
        
        return profile
    
    def save_device_profile(self, profile: DeviceProfile, output_path: str) -> str:
        """保存设备配置文件"""
        profile_dict = asdict(profile)
        
        output_file = Path(output_path) / f"device_profile_{profile.device_id}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(profile_dict, f, indent=2, ensure_ascii=False)
        
        logger.info(f"设备配置文件已保存: {output_file}")
        return str(output_file)

def main():
    parser = argparse.ArgumentParser(description="硬件检测和配置工具")
    parser.add_argument("--output", "-o", default="device_profiles",
                       help="输出目录")
    parser.add_argument("--power-profile", "-p", 
                       choices=['performance', 'balanced', 'power_save'],
                       default='balanced',
                       help="功耗配置")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="详细输出")
    parser.add_argument("--json-only", action="store_true",
                       help="仅输出JSON格式")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    detector = HardwareDetector()
    
    try:
        # 创建设备配置文件
        profile = detector.create_device_profile(args.power_profile)
        
        if args.json_only:
            # 仅输出JSON
            print(json.dumps(asdict(profile), indent=2, ensure_ascii=False))
        else:
            # 保存配置文件并显示摘要
            profile_path = detector.save_device_profile(profile, args.output)
            
            print(f"\n✓ 设备检测完成")
            print(f"设备名称: {profile.device_name}")
            print(f"性能等级: {profile.performance_class.upper()}")
            print(f"功耗配置: {profile.power_profile}")
            print(f"CPU: {profile.hardware_info.cpu_model}")
            print(f"内存: {profile.hardware_info.memory_total // (1024**3)}GB")
            print(f"音频设备: {len(profile.audio_devices)}个")
            print(f"配置文件: {profile_path}")
            
            # 显示推荐配置摘要
            config = profile.recommended_config
            print(f"\n推荐配置:")
            print(f"  采样率: {config['audio']['sample_rate']}Hz")
            print(f"  帧大小: {config['audio']['frame_size']} samples")
            print(f"  通道数: {config['audio']['channels']}")
            print(f"  缓冲区: {config['audio']['buffer_size']} samples")
            print(f"  线程数: {config['processing']['thread_count']}")
    
    except Exception as e:
        logger.error(f"设备检测失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()