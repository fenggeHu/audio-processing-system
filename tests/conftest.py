"""
Pytest configuration and test fixtures
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch

@pytest.fixture
def sample_audio_data():
    """Generate sample audio data for testing"""
    sample_rate = 48000
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio_data = 0.5 * np.sin(2 * np.pi * 440 * t)  # 440 Hz tone
    return audio_data.astype(np.float32)

@pytest.fixture
def mock_audio_config():
    """Mock audio configuration"""
    return {
        "sample_rate": 48000,
        "channels": 2,
        "buffer_size": 1024,
        "format": "float32"
    }

@pytest.fixture(autouse=True)
def mock_pyaudio():
    """Auto-use mock PyAudio for all tests"""
    try:
        with patch("pyaudio.PyAudio") as mock:
            yield mock
    except ImportError:
        # PyAudio not available, create a simple mock
        mock = Mock()
        mock.get_device_count.return_value = 0
        mock.get_device_info_by_index.return_value = {}
        yield mock

