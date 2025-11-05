#!/usr/bin/env python3
"""
启动脚本1: 仅启动系统内核 (不包含Web界面)
Production Audio Processing System - Core Only
"""

import sys
import asyncio
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def start_core_system():
    """启动核心音频处理系统"""
    print("🎵 启动生产级音频处理系统 (仅内核)")
    print("=" * 50)
    
    try:
        # Import required modules
        from src.config.logging_config import log_system
        from src.config.embedded_config import embedded_config
        from src.config.platform_config import platform_config
        from src.audio_core.integrated_audio_system import IntegratedProductionAudioSystem
        
        print("📋 初始化系统配置...")
        log_system("Initializing core system configurations")
        embedded_config.apply_runtime_optimizations()
        platform_config.apply_platform_optimizations()
        print("✅ 系统配置初始化完成")
        
        print("🔧 创建音频处理系统...")
        audio_system = IntegratedProductionAudioSystem("core_system")
        
        # System configuration (without web interface)
        system_config = {
            "sample_rate": 48000,
            "channels": 2,
            "bit_depth": 24,
            "buffer_size": 256,
            "auto_detect_devices": True,
            "enable_all_devices": True,
            "enable_quality_monitoring": True,
            "enable_hot_plug": True,
            # Web interface disabled
            "web_enabled": False,
            "capture_service": {
                "device_manager": {
                    "scan_interval": 5.0,
                    "enable_hot_plug": True
                }
            },
            "recovery": {
                "enable_auto_recovery": True,
                "max_retry_attempts": 3,
                "retry_delay_seconds": 2.0
            },
            "dashboard": {
                "max_history_points": 10000,
                "input_monitor": {
                    "waveform_buffer_size": 2048,
                    "spectrum_buffer_size": 1024
                }
            }
        }
        
        print("⚙️  初始化音频处理系统...")
        if not await audio_system.initialize_system(system_config):
            raise Exception("音频系统初始化失败")
        print("✅ 音频系统初始化成功")
        
        print("🚀 启动音频处理系统...")
        if not await audio_system.start_system():
            raise Exception("音频系统启动失败")
        print("✅ 音频系统启动成功")
        
        print("")
        print("📊 系统状态:")
        print("  • 音频处理内核: 运行中")
        print("  • 设备管理器: 活跃")
        print("  • 组件注册表: 已加载")
        print("  • 恢复管理器: 监控中")
        print("  • Web界面: 未启用")
        print("")
        print("💡 提示: 如需Web界面，请使用 'python start_with_web.py'")
        print("⏹️  按 Ctrl+C 停止系统")
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n⏹️  正在停止系统...")
            await audio_system.stop_system()
            print("✅ 系统已停止")
        
    except Exception as e:
        print(f"❌ 系统启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def main():
    """Main entry point"""
    try:
        asyncio.run(start_core_system())
    except KeyboardInterrupt:
        print("\n⏹️  用户中断")
    except Exception as e:
        print(f"❌ 主程序错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()