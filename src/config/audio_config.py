"""
Audio Configuration Management

Configuration classes and utilities for audio system settings.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from pathlib import Path
import yaml
import json


@dataclass
class AudioConfig:
    """Audio system configuration."""
    
    # Basic audio parameters
    sample_rate: int = 48000
    buffer_size: int = 256
    channels: int = 2
    bit_depth: int = 24
    
    # Device configuration
    input_device: Optional[str] = None
    output_device: Optional[str] = None
    
    # Processing configuration
    enable_processing: bool = True
    processing_components: List[str] = None
    
    # Performance settings
    max_latency_ms: float = 20.0
    target_latency_ms: float = 10.0
    
    def __post_init__(self):
        if self.processing_components is None:
            self.processing_components = []
    
    @classmethod
    def from_file(cls, config_path: Path) -> 'AudioConfig':
        """Load configuration from file."""
        if not config_path.exists():
            return cls()
        
        with open(config_path, 'r') as f:
            if config_path.suffix.lower() == '.json':
                data = json.load(f)
            else:
                data = yaml.safe_load(f)
        
        return cls(**data.get('audio', {}))
    
    def to_file(self, config_path: Path) -> None:
        """Save configuration to file."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {'audio': self.__dict__}
        
        with open(config_path, 'w') as f:
            if config_path.suffix.lower() == '.json':
                json.dump(data, f, indent=2)
            else:
                yaml.dump(data, f, default_flow_style=False)
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        if self.sample_rate not in [44100, 48000, 96000, 192000]:
            errors.append(f"Invalid sample rate: {self.sample_rate}")
        
        if self.buffer_size not in [64, 128, 256, 512, 1024, 2048]:
            errors.append(f"Invalid buffer size: {self.buffer_size}")
        
        if self.channels < 1 or self.channels > 32:
            errors.append(f"Invalid channel count: {self.channels}")
        
        if self.bit_depth not in [16, 24, 32]:
            errors.append(f"Invalid bit depth: {self.bit_depth}")
        
        if self.max_latency_ms <= 0:
            errors.append(f"Invalid max latency: {self.max_latency_ms}")
        
        if self.target_latency_ms <= 0 or self.target_latency_ms > self.max_latency_ms:
            errors.append(f"Invalid target latency: {self.target_latency_ms}")
        
        return errors