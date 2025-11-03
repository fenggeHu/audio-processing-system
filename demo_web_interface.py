#!/usr/bin/env python3
"""
Simple demo of the Web Control Interface.

This script starts a minimal audio processing system with the web control
interface to demonstrate the functionality without requiring all services.
"""

import asyncio
import signal
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from audio_processing.models import AudioConfig, AudioMetrics
from audio_processing.services.control import ControlService


class MockServiceManager:
    """Mock service manager for demo purposes."""
    
    def __init__(self):
        self.is_running = True
        self._services = {
            "CaptureService": {"running": True, "healthy": True},
            "SSLService": {"running": True, "healthy": True},
            "AECService": {"running": False, "healthy": False},
            "AGCService": {"running": True, "healthy": True},
            "BeamformingService": {"running": True, "healthy": True}
        }
    
    def get_service_status(self):
        """Get mock service status."""
        return {
            name: {
                "running": status["running"],
                "healthy": status["healthy"],
                "metrics": {
                    "cpu_usage": 15.5 + hash(name) % 20,
                    "memory_mb": 50 + hash(name) % 100,
                    "latency_ms": 2.5 + (hash(name) % 10) / 10
                }
            }
            for name, status in self._services.items()
        }
    
    def get_system_metrics(self):
        """Get mock system metrics."""
        return {
            name: AudioMetrics(
                processing_latency_ms=2.5 + (hash(name) % 10) / 10,
                cpu_usage_percent=15.5 + hash(name) % 20,
                memory_usage_mb=50 + hash(name) % 100,
                frames_processed=1000 + hash(name) % 5000,
                frames_dropped=hash(name) % 10
            )
            for name in self._services.keys()
        }
    
    async def update_config(self, config):
        """Mock config update."""
        print(f"Mock: Updated config - Sample Rate: {config.sample_rate}Hz")
    
    async def restart_service(self, service_name):
        """Mock service restart."""
        print(f"Mock: Restarted service {service_name}")
        # Simulate restart by toggling status
        if service_name in self._services:
            self._services[service_name]["running"] = True
            self._services[service_name]["healthy"] = True
    
    async def get_service_by_name(self, name):
        """Mock get service by name."""
        mock_service = Mock()
        mock_service.start = AsyncMock()
        mock_service.stop = AsyncMock()
        return mock_service
    
    def subscribe_to_events(self, event_type, handler):
        """Mock event subscription."""
        pass


async def main():
    """Run the web interface demo."""
    print("🎵 Audio Processing System - Web Control Interface Demo 🎵")
    print("=" * 60)
    
    # Create audio configuration
    config = AudioConfig(
        sample_rate=48000,
        frame_size=480,  # 10ms at 48kHz
        channels=8,
        buffer_size=4096,
        enable_ssl=True,
        enable_beamforming=True,
        enable_aec=True,
        enable_denoise=True,
        enable_agc=True,
        max_latency_ms=40.0,
        cpu_limit_percent=80.0
    )
    
    # Create mock service manager
    service_manager = MockServiceManager()
    
    # Create control service
    control_service = ControlService(
        config=config,
        service_manager=service_manager,
        host="127.0.0.1",
        port=8080
    )
    
    # Setup graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler():
        print("\n🛑 Shutdown signal received...")
        shutdown_event.set()
    
    # Register signal handlers (Unix only)
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
    
    try:
        # Start the control service
        await control_service.start()
        
        print(f"🚀 Web interface started successfully!")
        print(f"📱 Open your browser and go to: http://127.0.0.1:8080")
        print(f"🔧 Configuration: {config.sample_rate}Hz, {config.channels} channels")
        print(f"📊 Mock services: {len(service_manager._services)} services")
        print("=" * 60)
        print("Features available in the web interface:")
        print("  • Real-time system status monitoring")
        print("  • Service management (start/stop/restart)")
        print("  • Configuration parameter adjustment")
        print("  • Performance metrics visualization")
        print("  • WebSocket real-time updates")
        print("=" * 60)
        print("Press Ctrl+C to stop the demo")
        print("=" * 60)
        
        # Start the web server
        server_task = asyncio.create_task(control_service.start_server())
        
        # Wait for shutdown signal
        try:
            await shutdown_event.wait()
        except KeyboardInterrupt:
            print("\n🛑 Keyboard interrupt received...")
        
        # Cancel server task
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Stop the control service
        await control_service.stop()
        print("✅ Demo stopped successfully")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✅ Demo stopped by user")
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        sys.exit(1)