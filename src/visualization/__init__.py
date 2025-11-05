"""
Visualization Module

Real-time audio visualization, monitoring dashboards,
and user interface components.
"""

__version__ = "1.0.0"
__author__ = "Production Audio System Team"

from .dashboard import Dashboard
from .monitors import AudioMonitor
from .web_interface import WebInterface

__all__ = [
    "Dashboard",
    "AudioMonitor",
    "WebInterface"
]