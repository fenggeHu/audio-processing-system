"""
Cross-Platform Audio Interface Configuration

Platform-specific configurations for Linux ALSA, macOS CoreAudio, and Windows WASAPI.
"""

import platform
import sys
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from enum import Enum


class AudioBackend(Enum):
    """Supported audio backends by platform."""
    ALSA = "alsa"           # Linux
    PULSE = "pulse"         # Linux PulseAudio
    JACK = "jack"           # Linux/macOS JACK
    COREAUDIO = "coreaudio" # macOS
    WASAPI = "wasapi"       # Windows
    DIRECTSOUND = "directsound"  # Windows
    MME = "mme"             # Windows Multimedia Extensions


@dataclass
class PlatformAudioConfig:
    """Platform-specific audio configuration."""
    
    # Backend selection
    primary_backend: AudioBackend
    fallback_backends: List[AudioBackend]
    
    # Device configuration
    default_sample_rate: int = 48000
    supported_sample_rates: List[int] = None
    default_buffer_size: int = 256
    supported_buffer_sizes: List[int] = None
    
    # Channel configuration
    max_input_channels: int = 32
    max_output_channels: int = 8
    
    # Latency settings
    target_latency_ms: float = 10.0
    max_acceptable_latency_ms: float = 50.0
    
    # Platform-specific settings
    platform_settings: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.supported_sample_rates is None:
            self.supported_sample_rates = [44100, 48000, 96000, 192000]
        if self.supported_buffer_sizes is None:
            self.supported_buffer_sizes = [64, 128, 256, 512, 1024]
        if self.platform_settings is None:
            self.platform_settings = {}


class PlatformConfigManager:
    """Manager for platform-specific audio configurations."""
    
    def __init__(self):
        self.platform = self._detect_platform()
        self.config = self._create_platform_config()
    
    def _detect_platform(self) -> str:
        """Detect the current platform."""
        system = platform.system().lower()
        if system == "linux":
            return "linux"
        elif system == "darwin":
            return "macos"
        elif system == "windows":
            return "windows"
        else:
            return "unknown"
    
    def _create_platform_config(self) -> PlatformAudioConfig:
        """Create platform-specific configuration."""
        if self.platform == "linux":
            return self._create_linux_config()
        elif self.platform == "macos":
            return self._create_macos_config()
        elif self.platform == "windows":
            return self._create_windows_config()
        else:
            return self._create_default_config()
    
    def _create_linux_config(self) -> PlatformAudioConfig:
        """Create Linux ALSA configuration."""
        return PlatformAudioConfig(
            primary_backend=AudioBackend.ALSA,
            fallback_backends=[AudioBackend.PULSE, AudioBackend.JACK],
            default_sample_rate=48000,
            supported_sample_rates=[44100, 48000, 96000, 192000],
            default_buffer_size=256,
            supported_buffer_sizes=[64, 128, 256, 512, 1024, 2048],
            max_input_channels=32,
            max_output_channels=8,
            target_latency_ms=8.0,
            max_acceptable_latency_ms=40.0,
            platform_settings={
                # ALSA-specific settings
                "alsa_device": "default",
                "alsa_subdevice": 0,
                "alsa_periods": 2,
                "alsa_period_size": 256,
                "enable_mmap": True,
                "enable_realtime": True,
                "realtime_priority": 80,
                
                # PulseAudio settings
                "pulse_server": None,  # Use default
                "pulse_application_name": "ProductionAudioSystem",
                "pulse_stream_name": "AudioProcessing",
                
                # JACK settings
                "jack_client_name": "ProductionAudio",
                "jack_auto_connect": True,
                "jack_ports": ["system:capture_1", "system:capture_2"],
                
                # Linux-specific optimizations
                "use_monotonic_clock": True,
                "enable_thread_priority": True,
                "cpu_dma_latency": 0,  # Disable CPU power saving
            }
        )
    
    def _create_macos_config(self) -> PlatformAudioConfig:
        """Create macOS CoreAudio configuration."""
        return PlatformAudioConfig(
            primary_backend=AudioBackend.COREAUDIO,
            fallback_backends=[AudioBackend.JACK],
            default_sample_rate=48000,
            supported_sample_rates=[44100, 48000, 88200, 96000, 176400, 192000],
            default_buffer_size=256,
            supported_buffer_sizes=[64, 128, 256, 512, 1024],
            max_input_channels=32,
            max_output_channels=8,
            target_latency_ms=6.0,
            max_acceptable_latency_ms=30.0,
            platform_settings={
                # CoreAudio-specific settings
                "coreaudio_device_id": None,  # Use default
                "coreaudio_stream_format": "Float32",
                "enable_hog_mode": False,  # Exclusive device access
                "enable_hardware_io": True,
                "io_buffer_duration": 0.005,  # 5ms
                
                # Audio Unit settings
                "audio_unit_type": "kAudioUnitType_Output",
                "audio_unit_subtype": "kAudioUnitSubType_HALOutput",
                "audio_unit_manufacturer": "kAudioUnitManufacturer_Apple",
                
                # macOS-specific optimizations
                "enable_time_constraints": True,
                "thread_time_constraint_policy": {
                    "period": 2902,      # ~128 frames at 44.1kHz
                    "computation": 1451,  # 50% of period
                    "constraint": 2902,   # Same as period
                    "preemptible": False,
                },
                
                # Power management
                "prevent_system_sleep": True,
                "prevent_display_sleep": False,
            }
        )
    
    def _create_windows_config(self) -> PlatformAudioConfig:
        """Create Windows WASAPI configuration."""
        return PlatformAudioConfig(
            primary_backend=AudioBackend.WASAPI,
            fallback_backends=[AudioBackend.DIRECTSOUND, AudioBackend.MME],
            default_sample_rate=48000,
            supported_sample_rates=[44100, 48000, 96000, 192000],
            default_buffer_size=256,
            supported_buffer_sizes=[128, 256, 512, 1024],
            max_input_channels=32,
            max_output_channels=8,
            target_latency_ms=10.0,
            max_acceptable_latency_ms=50.0,
            platform_settings={
                # WASAPI-specific settings
                "wasapi_exclusive_mode": False,
                "wasapi_event_driven": True,
                "wasapi_device_id": None,  # Use default
                "wasapi_share_mode": "AUDCLNT_SHAREMODE_SHARED",
                "wasapi_stream_flags": [
                    "AUDCLNT_STREAMFLAGS_EVENTCALLBACK",
                    "AUDCLNT_STREAMFLAGS_NOPERSIST",
                ],
                
                # DirectSound settings
                "directsound_device_guid": None,  # Use default
                "directsound_buffer_size": 4096,
                "directsound_num_buffers": 4,
                
                # MME settings
                "mme_device_id": 0,  # WAVE_MAPPER
                "mme_buffer_count": 4,
                "mme_buffer_size": 1024,
                
                # Windows-specific optimizations
                "enable_mmcss": True,  # Multimedia Class Scheduler Service
                "mmcss_task_name": "Pro Audio",
                "thread_priority": "THREAD_PRIORITY_TIME_CRITICAL",
                "process_priority": "HIGH_PRIORITY_CLASS",
                
                # Power management
                "prevent_system_sleep": True,
                "execution_state": [
                    "ES_CONTINUOUS",
                    "ES_SYSTEM_REQUIRED",
                    "ES_AWAYMODE_REQUIRED",
                ],
            }
        )
    
    def _create_default_config(self) -> PlatformAudioConfig:
        """Create default configuration for unknown platforms."""
        return PlatformAudioConfig(
            primary_backend=AudioBackend.ALSA,  # Fallback to ALSA
            fallback_backends=[],
            platform_settings={}
        )
    
    def get_portaudio_params(self) -> Dict[str, Any]:
        """Get PortAudio parameters for the current platform."""
        base_params = {
            "rate": self.config.default_sample_rate,
            "frames_per_buffer": self.config.default_buffer_size,
            "channels": 2,  # Default stereo
        }
        
        # Add platform-specific parameters
        if self.platform == "linux":
            if self.config.primary_backend == AudioBackend.ALSA:
                base_params.update({
                    "input_device_info": {
                        "name": self.config.platform_settings.get("alsa_device", "default"),
                        "hostApi": 0,  # ALSA
                    },
                    "output_device_info": {
                        "name": self.config.platform_settings.get("alsa_device", "default"),
                        "hostApi": 0,  # ALSA
                    },
                })
        
        elif self.platform == "macos":
            base_params.update({
                "input_device_info": {
                    "hostApi": 5,  # CoreAudio
                },
                "output_device_info": {
                    "hostApi": 5,  # CoreAudio
                },
            })
        
        elif self.platform == "windows":
            if self.config.primary_backend == AudioBackend.WASAPI:
                base_params.update({
                    "input_device_info": {
                        "hostApi": 13,  # WASAPI
                    },
                    "output_device_info": {
                        "hostApi": 13,  # WASAPI
                    },
                })
        
        return base_params
    
    def apply_platform_optimizations(self) -> None:
        """Apply platform-specific optimizations."""
        try:
            if self.platform == "linux":
                self._apply_linux_optimizations()
            elif self.platform == "macos":
                self._apply_macos_optimizations()
            elif self.platform == "windows":
                self._apply_windows_optimizations()
        except Exception as e:
            print(f"Warning: Could not apply platform optimizations: {e}")
    
    def _apply_linux_optimizations(self) -> None:
        """Apply Linux-specific optimizations."""
        import os
        
        # Set CPU DMA latency
        try:
            with open("/dev/cpu_dma_latency", "wb") as f:
                f.write(b"\x00\x00\x00\x00")  # 0 microseconds
        except (OSError, PermissionError):
            pass
        
        # Set thread priority
        if self.config.platform_settings.get("enable_thread_priority"):
            try:
                import os
                os.nice(-10)  # Higher priority
            except (OSError, PermissionError):
                pass
    
    def _apply_macos_optimizations(self) -> None:
        """Apply macOS-specific optimizations."""
        # Prevent system sleep
        if self.config.platform_settings.get("prevent_system_sleep"):
            try:
                import subprocess
                subprocess.run(["caffeinate", "-i"], check=False)
            except (OSError, subprocess.SubprocessError):
                pass
    
    def _apply_windows_optimizations(self) -> None:
        """Apply Windows-specific optimizations."""
        # Enable MMCSS
        if self.config.platform_settings.get("enable_mmcss"):
            try:
                import ctypes
                from ctypes import wintypes
                
                avrt = ctypes.windll.avrt
                task_name = self.config.platform_settings.get("mmcss_task_name", "Pro Audio")
                task_index = wintypes.DWORD(0)
                
                handle = avrt.AvSetMmThreadCharacteristicsW(task_name, ctypes.byref(task_index))
                if handle:
                    avrt.AvSetMmThreadPriority(handle, 1)  # AVRT_PRIORITY_HIGH
            except (OSError, AttributeError):
                pass


# Global platform configuration instance
platform_config = PlatformConfigManager()