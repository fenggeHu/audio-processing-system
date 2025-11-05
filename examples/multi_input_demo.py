#!/usr/bin/env python3
"""
Multi-Input Audio Access Layer Demo

This script demonstrates the usage of the multi-input audio access layer
for dynamic device detection, selective access, and synchronized capture.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audio_core.multi_input_system import create_multi_input_system
from audio_core.models import AudioProcessingConfig, AudioFrame
from audio_core.multi_input_access import InputDeviceStatus


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MultiInputDemo:
    """Demo class for multi-input audio system"""
    
    def __init__(self):
        self.system = None
        self.frame_count = 0
        self.sync_frame_count = 0
    
    async def run_demo(self):
        """Run the complete demo"""
        logger.info("Starting Multi-Input Audio Access Layer Demo")
        
        try:
            # Create system with demo configuration
            self.system = create_multi_input_system(
                auto_detect=True,
                enable_all_by_default=True,
                enable_quality_monitoring=True,
                enable_hot_plug=True,
                sync_mode="software_sync",
                device_scan_interval_ms=2000,  # Slower for demo
                quality_check_interval_ms=500
            )
            
            # Register callbacks
            self._register_callbacks()
            
            # Initialize system
            logger.info("Initializing multi-input audio system...")
            if not await self.system.initialize():
                logger.error("Failed to initialize system")
                return
            
            logger.info("System initialized successfully")
            
            # Demonstrate device detection
            await self._demo_device_detection()
            
            # Demonstrate device management
            await self._demo_device_management()
            
            # Demonstrate capture (if devices available)
            await self._demo_audio_capture()
            
            # Demonstrate visualization data
            await self._demo_visualization()
            
            # Run for a short time to show real-time updates
            logger.info("Running system for 10 seconds to show real-time updates...")
            await asyncio.sleep(10.0)
            
        except Exception as e:
            logger.error(f"Demo error: {e}")
        
        finally:
            # Cleanup
            if self.system:
                await self.system.shutdown()
            logger.info("Demo completed")
    
    def _register_callbacks(self):
        """Register system callbacks"""
        
        def on_audio_frame(device_id: str, frame: AudioFrame):
            self.frame_count += 1
            if self.frame_count % 100 == 0:  # Log every 100th frame
                logger.info(f"Received frame {self.frame_count} from {device_id}: "
                           f"{frame.frame_size} samples, {frame.channels} channels")
        
        def on_synchronized_frames(frames: dict):
            self.sync_frame_count += 1
            if self.sync_frame_count % 50 == 0:  # Log every 50th sync
                logger.info(f"Synchronized frames {self.sync_frame_count} from "
                           f"{len(frames)} devices")
        
        def on_device_status_change(device_id: str, status: InputDeviceStatus):
            logger.info(f"Device {device_id} status changed: {status.state.value} "
                       f"(enabled: {status.is_enabled}, gain: {status.gain_db}dB)")
        
        def on_hotplug_event(device_id: str, device, added: bool):
            action = "added" if added else "removed"
            device_name = device.name if device else "Unknown"
            logger.info(f"Hot-plug event: Device {device_name} ({device_id}) {action}")
        
        # Register callbacks
        self.system.register_input_callback(on_audio_frame)
        self.system.register_sync_callback(on_synchronized_frames)
        self.system.register_status_callback(on_device_status_change)
        self.system.register_hotplug_callback(on_hotplug_event)
    
    async def _demo_device_detection(self):
        """Demonstrate device detection capabilities"""
        logger.info("\n=== Device Detection Demo ===")
        
        # Scan for devices
        devices = self.system.scan_input_devices()
        logger.info(f"Detected {len(devices)} input devices:")
        
        for i, device in enumerate(devices, 1):
            logger.info(f"  {i}. {device['name']} ({device['device_id']})")
            logger.info(f"     Type: {device['device_type']}")
            logger.info(f"     Channels: {device['max_input_channels']}")
            logger.info(f"     Sample rates: {device['supported_sample_rates']}")
            
            # Get device capabilities
            capabilities = self.system.get_device_capabilities(device['device_id'])
            if capabilities:
                logger.info(f"     Capabilities: {capabilities}")
        
        if not devices:
            logger.warning("No input devices detected. This may be due to:")
            logger.warning("  - No microphones connected")
            logger.warning("  - PyAudio not properly installed")
            logger.warning("  - Audio permissions not granted")
    
    async def _demo_device_management(self):
        """Demonstrate device management features"""
        logger.info("\n=== Device Management Demo ===")
        
        selected_devices = self.system.get_selected_devices()
        logger.info(f"Currently selected devices: {len(selected_devices)}")
        
        if selected_devices:
            # Demonstrate device control
            device = selected_devices[0]
            device_id = device.device_id
            
            logger.info(f"Demonstrating controls on device: {device.name}")
            
            # Set priority
            self.system.set_device_priority(device_id, 10)
            logger.info(f"Set priority to 10 for {device_id}")
            
            # Set gain
            self.system.set_input_gain(device_id, 6.0)
            logger.info(f"Set gain to 6.0dB for {device_id}")
            
            # Mute and unmute
            self.system.mute_input(device_id, True)
            logger.info(f"Muted {device_id}")
            await asyncio.sleep(1.0)
            
            self.system.mute_input(device_id, False)
            logger.info(f"Unmuted {device_id}")
            
            # Disable and re-enable
            self.system.disable_device(device_id)
            logger.info(f"Disabled {device_id}")
            await asyncio.sleep(1.0)
            
            self.system.enable_device(device_id)
            logger.info(f"Re-enabled {device_id}")
    
    async def _demo_audio_capture(self):
        """Demonstrate audio capture functionality"""
        logger.info("\n=== Audio Capture Demo ===")
        
        selected_devices = self.system.get_selected_devices()
        if not selected_devices:
            logger.warning("No devices selected for capture demo")
            return
        
        # Create audio configuration
        audio_config = AudioProcessingConfig(
            config_id="demo_config",
            name="Demo Configuration",
            sample_rate=48000,
            channels=2,
            bit_depth=16,
            buffer_size=256
        )
        
        logger.info(f"Starting capture for {len(selected_devices)} devices...")
        logger.info(f"Audio config: {audio_config.sample_rate}Hz, "
                   f"{audio_config.channels}ch, {audio_config.bit_depth}bit")
        
        # Start capture
        if self.system.start_capture(audio_config):
            logger.info("Capture started successfully")
            
            # Run capture for a few seconds
            logger.info("Capturing audio for 5 seconds...")
            await asyncio.sleep(5.0)
            
            # Get capture status
            status = self.system.get_input_status()
            logger.info("Capture status:")
            for device_id, device_status in status.items():
                ds = device_status.get('device_status', {})
                cs = device_status.get('capture_status', {})
                logger.info(f"  {device_id}: "
                           f"frames={ds.get('frames_captured', 0)}, "
                           f"dropped={ds.get('frames_dropped', 0)}, "
                           f"active={cs.get('is_active', False)}")
            
            # Stop capture
            self.system.stop_capture()
            logger.info("Capture stopped")
        else:
            logger.error("Failed to start capture")
    
    async def _demo_visualization(self):
        """Demonstrate visualization data"""
        logger.info("\n=== Visualization Demo ===")
        
        # Get UI data
        ui_data = self.system.get_ui_data()
        logger.info("System UI Data:")
        logger.info(f"  Total devices: {ui_data['system_status']['total_devices']}")
        logger.info(f"  Active devices: {ui_data['system_status']['active_devices']}")
        logger.info(f"  Error devices: {ui_data['system_status']['error_devices']}")
        
        # Show device details
        for device_data in ui_data['devices']:
            logger.info(f"  Device {device_data['device_id']}:")
            logger.info(f"    State: {device_data['state']}")
            logger.info(f"    Enabled: {device_data['is_enabled']}")
            logger.info(f"    Signal strength: {device_data['signal_strength']:.2f}")
            logger.info(f"    Noise level: {device_data['noise_level_db']:.1f}dB")
            logger.info(f"    Connection quality: {device_data['connection_quality']:.2f}")
        
        # Get synchronization status
        sync_status = self.system.get_synchronization_status()
        logger.info("Synchronization Status:")
        logger.info(f"  Reference device: {sync_status.get('reference_device')}")
        logger.info(f"  Sync mode: {sync_status.get('sync_mode')}")
        logger.info(f"  Device count: {sync_status.get('device_count')}")
        
        # Show system properties
        logger.info("System Properties:")
        logger.info(f"  Initialized: {self.system.is_initialized}")
        logger.info(f"  Running: {self.system.is_running}")
        logger.info(f"  Device count: {self.system.device_count}")
        logger.info(f"  Selected devices: {self.system.selected_device_count}")
        logger.info(f"  Hot-plug enabled: {self.system.hotplug_enabled}")


async def main():
    """Main demo function"""
    demo = MultiInputDemo()
    await demo.run_demo()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        sys.exit(1)