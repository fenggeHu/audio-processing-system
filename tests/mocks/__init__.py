"""
Mock implementations for testing audio processing components
"""

from .mock_portaudio import MockPortAudio, MockPyAudio, get_mock_portaudio

__all__ = ['MockPortAudio', 'MockPyAudio', 'get_mock_portaudio']