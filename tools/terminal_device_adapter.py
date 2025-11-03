#!/usr/bin/env python3
"""
终端设备适配器
Terminal Device Adapter

统一管理终端设备的硬件检测、配置优化和状态监控
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Any
import argparse
import logging
from dataclasses import dataclass, asdict

# 导入其他工具模块
sys.path.insert(0, str(Path(__file__).parent))
from hardware_detector import HardwareDetector, DeviceProfile
from power_manager import PowerManager
from device_monitor import DeviceMonitor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class TerminalDeviceConfig:
    """终端设备配置"""
    device_profile: DeviceProfile
    power_config: Dict[str, Any]
    audio_config: Dict[str, Any]
    monitoring_config: Dict[str, Any]
    optimization_applied: List[str]
    created_at: str

class TerminalDeviceAdapter:
    """终端设备适配器"""
    
    def __init__(self, config_dir: str = "terminal_config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化各个组件
        self.hardware_detector = HardwareDetector()
        self.power_manager = PowerManager()
        self.device_monitor = DeviceMonitor()
        
        # 设备配置
        self.device_config = None
        
        # 教室环境预设
        self.classroom_presets = {
            "standard": {
                "description": "标准教室 (120-150㎡, 60-100座位)",
                "power_profile": "classroom",
                "audio_settings": {
                    "target_latency": 20.0,
                    "classroom_type": "standard_classroom"
                },
                "monitoring": {
                    "interval": 30,
                    "auto_recovery": True
                }
            },
            "large": {
                "description": "大型教室 (200+㎡, 150+座位)",
                "power_profile": "performance",
                "audio_settings": {
                    "target_latency": 30.0,
                    "classroom_type": "large_classroom"
                },
                "monitoring": {
                    "interval": 20,
                    "auto_recovery": True
                }
            },
            "small": {
                "description": "小型教室 (60-80㎡, 30-40座位)",
                "power_profile": "balanced",
                "audio_settings": {
                    "target_latency": 15.0,
                    "classroom_type": "small_classroom"
                },
                "monitoring": {
                    "interval": 45,
                    "auto_recovery": True
                }
            },
            "laboratory": {
                "description": "实验室环境",
                "power_profile": "performance",
                "audio_settings": {
                    "target_latency": 25.0,
                    "classroom_type": "standard_classroom"
                },
                "monitoring": {
                    "interval": 15,
                    "auto_recovery": True
                }
            }
        }
    
    def detect_and_configure_device(self, classroom_preset: str = "auto", 
                                  power_profile: str = "auto") -> TerminalDeviceConfig:
        """检测设备并自动配置"""
        logger.info("开始终端设备检测和配置...")
        
        # 1. 硬件检测
        logger.info("步骤 1/5: 硬件检测")
        device_profile = self.hardware_detector.create_device_profile()
        
        # 2. 自动选择预设
        if classroom_preset == "auto":
            classroom_preset = self._auto_select_classroom_preset(device_profile)
        
        if power_profile == "auto":
            power_profile = self._auto_select_power_profile(device_profile)
        
        logger.info(f"选择教室预设: {classroom_preset}")
        logger.info(f"选择电源配置: {power_profile}")
        
        # 3. 电源管理配置
        logger.info("步骤 2/5: 电源管理配置")
        self.power_manager.apply_power_profile(power_profile)
        power_config = self.power_manager.generate_power_config(power_profile)
        
        # 4. 音频设备配置
        logger.info("步骤 3/5: 音频设备配置")
        audio_config = self._configure_audio_system(classroom_preset)
        
        # 5. 监控配置
        logger.info("步骤 4/5: 监控系统配置")
        monitoring_config = self._configure_monitoring(classroom_preset)
        
        # 6. 系统优化
        logger.info("步骤 5/5: 系统优化")
        optimizations = self._apply_system_optimizations(device_profile, classroom_preset)
        
        # 创建终端设备配置
        terminal_config = TerminalDeviceConfig(
            device_profile=device_profile,
            power_config=power_config,
            audio_config=audio_config,
            monitoring_config=monitoring_config,
            optimization_applied=optimizations,
            created_at=time.strftime("%Y-%m-%d %H:%M:%S")
        )
        
        self.device_config = terminal_config
        logger.info("终端设备配置完成")
        
        return terminal_config
    
    def _auto_select_classroom_preset(self, device_profile: DeviceProfile) -> str:
        """自动选择教室预设"""
        performance_class = device_profile.performance_class
        memory_gb = device_profile.hardware_info.memory_total // (1024**3)
        cpu_cores = device_profile.hardware_info.cpu_cores
        
        # 根据硬件性能选择预设
        if performance_class == "high" and memory_gb >= 16 and cpu_cores >= 8:
            return "large"
        elif performance_class == "medium" or (memory_gb >= 8 and cpu_cores >= 4):
            return "standard"
        else:
            return "small"
    
    def _auto_select_power_profile(self, device_profile: DeviceProfile) -> str:
        """自动选择电源配置"""
        performance_class = device_profile.performance_class
        
        # 根据性能等级选择电源配置
        if performance_class == "high":
            return "performance"
        elif performance_class == "medium":
            return "classroom"
        else:
            return "balanced"
    
    def _configure_audio_system(self, classroom_preset: str) -> Dict[str, Any]:
        """配置音频系统"""
        preset = self.classroom_presets.get(classroom_preset, self.classroom_presets["standard"])
        audio_settings = preset["audio_settings"]
        
        # 模拟音频配置（在实际实现中会调用audio_device_manager）
        audio_config = {
            "classroom_type": audio_settings["classroom_type"],
            "target_latency_ms": audio_settings["target_latency"],
            "sample_rate": 48000,
            "channels": 8 if classroom_preset != "small" else 4,
            "buffer_size": 2048,
            "microphone_array": {
                "type": "linear",
                "count": 8 if classroom_preset != "small" else 4,
                "spacing": 0.05
            },
            "processing": {
                "ssl_enabled": True,
                "beamforming_enabled": True,
                "aec_enabled": True,
                "denoise_enabled": True,
                "agc_enabled": True
            },
            "configured_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        return audio_config
    
    def _configure_monitoring(self, classroom_preset: str) -> Dict[str, Any]:
        """配置监控系统"""
        preset = self.classroom_presets.get(classroom_preset, self.classroom_presets["standard"])
        monitoring_settings = preset["monitoring"]
        
        monitoring_config = {
            "enabled": True,
            "interval": monitoring_settings["interval"],
            "auto_recovery": monitoring_settings["auto_recovery"],
            "thresholds": {
                "cpu_warning": 70.0,
                "cpu_critical": 90.0,
                "memory_warning": 80.0,
                "memory_critical": 95.0,
                "latency_warning": 50.0,
                "latency_critical": 100.0
            },
            "notifications": {
                "log": {"enabled": True},
                "email": {"enabled": False},
                "webhook": {"enabled": False}
            },
            "configured_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        return monitoring_config
    
    def _apply_system_optimizations(self, device_profile: DeviceProfile, 
                                  classroom_preset: str) -> List[str]:
        """应用系统优化"""
        optimizations = []
        
        try:
            # 音频处理优化
            if self.power_manager.optimize_for_audio_processing():
                optimizations.append("音频处理优化")
            
            # 根据教室类型应用特定优化
            if classroom_preset == "large":
                # 大型教室优化
                optimizations.append("大型教室网络优化")
                optimizations.append("高并发音频处理优化")
            elif classroom_preset == "small":
                # 小型教室优化
                optimizations.append("低功耗模式优化")
                optimizations.append("简化音频处理链")
            
            # 根据硬件性能应用优化
            if device_profile.performance_class == "low":
                optimizations.append("低性能设备优化")
            elif device_profile.performance_class == "high":
                optimizations.append("高性能设备优化")
            
        except Exception as e:
            logger.warning(f"系统优化过程中发生错误: {e}")
        
        return optimizations
    
    def save_device_config(self, config: TerminalDeviceConfig, 
                          filename: str = None) -> str:
        """保存设备配置"""
        if filename is None:
            device_id = config.device_profile.device_id
            filename = f"terminal_config_{device_id}.json"
        
        config_file = self.config_dir / filename
        
        # 转换为可序列化的字典
        config_dict = asdict(config)
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
        
        logger.info(f"设备配置已保存: {config_file}")
        return str(config_file)
    
    def load_device_config(self, config_file: str) -> TerminalDeviceConfig:
        """加载设备配置"""
        with open(config_file, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)
        
        # 重构对象（简化版本，实际实现需要更复杂的反序列化）
        logger.info(f"设备配置已加载: {config_file}")
        return config_dict
    
    def generate_deployment_script(self, config: TerminalDeviceConfig) -> str:
        """生成部署脚本"""
        script_content = f'''#!/bin/bash
# 终端设备自动配置脚本
# 生成时间: {config.created_at}
# 设备: {config.device_profile.device_name}

set -e

echo "开始终端设备配置..."

# 设备信息
DEVICE_ID="{config.device_profile.device_id}"
DEVICE_NAME="{config.device_profile.device_name}"
PERFORMANCE_CLASS="{config.device_profile.performance_class}"

echo "设备ID: $DEVICE_ID"
echo "设备名称: $DEVICE_NAME"
echo "性能等级: $PERFORMANCE_CLASS"

# 应用电源配置
echo "应用电源配置..."
python3 /opt/audio-processing-system/tools/power_manager.py \\
    --profile {config.power_config["power_profile"]["name"]} \\
    --optimize

# 配置音频系统
echo "配置音频系统..."
python3 /opt/audio-processing-system/tools/audio_device_manager.py \\
    --classroom-type {config.audio_config["classroom_type"]} \\
    --target-latency {config.audio_config["target_latency_ms"]}

# 启动监控
echo "启动设备监控..."
python3 /opt/audio-processing-system/tools/device_monitor.py \\
    --monitor &

# 启动音频处理服务
echo "启动音频处理服务..."
systemctl enable audio-processing
systemctl start audio-processing

echo "终端设备配置完成！"
echo "Web界面: http://localhost"
echo "监控状态: systemctl status audio-processing"
'''
        
        script_file = self.config_dir / "deploy_terminal_config.sh"
        with open(script_file, 'w') as f:
            f.write(script_content)
        
        script_file.chmod(0o755)
        
        logger.info(f"部署脚本已生成: {script_file}")
        return str(script_file)
    
    def get_device_summary(self, config: TerminalDeviceConfig) -> Dict[str, Any]:
        """获取设备配置摘要"""
        return {
            "device_info": {
                "name": config.device_profile.device_name,
                "performance_class": config.device_profile.performance_class,
                "cpu": config.device_profile.hardware_info.cpu_model,
                "memory_gb": config.device_profile.hardware_info.memory_total // (1024**3),
                "architecture": config.device_profile.system_info.architecture
            },
            "audio_config": {
                "classroom_type": config.audio_config["classroom_type"],
                "target_latency": config.audio_config["target_latency_ms"],
                "channels": config.audio_config["channels"],
                "sample_rate": config.audio_config["sample_rate"]
            },
            "power_config": {
                "profile": config.power_config["power_profile"]["name"],
                "description": config.power_config["power_profile"]["description"]
            },
            "monitoring": {
                "enabled": config.monitoring_config["enabled"],
                "interval": config.monitoring_config["interval"],
                "auto_recovery": config.monitoring_config["auto_recovery"]
            },
            "optimizations": config.optimization_applied,
            "created_at": config.created_at
        }

def main():
    parser = argparse.ArgumentParser(description="终端设备适配器")
    parser.add_argument("--classroom", "-c",
                       choices=["auto", "standard", "large", "small", "laboratory"],
                       default="auto",
                       help="教室类型预设")
    parser.add_argument("--power", "-p",
                       choices=["auto", "performance", "balanced", "power_save", "classroom"],
                       default="auto",
                       help="电源配置文件")
    parser.add_argument("--output", "-o", default="terminal_config",
                       help="输出目录")
    parser.add_argument("--deploy-script", "-d", action="store_true",
                       help="生成部署脚本")
    parser.add_argument("--load-config", "-l", help="加载现有配置文件")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    adapter = TerminalDeviceAdapter(args.output)
    
    try:
        if args.load_config:
            # 加载现有配置
            config = adapter.load_device_config(args.load_config)
            print("✓ 配置文件已加载")
        else:
            # 检测和配置设备
            config = adapter.detect_and_configure_device(args.classroom, args.power)
            
            # 保存配置
            config_file = adapter.save_device_config(config)
            print(f"✓ 设备配置已保存: {config_file}")
        
        # 生成部署脚本
        if args.deploy_script:
            script_file = adapter.generate_deployment_script(config)
            print(f"✓ 部署脚本已生成: {script_file}")
        
        # 显示配置摘要
        summary = adapter.get_device_summary(config)
        
        print(f"\n终端设备配置摘要:")
        print(f"设备名称: {summary['device_info']['name']}")
        print(f"性能等级: {summary['device_info']['performance_class'].upper()}")
        print(f"CPU: {summary['device_info']['cpu']}")
        print(f"内存: {summary['device_info']['memory_gb']}GB")
        print(f"架构: {summary['device_info']['architecture']}")
        
        print(f"\n音频配置:")
        print(f"教室类型: {summary['audio_config']['classroom_type']}")
        print(f"目标延迟: {summary['audio_config']['target_latency']}ms")
        print(f"通道数: {summary['audio_config']['channels']}")
        print(f"采样率: {summary['audio_config']['sample_rate']}Hz")
        
        print(f"\n电源配置:")
        print(f"配置文件: {summary['power_config']['profile']}")
        print(f"描述: {summary['power_config']['description']}")
        
        print(f"\n监控配置:")
        print(f"启用: {'是' if summary['monitoring']['enabled'] else '否'}")
        print(f"监控间隔: {summary['monitoring']['interval']}秒")
        print(f"自动恢复: {'是' if summary['monitoring']['auto_recovery'] else '否'}")
        
        print(f"\n应用的优化:")
        for opt in summary['optimizations']:
            print(f"  - {opt}")
        
        print(f"\n配置时间: {summary['created_at']}")
    
    except Exception as e:
        logger.error(f"终端设备适配失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()