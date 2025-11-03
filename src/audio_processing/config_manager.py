"""
Configuration management system for the audio processing system.

This module provides the ConfigManager class that handles JSON configuration
files, parameter validation, runtime hot updates, and version management
with rollback capabilities.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, Union
import structlog
from pydantic import BaseModel, ValidationError

from .base import BaseConfigurable
from .models import AudioConfig
from .exceptions import ConfigError

logger = structlog.get_logger(__name__)


class ConfigVersion(BaseModel):
    """Configuration version metadata."""
    version: int
    timestamp: datetime
    config_data: Dict[str, Any]
    description: Optional[str] = None
    user: Optional[str] = None


class ConfigManager(BaseConfigurable):
    """
    Configuration management system with JSON file support, validation,
    hot updates, and version management.
    
    Supports:
    - JSON configuration file management
    - Parameter validation with Pydantic models
    - Runtime hot updates without system restart
    - Configuration version history and rollback
    - Event-driven configuration change notifications
    """
    
    def __init__(self, 
                 config_path: Union[str, Path],
                 schema_model: Optional[type] = None,
                 auto_save: bool = True,
                 max_versions: int = 50):
        """
        Initialize ConfigManager.
        
        Args:
            config_path: Path to JSON configuration file
            schema_model: Pydantic model for validation (defaults to AudioConfig)
            auto_save: Whether to automatically save changes to file
            max_versions: Maximum number of versions to keep in history
        """
        self.config_path = Path(config_path)
        self.schema_model = schema_model or AudioConfig
        self.auto_save = auto_save
        self.max_versions = max_versions
        
        # Version management
        self._versions: List[ConfigVersion] = []
        self._current_version = 0
        
        # Event handlers for configuration changes
        self._change_handlers: List[Callable[[Dict[str, Any], Dict[str, Any]], None]] = []
        self._async_change_handlers: List[Callable[[Dict[str, Any], Dict[str, Any]], None]] = []
        
        # Load initial configuration
        initial_config = self._load_from_file()
        super().__init__(initial_config)
        
        # Create initial version
        self._create_version(initial_config, "Initial configuration")
    
    def _load_from_file(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        if not self.config_path.exists():
            logger.info("Config file not found, creating default", path=str(self.config_path))
            default_config = self._get_default_config()
            self._save_to_file(default_config)
            return default_config
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            logger.info("Configuration loaded from file", 
                       path=str(self.config_path),
                       keys=list(config_data.keys()))
            return config_data
            
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to load config file", 
                        path=str(self.config_path), 
                        error=str(e))
            raise ConfigError(f"Failed to load configuration: {e}")
    
    def _save_to_file(self, config_data: Dict[str, Any]) -> None:
        """Save configuration to JSON file."""
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write with pretty formatting
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info("Configuration saved to file", path=str(self.config_path))
            
        except IOError as e:
            logger.error("Failed to save config file", 
                        path=str(self.config_path), 
                        error=str(e))
            raise ConfigError(f"Failed to save configuration: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration based on schema model."""
        if hasattr(self.schema_model, 'model_validate'):
            # Pydantic v2
            default_instance = self.schema_model()
            return default_instance.model_dump()
        else:
            # Pydantic v1 or other
            default_instance = self.schema_model()
            return default_instance.dict() if hasattr(default_instance, 'dict') else {}
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate configuration using Pydantic model.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            # Use Pydantic model for validation
            if hasattr(self.schema_model, 'model_validate'):
                # Pydantic v2
                self.schema_model.model_validate(config)
            else:
                # Pydantic v1 or other validation
                self.schema_model(**config)
            
            return True
            
        except ValidationError as e:
            logger.error("Configuration validation failed", 
                        errors=e.errors() if hasattr(e, 'errors') else str(e))
            return False
        except Exception as e:
            logger.error("Unexpected validation error", error=str(e))
            return False
    
    async def apply_config(self, config: Dict[str, Any], 
                          description: Optional[str] = None,
                          user: Optional[str] = None) -> None:
        """
        Apply new configuration with validation, versioning, and hot updates.
        
        Args:
            config: New configuration to apply
            description: Optional description of the change
            user: Optional user who made the change
        """
        if not self.validate_config(config):
            raise ConfigError("Configuration validation failed")
        
        old_config = self._config.copy()
        
        # Apply configuration through parent class
        await super().apply_config(config)
        
        # Create new version
        self._create_version(config, description, user)
        
        # Save to file if auto_save is enabled
        if self.auto_save:
            self._save_to_file(config)
        
        # Notify change handlers
        await self._notify_change_handlers(old_config, config)
        
        logger.info("Configuration applied successfully",
                   version=self._current_version,
                   description=description,
                   user=user)
    
    def _create_version(self, config_data: Dict[str, Any], 
                       description: Optional[str] = None,
                       user: Optional[str] = None) -> None:
        """Create a new configuration version."""
        self._current_version += 1
        
        version = ConfigVersion(
            version=self._current_version,
            timestamp=datetime.now(),
            config_data=config_data.copy(),
            description=description,
            user=user
        )
        
        self._versions.append(version)
        
        # Limit version history
        if len(self._versions) > self.max_versions:
            self._versions.pop(0)
        
        logger.debug("Configuration version created", 
                    version=self._current_version,
                    total_versions=len(self._versions))
    
    async def rollback_to_version(self, version: int) -> None:
        """
        Rollback to a specific configuration version.
        
        Args:
            version: Version number to rollback to
        """
        target_version = None
        for v in self._versions:
            if v.version == version:
                target_version = v
                break
        
        if not target_version:
            raise ConfigError(f"Version {version} not found in history")
        
        logger.info("Rolling back configuration", 
                   from_version=self._current_version,
                   to_version=version)
        
        await self.apply_config(
            target_version.config_data,
            description=f"Rollback to version {version}",
            user="system"
        )
    
    async def rollback_steps(self, steps: int = 1) -> None:
        """
        Rollback configuration by number of steps.
        
        Args:
            steps: Number of versions to rollback
        """
        if steps <= 0:
            raise ValueError("Steps must be positive")
        
        if len(self._versions) < steps + 1:
            raise ConfigError(f"Cannot rollback {steps} steps, only {len(self._versions)-1} versions available")
        
        target_version = self._versions[-(steps + 1)]
        await self.rollback_to_version(target_version.version)
    
    def get_version_history(self) -> List[ConfigVersion]:
        """Get list of all configuration versions."""
        return self._versions.copy()
    
    def get_version(self, version: int) -> Optional[ConfigVersion]:
        """Get specific configuration version."""
        for v in self._versions:
            if v.version == version:
                return v
        return None
    
    def get_current_version(self) -> int:
        """Get current configuration version number."""
        return self._current_version
    
    def add_change_handler(self, handler: Callable[[Dict[str, Any], Dict[str, Any]], None]) -> None:
        """
        Add synchronous configuration change handler.
        
        Args:
            handler: Function that takes (old_config, new_config) parameters
        """
        self._change_handlers.append(handler)
    
    def add_async_change_handler(self, handler: Callable[[Dict[str, Any], Dict[str, Any]], None]) -> None:
        """
        Add asynchronous configuration change handler.
        
        Args:
            handler: Async function that takes (old_config, new_config) parameters
        """
        self._async_change_handlers.append(handler)
    
    def remove_change_handler(self, handler: Callable) -> None:
        """Remove configuration change handler."""
        if handler in self._change_handlers:
            self._change_handlers.remove(handler)
        if handler in self._async_change_handlers:
            self._async_change_handlers.remove(handler)
    
    async def _notify_change_handlers(self, old_config: Dict[str, Any], 
                                    new_config: Dict[str, Any]) -> None:
        """Notify all registered change handlers."""
        # Notify synchronous handlers
        for handler in self._change_handlers:
            try:
                handler(old_config, new_config)
            except Exception as e:
                logger.error("Error in sync change handler", error=str(e))
        
        # Notify asynchronous handlers
        for handler in self._async_change_handlers:
            try:
                await handler(old_config, new_config)
            except Exception as e:
                logger.error("Error in async change handler", error=str(e))
    
    def reload_from_file(self) -> None:
        """Reload configuration from file (synchronous)."""
        config_data = self._load_from_file()
        
        if not self.validate_config(config_data):
            raise ConfigError("Loaded configuration is invalid")
        
        self._config.copy()
        self._config = config_data
        self._config_version += 1
        
        # Create version for file reload
        self._create_version(config_data, "Reloaded from file", "system")
        
        logger.info("Configuration reloaded from file", path=str(self.config_path))
    
    async def hot_reload(self) -> None:
        """Hot reload configuration from file with full validation and notifications."""
        config_data = self._load_from_file()
        await self.apply_config(config_data, "Hot reload from file", "system")
    
