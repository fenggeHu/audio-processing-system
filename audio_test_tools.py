#!/usr/bin/env python3
"""
Audio Testing and Debugging Tools

This script provides various tools for testing and debugging audio processing:
1. Audio device detection and testing
2. Real-time audio visualization
3. Audio processing parameter tuning
4. Performance monitoring
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
import numpy as np

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from audio_processing.models import AudioConfig, AudioFrame
from audio_processing.services.capture import CaptureService, DeviceManager
from audio_processing.services.ssl import SSLService
from audio_processing.services.beamformer import BeamformerService


class AudioTestTools:
    """Audio testing and debugging tools."""
    
    def __init__(self):
        self.config = AudioConfig(
            sample_rate=48000,
            frame_size=480,
            channels=8,
            enable_ssl=True,
            enable_beamforming=True
        )
        self.capture_service = None
        self.ssl_service = None
        self.beamformer_service = None
    
    async def test_audio_devices(self):
        """Test available audio devices."""
        print("🎤 Testing Audio Devices")
        print("=" * 50)
        
        device_manager = DeviceManager()
        devices = await device_manager.scan_devices()
        
        if not devices:
            print("❌ No audio devices found!")
            return
        
        print(f"Found {len(devices)} audio devices:")
        print()
        
        for device in devices:
            print(f"Device {device.device_id}: {device.name}")
            print(f"  Channels: {device.channels}")
            print(f"  Sample Rate: {device.sample_rate} Hz")
            print(f"  Default: {'Yes' if device.is_default else 'No'}")
            print(f"  Latency: {device.latency_ms:.1f} ms")
            
            # Test device
            print("  Testing device...", end=" ")
            is_working = await device_manager.test_device(device.device_id)
            print("✅ Working" if is_working else "❌ Failed")
            print()
    
    async def test_audio_capture(self, duration_seconds: int = 10):
        """Test real-time audio capture."""
        print(f"🎵 Testing Audio Capture ({duration_seconds}s)")
        print("=" * 50)
        
        # Create capture service
        self.capture_service = CaptureService("TestCapture", self.config)
        
        try:
            # Start capture
            await self.capture_service.start()
            print("✅ Audio capture started")
            
            # Monitor capture for specified duration
            start_time = time.time()
            frame_count = 0
            
            print("Monitoring audio capture...")
            print("Frame | Timestamp | Channels | Samples | RMS Level")
            print("-" * 55)
            
            async for frame in self.capture_service.get_frame_stream():
                frame_count += 1
                
                # Calculate RMS level for each channel
                rms_levels = []
                for ch in range(frame.channels):
                    rms = np.sqrt(np.mean(frame.data[ch] ** 2))
                    rms_levels.append(rms)
                
                avg_rms = np.mean(rms_levels)
                
                print(f"{frame_count:5d} | {frame.timestamp.strftime('%H:%M:%S.%f')[:-3]} | "
                      f"{frame.channels:8d} | {frame.frame_size:7d} | {avg_rms:.4f}")
                
                # Check if duration exceeded
                if time.time() - start_time >= duration_seconds:
                    break
            
            print(f"\n✅ Captured {frame_count} frames in {duration_seconds}s")
            
            # Get capture metrics
            metrics = self.capture_service.get_capture_metrics()
            print("\nCapture Metrics:")
            for key, value in metrics.items():
                print(f"  {key}: {value}")
            
        except Exception as e:
            print(f"❌ Capture test failed: {e}")
        finally:
            if self.capture_service:
                await self.capture_service.stop()
    
    async def test_sound_source_localization(self, duration_seconds: int = 30):
        """Test sound source localization."""
        print(f"🎯 Testing Sound Source Localization ({duration_seconds}s)")
        print("=" * 50)
        
        # Create services
        self.capture_service = CaptureService("TestCapture", self.config)
        self.ssl_service = SSLService("TestSSL", self.config)
        
        try:
            # Start services
            await self.capture_service.start()
            await self.ssl_service.start()
            print("✅ Services started")
            
            # Enable mock audio with different frequencies per channel
            self.capture_service.set_mock_audio_enabled(True)
            print("🔊 Mock audio enabled (test tones)")
            
            start_time = time.time()
            frame_count = 0
            
            print("\nSound Source Localization Results:")
            print("Frame | Timestamp | Azimuth | Elevation | Confidence")
            print("-" * 60)
            
            async for frame in self.capture_service.get_frame_stream():
                frame_count += 1
                
                # Process frame through SSL
                ssl_result = await self.ssl_service.process_frame(frame)
                
                # Get SSL metadata
                ssl_data = ssl_result.metadata.get('ssl', {})
                azimuth = ssl_data.get('azimuth_deg', 0.0)
                elevation = ssl_data.get('elevation_deg', 0.0)
                confidence = ssl_data.get('confidence', 0.0)
                
                print(f"{frame_count:5d} | {frame.timestamp.strftime('%H:%M:%S.%f')[:-3]} | "
                      f"{azimuth:7.1f}° | {elevation:9.1f}° | {confidence:.3f}")
                
                # Check if duration exceeded
                if time.time() - start_time >= duration_seconds:
                    break
            
            print(f"\n✅ Processed {frame_count} frames for SSL")
            
        except Exception as e:
            print(f"❌ SSL test failed: {e}")
        finally:
            if self.ssl_service:
                await self.ssl_service.stop()
            if self.capture_service:
                await self.capture_service.stop()
    
    async def test_beamforming(self, duration_seconds: int = 20):
        """Test beamforming with different steering angles."""
        print(f"📡 Testing Beamforming ({duration_seconds}s)")
        print("=" * 50)
        
        # Create services
        self.capture_service = CaptureService("TestCapture", self.config)
        # Create mock microphone positions for testing
        from audio_processing.services.ssl import MicrophonePosition
        mock_mic_positions = [
            MicrophonePosition(x=-0.1, y=0.0, z=0.0, channel=0),
            MicrophonePosition(x=-0.05, y=0.0, z=0.0, channel=1),
            MicrophonePosition(x=0.0, y=0.0, z=0.0, channel=2),
            MicrophonePosition(x=0.05, y=0.0, z=0.0, channel=3),
            MicrophonePosition(x=0.1, y=0.0, z=0.0, channel=4),
            MicrophonePosition(x=0.15, y=0.0, z=0.0, channel=5),
            MicrophonePosition(x=0.2, y=0.0, z=0.0, channel=6),
            MicrophonePosition(x=0.25, y=0.0, z=0.0, channel=7),
        ]
        self.beamformer_service = BeamformerService("TestBeamformer", self.config, mock_mic_positions)
        
        try:
            # Start services
            await self.capture_service.start()
            await self.beamformer_service.start()
            print("✅ Services started")
            
            # Enable mock audio
            self.capture_service.set_mock_audio_enabled(True)
            print("🔊 Mock audio enabled")
            
            # Test different steering angles
            test_angles = [0, 30, 60, 90, 120, 150, 180]
            frames_per_angle = max(1, duration_seconds // len(test_angles))
            
            print(f"\nTesting {len(test_angles)} steering angles ({frames_per_angle}s each):")
            print("Angle | Frame | Output RMS | Gain (dB)")
            print("-" * 40)
            
            for angle in test_angles:
                # Set beamformer steering angle
                await self.beamformer_service.set_steering_angle(angle, 0)
                
                frame_count = 0
                angle_start = time.time()
                
                async for frame in self.capture_service.get_frame_stream():
                    frame_count += 1
                    
                    # Process frame through beamformer
                    bf_result = await self.beamformer_service.process_frame(frame)
                    
                    # Calculate output RMS
                    output_rms = np.sqrt(np.mean(bf_result.data ** 2))
                    gain_db = 20 * np.log10(max(output_rms, 1e-10))
                    
                    print(f"{angle:5d}° | {frame_count:5d} | {output_rms:.4f} | {gain_db:8.1f}")
                    
                    # Check if time for this angle exceeded
                    if time.time() - angle_start >= frames_per_angle:
                        break
            
            print(f"\n✅ Beamforming test completed")
            
        except Exception as e:
            print(f"❌ Beamforming test failed: {e}")
        finally:
            if self.beamformer_service:
                await self.beamformer_service.stop()
            if self.capture_service:
                await self.capture_service.stop()
    
    async def interactive_audio_tuning(self):
        """Interactive audio parameter tuning."""
        print("🎛️  Interactive Audio Parameter Tuning")
        print("=" * 50)
        print("Commands:")
        print("  devices - List audio devices")
        print("  capture <seconds> - Test capture for N seconds")
        print("  ssl <seconds> - Test SSL for N seconds")
        print("  beamform <seconds> - Test beamforming for N seconds")
        print("  mock on/off - Enable/disable mock audio")
        print("  freq <hz> - Set mock audio frequency")
        print("  config - Show current configuration")
        print("  quit - Exit")
        print()
        
        while True:
            try:
                command = input("audio_test> ").strip().lower()
                
                if command == "quit":
                    break
                elif command == "devices":
                    await self.test_audio_devices()
                elif command.startswith("capture"):
                    parts = command.split()
                    duration = int(parts[1]) if len(parts) > 1 else 5
                    await self.test_audio_capture(duration)
                elif command.startswith("ssl"):
                    parts = command.split()
                    duration = int(parts[1]) if len(parts) > 1 else 10
                    await self.test_sound_source_localization(duration)
                elif command.startswith("beamform"):
                    parts = command.split()
                    duration = int(parts[1]) if len(parts) > 1 else 10
                    await self.test_beamforming(duration)
                elif command == "mock on":
                    if self.capture_service:
                        self.capture_service.set_mock_audio_enabled(True)
                        print("✅ Mock audio enabled")
                    else:
                        print("❌ No capture service running")
                elif command == "mock off":
                    if self.capture_service:
                        self.capture_service.set_mock_audio_enabled(False)
                        print("✅ Mock audio disabled")
                    else:
                        print("❌ No capture service running")
                elif command.startswith("freq"):
                    parts = command.split()
                    if len(parts) > 1:
                        freq = float(parts[1])
                        if self.capture_service:
                            self.capture_service.set_mock_frequency(freq)
                            print(f"✅ Mock frequency set to {freq} Hz")
                        else:
                            print("❌ No capture service running")
                    else:
                        print("❌ Please specify frequency: freq <hz>")
                elif command == "config":
                    print("Current Configuration:")
                    print(f"  Sample Rate: {self.config.sample_rate} Hz")
                    print(f"  Channels: {self.config.channels}")
                    print(f"  Frame Size: {self.config.frame_size} samples")
                    print(f"  Frame Duration: {self.config.get_frame_duration_ms():.1f} ms")
                    print(f"  SSL Enabled: {self.config.enable_ssl}")
                    print(f"  Beamforming Enabled: {self.config.enable_beamforming}")
                else:
                    print("❌ Unknown command. Type 'quit' to exit.")
                
                print()
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")


async def main():
    """Main entry point."""
    print("🎵 Audio Testing and Debugging Tools 🎵")
    print("=" * 60)
    
    tools = AudioTestTools()
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "devices":
            await tools.test_audio_devices()
        elif command == "capture":
            duration = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            await tools.test_audio_capture(duration)
        elif command == "ssl":
            duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            await tools.test_sound_source_localization(duration)
        elif command == "beamform":
            duration = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            await tools.test_beamforming(duration)
        elif command == "interactive":
            await tools.interactive_audio_tuning()
        else:
            print(f"❌ Unknown command: {command}")
            print("Available commands: devices, capture, ssl, beamform, interactive")
    else:
        # Default to interactive mode
        await tools.interactive_audio_tuning()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✅ Testing stopped by user")
    except Exception as e:
        print(f"❌ Testing failed: {e}")
        sys.exit(1)