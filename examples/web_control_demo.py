#!/usr/bin/env python3
"""
Web Control Interface Demo

This example demonstrates how to set up and use the web control interface
for the audio processing system. It shows how to integrate the ControlService
with the existing service manager and provides a complete working example.
"""

import asyncio
import signal
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audio_processing.models import AudioConfig
from audio_processing.service_manager import ServiceManager
from audio_processing.services.control import ControlService
from audio_processing.services.telemetry import TelemetryService
from audio_processing.services.capture import CaptureService
from audio_processing.services.ssl import SSLService
from audio_processing.services.aec import AECService
from audio_processing.services.agc import AGCService
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class WebControlDemo:
    """
    Demonstration of the web control interface.
    
    Sets up a complete audio processing system with web control interface
    for monitoring and configuration management.
    """
    
    def __init__(self):
        self.config = AudioConfig(
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
        
        self.service_manager = None
        self.control_service = None
        self.shutdown_event = asyncio.Event()
    
    async def setup_services(self) -> None:
        """Set up all audio processing services."""
        logger.info("Setting up audio processing services")
        
        # Create service manager
        self.service_manager = ServiceManager(self.config)
        
        # Register core services (these would normally be the actual implementations)
        # For demo purposes, we'll register mock services that simulate the real ones
        
        # Register telemetry service first (other services may depend on it)
        self.service_manager.register_service(
            TelemetryService,
            name="TelemetryService"
        )
        
        # Register audio processing services
        self.service_manager.register_service(
            CaptureService,
            name="CaptureService",
            config={"device_id": 0, "channels": self.config.channels}
        )
        
        self.service_manager.register_service(
            SSLService,
            name="SSLService",
            config={"mic_positions": [(0, 0), (1, 0), (0, 1), (1, 1)]}
        )
        
        self.service_manager.register_service(
            AECService,
            name="AECService",
            config={"filter_length": 256}
        )
        
        self.service_manager.register_service(
            AGCService,
            name="AGCService",
            config={"target_level_dbfs": -18.0}
        )
        
        # Create and register control service
        self.control_service = ControlService(
            config=self.config,
            service_manager=self.service_manager,
            host="0.0.0.0",
            port=8080
        )
        
        # Register control service with service manager
        self.service_manager.register_service(
            ControlService,
            implementation=type(self.control_service),
            name="ControlService"
        )
        
        logger.info("Services registered successfully")
    
    async def start_system(self) -> None:
        """Start the complete audio processing system."""
        logger.info("Starting audio processing system")
        
        try:
            # Start service manager (this starts all registered services)
            await self.service_manager.start()
            
            # Start control service separately to get the web server running
            await self.control_service.start()
            
            logger.info(
                "System started successfully",
                web_interface=self.control_service.get_server_url()
            )
            
            print(f"\n{'='*60}")
            print("🎵 Audio Processing System Started Successfully! 🎵")
            print(f"{'='*60}")
            print(f"Web Interface: {self.control_service.get_server_url()}")
            print(f"Services Running: {len(self.service_manager.get_service_status())}")
            print(f"Configuration Version: {self.control_service._get_config_version()}")
            print(f"{'='*60}")
            print("\nOpen your web browser and navigate to the URL above")
            print("to access the control interface.")
            print("\nPress Ctrl+C to stop the system")
            print(f"{'='*60}\n")
            
        except Exception as e:
            logger.error("Failed to start system", error=str(e))
            raise
    
    async def stop_system(self) -> None:
        """Stop the audio processing system."""
        logger.info("Stopping audio processing system")
        
        try:
            if self.control_service:
                await self.control_service.stop()
            
            if self.service_manager:
                await self.service_manager.stop()
            
            logger.info("System stopped successfully")
            
        except Exception as e:
            logger.error("Error during system shutdown", error=str(e))
    
    async def run(self) -> None:
        """Run the complete demo."""
        try:
            # Setup signal handlers for graceful shutdown
            def signal_handler():
                logger.info("Shutdown signal received")
                self.shutdown_event.set()
            
            # Register signal handlers
            if sys.platform != "win32":
                loop = asyncio.get_running_loop()
                for sig in (signal.SIGTERM, signal.SIGINT):
                    loop.add_signal_handler(sig, signal_handler)
            
            # Setup and start services
            await self.setup_services()
            await self.start_system()
            
            # Start web server in background
            server_task = asyncio.create_task(self.control_service.start_server())
            
            # Wait for shutdown signal
            await self.shutdown_event.wait()
            
            # Cancel server task
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
            
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error("Demo failed", error=str(e))
            raise
        finally:
            await self.stop_system()


async def main():
    """Main entry point for the web control demo."""
    demo = WebControlDemo()
    await demo.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDemo stopped by user")
    except Exception as e:
        print(f"Demo failed: {e}")
        sys.exit(1)