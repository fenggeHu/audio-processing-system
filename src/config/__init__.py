"""
Configuration Module

System configuration management, settings persistence,
and environment-specific configurations.
"""

__version__ = "1.0.0"
__author__ = "Production Audio System Team"

from .audio_config import AudioConfig
from .system_config import SystemConfig
from .platform_config import PlatformConfigManager
from .embedded_config import EmbeddedConfigManager

__all__ = [
    "AudioConfig",
    "SystemConfig", 
    "PlatformConfigManager",
    "EmbeddedConfigManager"
]