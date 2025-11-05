"""
System Configuration Management

System-wide configuration settings and management.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from pathlib import Path
import yaml
import json
import os


@dataclass
class SystemConfig:
    """System configuration settings."""
    
    # System identification
    system_name: str = "ProductionAudioSystem"
    system_id: str = "default"
    
    # Logging configuration
    log_level: str = "INFO"
    log_dir: Path = Path("logs")
    enable_performance_logging: bool = True
    
    # Web interface
    web_enabled: bool = True
    web_port: int = 8080
    web_host: str = "0.0.0.0"
    
    # Monitoring
    enable_monitoring: bool = True
    monitoring_interval_sec: float = 1.0
    
    # Security
    enable_authentication: bool = False
    api_key: Optional[str] = None
    
    # Storage
    data_dir: Path = Path("data")
    config_dir: Path = Path("config")
    
    def __post_init__(self):
        # Ensure paths are Path objects
        if isinstance(self.log_dir, str):
            self.log_dir = Path(self.log_dir)
        if isinstance(self.data_dir, str):
            self.data_dir = Path(self.data_dir)
        if isinstance(self.config_dir, str):
            self.config_dir = Path(self.config_dir)
    
    @classmethod
    def from_file(cls, config_path: Path) -> 'SystemConfig':
        """Load system configuration from file."""
        if not config_path.exists():
            return cls()
        
        with open(config_path, 'r') as f:
            if config_path.suffix.lower() == '.json':
                data = json.load(f)
            else:
                data = yaml.safe_load(f)
        
        return cls(**data.get('system', {}))
    
    def to_file(self, config_path: Path) -> None:
        """Save system configuration to file."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert Path objects to strings for serialization
        data = {'system': {}}
        for key, value in self.__dict__.items():
            if isinstance(value, Path):
                data['system'][key] = str(value)
            else:
                data['system'][key] = value
        
        with open(config_path, 'w') as f:
            if config_path.suffix.lower() == '.json':
                json.dump(data, f, indent=2)
            else:
                yaml.dump(data, f, default_flow_style=False)
    
    def create_directories(self) -> None:
        """Create necessary directories."""
        directories = [
            self.log_dir,
            self.data_dir,
            self.config_dir,
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_environment_overrides(self) -> Dict[str, Any]:
        """Get configuration overrides from environment variables."""
        overrides = {}
        
        # Map environment variables to config fields
        env_mapping = {
            'AUDIO_SYSTEM_NAME': 'system_name',
            'AUDIO_SYSTEM_ID': 'system_id',
            'AUDIO_LOG_LEVEL': 'log_level',
            'AUDIO_LOG_DIR': 'log_dir',
            'AUDIO_WEB_PORT': 'web_port',
            'AUDIO_WEB_HOST': 'web_host',
            'AUDIO_DATA_DIR': 'data_dir',
            'AUDIO_CONFIG_DIR': 'config_dir',
        }
        
        for env_var, config_field in env_mapping.items():
            value = os.environ.get(env_var)
            if value is not None:
                # Type conversion based on field
                if config_field in ['web_port']:
                    overrides[config_field] = int(value)
                elif config_field in ['log_dir', 'data_dir', 'config_dir']:
                    overrides[config_field] = Path(value)
                elif config_field in ['enable_monitoring', 'enable_authentication', 'web_enabled']:
                    overrides[config_field] = value.lower() in ['true', '1', 'yes', 'on']
                else:
                    overrides[config_field] = value
        
        return overrides
    
    def apply_environment_overrides(self) -> None:
        """Apply environment variable overrides to configuration."""
        overrides = self.get_environment_overrides()
        
        for key, value in overrides.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def validate(self) -> List[str]:
        """Validate system configuration."""
        errors = []
        
        if not self.system_name:
            errors.append("System name cannot be empty")
        
        if not self.system_id:
            errors.append("System ID cannot be empty")
        
        if self.log_level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            errors.append(f"Invalid log level: {self.log_level}")
        
        if self.web_port < 1 or self.web_port > 65535:
            errors.append(f"Invalid web port: {self.web_port}")
        
        if self.monitoring_interval_sec <= 0:
            errors.append(f"Invalid monitoring interval: {self.monitoring_interval_sec}")
        
        return errors