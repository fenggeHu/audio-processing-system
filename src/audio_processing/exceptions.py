"""
Custom exceptions for the audio processing system.

This module defines all custom exception types used throughout
the audio processing system for better error handling and debugging.
"""


class AudioProcessingError(Exception):
    """Base exception for all audio processing errors."""
    
    def __init__(self, message: str, service_name: str = None, 
                 error_code: str = None):
        super().__init__(message)
        self.service_name = service_name
        self.error_code = error_code
        self.message = message
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.service_name:
            parts.append(f"Service: {self.service_name}")
        if self.error_code:
            parts.append(f"Code: {self.error_code}")
        return " | ".join(parts)


class ServiceError(AudioProcessingError):
    """Exception raised when service operations fail."""


class ConfigError(AudioProcessingError):
    """Exception raised when configuration is invalid or cannot be applied."""


class ProcessingError(AudioProcessingError):
    """Exception raised during audio frame processing."""


class DeviceError(AudioProcessingError):
    """Exception raised when audio device operations fail."""


class ProcessingTimeoutError(AudioProcessingError):
    """Exception raised when processing takes too long."""


class DependencyError(AudioProcessingError):
    """Exception raised when service dependencies are not met."""


class PluginError(AudioProcessingError):
    """Exception raised during plugin operations."""
