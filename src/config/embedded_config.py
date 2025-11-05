"""
Embedded System Configuration

Optimized configurations for embedded systems including low memory mode,
CPU optimization, and real-time scheduling.
"""

import os
import platform
from dataclasses import dataclass
from typing import Dict, Any, Optional
from enum import Enum


class CPUArchitecture(Enum):
    """Supported CPU architectures for embedded systems."""
    ARM64 = "aarch64"
    ARM32 = "armv7l"
    X86_64 = "x86_64"
    X86 = "i386"


class MemoryMode(Enum):
    """Memory usage modes for different system constraints."""
    LOW_MEMORY = "low"      # < 512MB RAM
    NORMAL = "normal"       # 512MB - 2GB RAM  
    HIGH_MEMORY = "high"    # > 2GB RAM


@dataclass
class EmbeddedOptimizationConfig:
    """Configuration for embedded system optimizations."""
    
    # Memory management
    memory_mode: MemoryMode = MemoryMode.NORMAL
    max_buffer_size_mb: int = 64
    enable_memory_pooling: bool = True
    garbage_collection_threshold: int = 1000
    
    # CPU optimization
    cpu_architecture: CPUArchitecture = CPUArchitecture.X86_64
    enable_simd: bool = True
    enable_neon: bool = False  # ARM NEON instructions
    thread_count: int = 2
    cpu_affinity: Optional[list] = None
    
    # Real-time scheduling
    enable_realtime: bool = False
    realtime_priority: int = 50  # 1-99, higher = more priority
    scheduler_policy: str = "SCHED_FIFO"  # SCHED_FIFO, SCHED_RR
    
    # Audio buffer optimization
    audio_buffer_frames: int = 256
    audio_periods: int = 2
    enable_zero_copy: bool = True
    
    # Power management
    enable_power_saving: bool = False
    cpu_governor: str = "performance"  # performance, powersave, ondemand
    
    # Embedded-specific features
    enable_watchdog: bool = False
    watchdog_timeout_sec: int = 30
    enable_hardware_monitoring: bool = True


class EmbeddedConfigManager:
    """Manager for embedded system configurations."""
    
    def __init__(self):
        self.config = EmbeddedOptimizationConfig()
        self._detect_system_capabilities()
    
    def _detect_system_capabilities(self) -> None:
        """Auto-detect system capabilities and adjust configuration."""
        # Detect CPU architecture
        machine = platform.machine().lower()
        if machine in ["aarch64", "arm64"]:
            self.config.cpu_architecture = CPUArchitecture.ARM64
            self.config.enable_neon = True
        elif machine in ["armv7l", "armv6l"]:
            self.config.cpu_architecture = CPUArchitecture.ARM32
            self.config.enable_neon = True
        elif machine == "x86_64":
            self.config.cpu_architecture = CPUArchitecture.X86_64
        else:
            self.config.cpu_architecture = CPUArchitecture.X86
        
        # Detect available memory
        try:
            import psutil
            total_memory_mb = psutil.virtual_memory().total // (1024 * 1024)
            
            if total_memory_mb < 512:
                self.config.memory_mode = MemoryMode.LOW_MEMORY
                self.config.max_buffer_size_mb = 16
                self.config.thread_count = 1
                self.config.audio_buffer_frames = 128
            elif total_memory_mb < 2048:
                self.config.memory_mode = MemoryMode.NORMAL
                self.config.max_buffer_size_mb = 64
                self.config.thread_count = 2
            else:
                self.config.memory_mode = MemoryMode.HIGH_MEMORY
                self.config.max_buffer_size_mb = 128
                self.config.thread_count = min(4, os.cpu_count() or 2)
        except ImportError:
            # Fallback if psutil not available
            pass
        
        # Detect if running on embedded system
        if self._is_embedded_system():
            self.config.enable_power_saving = True
            self.config.enable_watchdog = True
            self.config.enable_hardware_monitoring = True
    
    def _is_embedded_system(self) -> bool:
        """Detect if running on an embedded system."""
        # Check for common embedded system indicators
        embedded_indicators = [
            "/proc/device-tree",  # Device tree (common on ARM)
            "/sys/firmware/devicetree",
            "/boot/config.txt",   # Raspberry Pi
        ]
        
        for indicator in embedded_indicators:
            if os.path.exists(indicator):
                return True
        
        # Check for ARM architecture
        if self.config.cpu_architecture in [CPUArchitecture.ARM64, CPUArchitecture.ARM32]:
            return True
        
        return False
    
    def get_optimization_flags(self) -> Dict[str, Any]:
        """Get compiler optimization flags for the current system."""
        flags = {
            "extra_compile_args": [],
            "extra_link_args": [],
            "define_macros": [],
        }
        
        # CPU-specific optimizations
        if self.config.cpu_architecture == CPUArchitecture.ARM64:
            flags["extra_compile_args"].extend([
                "-march=armv8-a",
                "-mtune=cortex-a72",
                "-mfpu=neon-fp-armv8" if self.config.enable_neon else "",
            ])
        elif self.config.cpu_architecture == CPUArchitecture.ARM32:
            flags["extra_compile_args"].extend([
                "-march=armv7-a",
                "-mtune=cortex-a7",
                "-mfpu=neon" if self.config.enable_neon else "",
            ])
        elif self.config.cpu_architecture == CPUArchitecture.X86_64:
            flags["extra_compile_args"].extend([
                "-march=native",
                "-mtune=native",
                "-msse4.2" if self.config.enable_simd else "",
                "-mavx2" if self.config.enable_simd else "",
            ])
        
        # Memory optimization flags
        if self.config.memory_mode == MemoryMode.LOW_MEMORY:
            flags["define_macros"].append(("LOW_MEMORY_MODE", "1"))
            flags["extra_compile_args"].append("-Os")  # Optimize for size
        else:
            flags["extra_compile_args"].append("-O3")  # Optimize for speed
        
        # Real-time optimization
        if self.config.enable_realtime:
            flags["define_macros"].append(("REALTIME_MODE", "1"))
            flags["extra_link_args"].append("-lrt")
        
        # Remove empty strings
        flags["extra_compile_args"] = [f for f in flags["extra_compile_args"] if f]
        
        return flags
    
    def apply_runtime_optimizations(self) -> None:
        """Apply runtime optimizations based on configuration."""
        try:
            import os
            import threading
            
            # Set CPU affinity if specified
            if self.config.cpu_affinity:
                try:
                    os.sched_setaffinity(0, self.config.cpu_affinity)
                except (AttributeError, OSError):
                    pass  # Not supported on this platform
            
            # Set real-time scheduling
            if self.config.enable_realtime:
                try:
                    import sched
                    if hasattr(sched, 'SCHED_FIFO'):
                        policy = getattr(sched, self.config.scheduler_policy, sched.SCHED_FIFO)
                        param = sched.sched_param(self.config.realtime_priority)
                        sched.sched_setscheduler(0, policy, param)
                except (ImportError, AttributeError, OSError):
                    pass  # Not supported on this platform
            
            # Set thread count for NumPy/SciPy
            os.environ["OMP_NUM_THREADS"] = str(self.config.thread_count)
            os.environ["OPENBLAS_NUM_THREADS"] = str(self.config.thread_count)
            os.environ["MKL_NUM_THREADS"] = str(self.config.thread_count)
            
        except Exception as e:
            # Log warning but don't fail
            print(f"Warning: Could not apply runtime optimizations: {e}")
    
    def get_audio_config(self) -> Dict[str, Any]:
        """Get optimized audio configuration."""
        return {
            "frames_per_buffer": self.config.audio_buffer_frames,
            "periods": self.config.audio_periods,
            "enable_zero_copy": self.config.enable_zero_copy,
            "max_buffer_size": self.config.max_buffer_size_mb * 1024 * 1024,
        }


# Global configuration instance
embedded_config = EmbeddedConfigManager()