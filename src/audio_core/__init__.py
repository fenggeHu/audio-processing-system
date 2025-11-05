"""
Audio Core Module

Core audio processing functionality including hardware interfaces,
device management, and low-level audio operations.
"""

__version__ = "1.0.0"
__author__ = "Production Audio System Team"

from .device_manager import DeviceManager
from .hardware_interface import HardwareAbstractionLayer, IHardwareDevice
from .models import AudioFrame

__all__ = [
    "DeviceManager",
    "HardwareAbstractionLayer",
    "IHardwareDevice",
    "AudioFrame"
]