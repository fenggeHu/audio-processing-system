#!/usr/bin/env python3
"""
配置文件生成器
Configuration Generator

为不同的部署场景生成配置文件模板
"""

import json
from pathlib import Path
from typing import Dict, Any, List
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ConfigGenerator:
    """配置文件生成器"""
    
    def __init__(self, output_dir: str = "config/templates"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 预定义的配置模板
        self.templates = {
            "classroom_standard": self._get_classroom_standard_config(),
            "classroom_large": self._get_classroom_large_config(),
            "classroom_small": self._get_classroom_small_config(),
            "laboratory": self._get_laboratory_config(),
            "conference_room": self._get_conference_room_config(),
            "auditorium": self._get_auditorium_config(),
            "development": self._get_development_config(),
            "production": self._get_production_config()
        }
    
    def _get_classroom_standard_config(self) -> Dict[str, Any]:
        """标准教室配置（120-150㎡，60-100座位）"""
        return {
            "system": {
                "name": "classroom_standard",
                "description": "标准多媒体教室音频处理系统",
                "environment": "production",
                "debug": False,
                "log_level": "INFO"
            },
            "audio": {
                "sample_rate": 48000,
                "frame_size": 480,  # 10ms
                "channels": 8,
                "buffer_size": 2048,
                "max_latency_ms": 40.0,
                "input_device": "auto",
                "output_device": "auto"
            },
            "microphone_array": {
                "type": "linear",
                "count": 8,
                "spacing": 0.05,  # 5cm间距
                "positions": [
                    [0.0, 0.0], [0.05, 0.0], [0.10, 0.0], [0.15, 0.0],
                    [0.20, 0.0], [0.25, 0.0], [0.30, 0.0], [0.35, 0.0]
                ],
                "calibration": {
                    "auto_calibrate": True,
                    "calibration_signal": "sweep",
                    "calibration_duration": 10.0
                }
            },
            "room_acoustics": {
                "dimensions": [12.0, 10.0, 3.0],  # 长x宽x高 (米)
                "reverberation_time": 0.8,
                "background_noise_level": -45.0,  # dBFS
                "teacher_area": {
                    "x_range": [0.0, 4.0],
                    "y_range": [0.0, 2.0]
                },
                "student_area": {
                    "x_range": [4.0, 12.0],
                    "y_range": [0.0, 10.0]
                }
            },
            "services": {
                "capture": {
                    "enabled": True,
                    "sync_tolerance_ms": 1.0
                },
                "ssl": {
                    "enabled": True,
                    "algorithm": "SRP-PHAT",
                    "update_interval_ms": 100,
                    "smoothing_factor": 0.3
                },
                "beamformer": {
                    "enabled": True,
                    "algorithm": "DAS",
                    "adaptive": True,
                    "target_gain_db": 10.0
                },
                "aec": {
                    "enabled": True,
                    "filter_length": 256,
                    "adaptation_rate": 0.1,
                    "double_talk_threshold": 0.5,
                    "target_erle_db": 20.0
                },
                "denoise": {
                    "enabled": True,
                    "algorithm": "RNNoise",
                    "strength": "moderate",
                    "preserve_speech": True
                },
                "agc": {
                    "enabled": True,
                    "target_level_dbfs": -18.0,
                    "max_gain_db": 20.0,
                    "attack_time_ms": 20.0,
                    "release_time_ms": 400.0,
                    "noise_gate_threshold_dbfs": -50.0
                }
            },
            "output": {
                "pa_system": {
                    "enabled": True,
                    "target_level_dbfs": -18.0,
                    "limiter_threshold_dbfs": -6.0,
                    "eq_enabled": True
                },
                "recording": {
                    "enabled": True,
                    "format": "wav",
                    "bitrate": 192000,
                    "target_level_dbfs": -20.0,
                    "auto_start": True
                },
                "streaming": {
                    "enabled": False,
                    "protocol": "RTMP",
                    "url": "",
                    "bitrate": 128000
                }
            },
            "monitoring": {
                "metrics_enabled": True,
                "health_check_interval": 30,
                "performance_logging": True,
                "audio_quality_monitoring": True
            },
            "web_interface": {
                "enabled": True,
                "host": "0.0.0.0",
                "port": 8000,
                "auth_required": False
            }
        }
    
    def _get_classroom_large_config(self) -> Dict[str, Any]:
        """大型教室配置（200+㎡，150+座位）"""
        config = self._get_classroom_standard_config()
        
        # 调整大型教室的参数
        config["system"]["name"] = "classroom_large"
        config["system"]["description"] = "大型多媒体教室音频处理系统"
        
        config["audio"]["channels"] = 16  # 更多麦克风
        config["microphone_array"]["count"] = 16
        config["microphone_array"]["type"] = "planar"
        config["microphone_array"]["positions"] = [
            [0.0, 0.0], [0.1, 0.0], [0.2, 0.0], [0.3, 0.0],
            [0.0, 0.1], [0.1, 0.1], [0.2, 0.1], [0.3, 0.1],
            [0.0, 0.2], [0.1, 0.2], [0.2, 0.2], [0.3, 0.2],
            [0.0, 0.3], [0.1, 0.3], [0.2, 0.3], [0.3, 0.3]
        ]
        
        config["room_acoustics"]["dimensions"] = [20.0, 15.0, 4.0]
        config["room_acoustics"]["reverberation_time"] = 1.2
        
        config["services"]["beamformer"]["algorithm"] = "MVDR"  # 更高级的算法
        config["services"]["aec"]["filter_length"] = 512  # 更长的滤波器
        
        return config
    
    def _get_classroom_small_config(self) -> Dict[str, Any]:
        """小型教室配置（60-80㎡，30-40座位）"""
        config = self._get_classroom_standard_config()
        
        config["system"]["name"] = "classroom_small"
        config["system"]["description"] = "小型多媒体教室音频处理系统"
        
        config["audio"]["channels"] = 4  # 较少麦克风
        config["microphone_array"]["count"] = 4
        config["microphone_array"]["positions"] = [
            [0.0, 0.0], [0.1, 0.0], [0.2, 0.0], [0.3, 0.0]
        ]
        
        config["room_acoustics"]["dimensions"] = [8.0, 7.0, 3.0]
        config["room_acoustics"]["reverberation_time"] = 0.6
        
        config["services"]["aec"]["filter_length"] = 128  # 较短的滤波器
        
        return config
    
    def _get_laboratory_config(self) -> Dict[str, Any]:
        """实验室配置"""
        config = self._get_classroom_standard_config()
        
        config["system"]["name"] = "laboratory"
        config["system"]["description"] = "实验室音频处理系统"
        
        # 实验室通常噪声较大，需要更强的降噪
        config["services"]["denoise"]["strength"] = "aggressive"
        config["services"]["agc"]["noise_gate_threshold_dbfs"] = -40.0
        
        # 更高的采样率用于精确测量
        config["audio"]["sample_rate"] = 96000
        config["audio"]["frame_size"] = 960
        
        return config
    
    def _get_conference_room_config(self) -> Dict[str, Any]:
        """会议室配置"""
        config = self._get_classroom_standard_config()
        
        config["system"]["name"] = "conference_room"
        config["system"]["description"] = "会议室音频处理系统"
        
        # 会议室需要更好的语音质量
        config["services"]["denoise"]["preserve_speech"] = True
        config["services"]["agc"]["target_level_dbfs"] = -15.0
        
        # 启用流媒体用于远程会议
        config["output"]["streaming"]["enabled"] = True
        config["output"]["streaming"]["protocol"] = "WebRTC"
        
        return config
    
    def _get_auditorium_config(self) -> Dict[str, Any]:
        """礼堂配置"""
        config = self._get_classroom_large_config()
        
        config["system"]["name"] = "auditorium"
        config["system"]["description"] = "礼堂音频处理系统"
        
        # 礼堂需要处理更长的混响
        config["room_acoustics"]["dimensions"] = [40.0, 30.0, 8.0]
        config["room_acoustics"]["reverberation_time"] = 2.0
        
        config["services"]["aec"]["filter_length"] = 1024
        config["services"]["beamformer"]["target_gain_db"] = 15.0
        
        return config
    
    def _get_development_config(self) -> Dict[str, Any]:
        """开发环境配置"""
        config = self._get_classroom_standard_config()
        
        config["system"]["name"] = "development"
        config["system"]["description"] = "开发测试环境"
        config["system"]["environment"] = "development"
        config["system"]["debug"] = True
        config["system"]["log_level"] = "DEBUG"
        
        # 开发环境使用较小的缓冲区以便调试
        config["audio"]["buffer_size"] = 1024
        config["audio"]["frame_size"] = 240  # 5ms
        
        # 启用所有监控功能
        config["monitoring"]["performance_logging"] = True
        config["monitoring"]["audio_quality_monitoring"] = True
        
        return config
    
    def _get_production_config(self) -> Dict[str, Any]:
        """生产环境配置"""
        config = self._get_classroom_standard_config()
        
        config["system"]["name"] = "production"
        config["system"]["description"] = "生产环境配置"
        config["system"]["environment"] = "production"
        config["system"]["debug"] = False
        config["system"]["log_level"] = "WARNING"
        
        # 生产环境优化性能
        config["audio"]["buffer_size"] = 4096
        config["monitoring"]["health_check_interval"] = 60
        
        # 启用认证
        config["web_interface"]["auth_required"] = True
        
        return config
    
    def generate_config(self, template_name: str, 
                       custom_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """生成配置文件"""
        if template_name not in self.templates:
            raise ValueError(f"未知的模板: {template_name}")
        
        config = self.templates[template_name].copy()
        
        # 应用自定义参数
        if custom_params:
            config = self._merge_config(config, custom_params)
        
        return config
    
    def _merge_config(self, base_config: Dict[str, Any], 
                     custom_config: Dict[str, Any]) -> Dict[str, Any]:
        """合并配置"""
        result = base_config.copy()
        
        for key, value in custom_config.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def save_config(self, config: Dict[str, Any], filename: str) -> str:
        """保存配置文件"""
        config_path = self.output_dir / filename
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        logger.info(f"配置文件已保存: {config_path}")
        return str(config_path)
    
    def generate_all_templates(self) -> List[str]:
        """生成所有模板配置文件"""
        generated_files = []
        
        for template_name in self.templates.keys():
            config = self.generate_config(template_name)
            filename = f"{template_name}.json"
            config_path = self.save_config(config, filename)
            generated_files.append(config_path)
        
        return generated_files
    
    def create_installer_config(self, template_name: str, 
                              install_params: Dict[str, Any]) -> str:
        """创建安装器专用配置"""
        config = self.generate_config(template_name)
        
        # 添加安装器特定的参数
        installer_config = {
            "installer": {
                "version": "1.0.0",
                "install_date": "",  # 安装时填写
                "install_path": install_params.get("install_path", "/opt/audio-processing-system"),
                "user": install_params.get("user", "audiouser"),
                "auto_start": install_params.get("auto_start", True),
                "web_interface_enabled": install_params.get("web_interface", True)
            },
            "hardware": {
                "detected_architecture": "",  # 安装时检测
                "detected_os": "",  # 安装时检测
                "memory_gb": 0,  # 安装时检测
                "cpu_cores": 0,  # 安装时检测
                "audio_devices": []  # 安装时检测
            }
        }
        
        # 合并配置
        final_config = self._merge_config(config, installer_config)
        
        # 保存安装器配置
        filename = f"installer_{template_name}.json"
        return self.save_config(final_config, filename)
    
    def create_deployment_script(self, configs: List[str]) -> str:
        """创建部署脚本"""
        script_content = '''#!/bin/bash
# 配置部署脚本
# Configuration Deployment Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR"
INSTALL_DIR="/opt/audio-processing-system"

# 颜色定义
GREEN='\\033[0;32m'
BLUE='\\033[0;34m'
NC='\\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# 显示可用配置
show_configs() {
    echo "可用的配置模板:"
    echo
'''
        
        for i, config_file in enumerate(configs, 1):
            config_name = Path(config_file).stem
            script_content += f'    echo "{i}) {config_name}"\n'
        
        script_content += '''
    echo
}

# 部署配置
deploy_config() {
    local config_file="$1"
    local config_name=$(basename "$config_file" .json)
    
    log_info "部署配置: $config_name"
    
    # 复制配置文件
    cp "$CONFIG_DIR/$config_file" "$INSTALL_DIR/config/audio_system.json"
    
    # 重启服务以应用新配置
    if systemctl is-active --quiet audio-processing; then
        log_info "重启音频处理服务..."
        systemctl restart audio-processing
        sleep 3
        
        if systemctl is-active --quiet audio-processing; then
            log_success "服务重启成功，新配置已生效"
        else
            echo "服务重启失败，请检查配置文件"
            return 1
        fi
    else
        log_info "服务未运行，配置将在下次启动时生效"
    fi
    
    log_success "配置部署完成: $config_name"
}

# 主函数
main() {
    echo "=========================================="
    echo "    音频处理系统配置部署工具"
    echo "=========================================="
    echo
    
    if [[ $# -eq 1 ]]; then
        # 直接指定配置文件
        local config_file="$1"
        if [[ -f "$CONFIG_DIR/$config_file" ]]; then
            deploy_config "$config_file"
        else
            echo "配置文件不存在: $config_file"
            exit 1
        fi
    else
        # 交互式选择
        show_configs
        read -p "请选择配置 (1-''' + str(len(configs)) + '''): " choice
        
        case $choice in
'''
        
        for i, config_file in enumerate(configs, 1):
            config_filename = Path(config_file).name
            script_content += f'            {i})\n                deploy_config "{config_filename}"\n                ;;\n'
        
        script_content += '''            *)
                echo "无效选择"
                exit 1
                ;;
        esac
    fi
}

main "$@"
'''
        
        script_path = self.output_dir / "deploy_config.sh"
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        script_path.chmod(0o755)
        
        logger.info(f"部署脚本已创建: {script_path}")
        return str(script_path)

def main():
    parser = argparse.ArgumentParser(description="配置文件生成器")
    parser.add_argument("--template", "-t", 
                       choices=["classroom_standard", "classroom_large", "classroom_small",
                               "laboratory", "conference_room", "auditorium", 
                               "development", "production"],
                       help="配置模板名称")
    parser.add_argument("--output", "-o", default="config/templates",
                       help="输出目录")
    parser.add_argument("--all", "-a", action="store_true",
                       help="生成所有模板")
    parser.add_argument("--deployment-script", "-d", action="store_true",
                       help="创建部署脚本")
    parser.add_argument("--custom", "-c", help="自定义参数JSON文件")
    
    args = parser.parse_args()
    
    generator = ConfigGenerator(args.output)
    
    try:
        if args.all:
            # 生成所有模板
            config_files = generator.generate_all_templates()
            print(f"\n✓ 已生成 {len(config_files)} 个配置模板:")
            for config_file in config_files:
                print(f"  - {Path(config_file).name}")
            
            # 创建部署脚本
            if args.deployment_script:
                script_path = generator.create_deployment_script(
                    [Path(f).name for f in config_files]
                )
                print(f"\n✓ 部署脚本已创建: {Path(script_path).name}")
        
        elif args.template:
            # 生成指定模板
            custom_params = {}
            if args.custom and Path(args.custom).exists():
                with open(args.custom) as f:
                    custom_params = json.load(f)
            
            config = generator.generate_config(args.template, custom_params)
            config_path = generator.save_config(config, f"{args.template}.json")
            
            print(f"\n✓ 配置文件已生成: {Path(config_path).name}")
        
        else:
            print("请指定 --template 或使用 --all 生成所有模板")
            parser.print_help()
    
    except Exception as e:
        logger.error(f"生成失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()