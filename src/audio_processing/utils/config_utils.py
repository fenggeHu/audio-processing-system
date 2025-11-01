"""
Configuration management utilities and CLI tools.

This module provides utility functions and a command-line interface
for managing audio system configurations using the ConfigManager.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional
import click
import structlog

from ..config_manager import ConfigManager
from ..models import AudioConfig
from ..exceptions import ConfigError

logger = structlog.get_logger(__name__)


class ConfigManagerCLI:
    """Command-line interface for configuration management."""
    
    def __init__(self, config_path: str = "config/audio_system.json"):
        self.config_path = Path(config_path)
        self.manager = ConfigManager(
            config_path=self.config_path,
            schema_model=AudioConfig,
            auto_save=True
        )
    
    async def show_current_config(self) -> None:
        """Display current configuration."""
        config = self.manager.get_current_config()
        version = self.manager.get_current_version()
        
        print(f"\n=== Current Configuration (Version {version}) ===")
        print(json.dumps(config, indent=2))
        print()
    
    async def show_version_history(self) -> None:
        """Display configuration version history."""
        versions = self.manager.get_version_history()
        
        print("\n=== Configuration Version History ===")
        for version in versions:
            print(f"Version {version.version}: {version.timestamp}")
            if version.description:
                print(f"  Description: {version.description}")
            if version.user:
                print(f"  User: {version.user}")
            print()
    
    async def update_config(self, updates: Dict[str, Any], 
                          description: Optional[str] = None) -> None:
        """Update configuration with new values."""
        try:
            current_config = self.manager.get_current_config()
            new_config = current_config.copy()
            new_config.update(updates)
            
            await self.manager.apply_config(
                new_config,
                description=description or "CLI update",
                user="cli_user"
            )
            
            print(f"✓ Configuration updated successfully")
            print(f"  New version: {self.manager.get_current_version()}")
            
        except ConfigError as e:
            print(f"✗ Configuration update failed: {e}")
            sys.exit(1)
    
    async def rollback_config(self, steps: int = 1) -> None:
        """Rollback configuration by specified steps."""
        try:
            old_version = self.manager.get_current_version()
            await self.manager.rollback_steps(steps)
            new_version = self.manager.get_current_version()
            
            print(f"✓ Configuration rolled back")
            print(f"  From version {old_version} to {new_version}")
            
        except ConfigError as e:
            print(f"✗ Rollback failed: {e}")
            sys.exit(1)
    
    async def validate_config_file(self, file_path: str) -> None:
        """Validate a configuration file."""
        try:
            with open(file_path, 'r') as f:
                config_data = json.load(f)
            
            if self.manager.validate_config(config_data):
                print(f"✓ Configuration file {file_path} is valid")
            else:
                print(f"✗ Configuration file {file_path} is invalid")
                sys.exit(1)
                
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"✗ Error reading configuration file: {e}")
            sys.exit(1)
    
    async def export_config(self, export_path: str) -> None:
        """Export current configuration to file."""
        try:
            self.manager.export_config(export_path)
            print(f"✓ Configuration exported to {export_path}")
            
        except ConfigError as e:
            print(f"✗ Export failed: {e}")
            sys.exit(1)
    
    async def hot_reload(self) -> None:
        """Hot reload configuration from file."""
        try:
            old_version = self.manager.get_current_version()
            await self.manager.hot_reload()
            new_version = self.manager.get_current_version()
            
            if new_version > old_version:
                print(f"✓ Configuration hot reloaded")
                print(f"  Version updated from {old_version} to {new_version}")
            else:
                print("ℹ No changes detected in configuration file")
                
        except ConfigError as e:
            print(f"✗ Hot reload failed: {e}")
            sys.exit(1)


# CLI Commands using Click
@click.group()
@click.option('--config-path', default='config/audio_system.json',
              help='Path to configuration file')
@click.pass_context
def cli(ctx, config_path):
    """Audio System Configuration Manager CLI."""
    ctx.ensure_object(dict)
    ctx.obj['config_path'] = config_path


@cli.command()
@click.pass_context
def show(ctx):
    """Show current configuration."""
    cli_manager = ConfigManagerCLI(ctx.obj['config_path'])
    asyncio.run(cli_manager.show_current_config())


@cli.command()
@click.pass_context
def history(ctx):
    """Show configuration version history."""
    cli_manager = ConfigManagerCLI(ctx.obj['config_path'])
    asyncio.run(cli_manager.show_version_history())


@cli.command()
@click.option('--sample-rate', type=int, help='Audio sample rate')
@click.option('--channels', type=int, help='Number of audio channels')
@click.option('--frame-size', type=int, help='Frame size in samples')
@click.option('--enable-ssl/--disable-ssl', help='Enable/disable SSL')
@click.option('--enable-aec/--disable-aec', help='Enable/disable AEC')
@click.option('--description', help='Description of the change')
@click.pass_context
def update(ctx, sample_rate, channels, frame_size, enable_ssl, enable_aec, description):
    """Update configuration parameters."""
    updates = {}
    
    if sample_rate is not None:
        updates['sample_rate'] = sample_rate
    if channels is not None:
        updates['channels'] = channels
    if frame_size is not None:
        updates['frame_size'] = frame_size
    if enable_ssl is not None:
        updates['enable_ssl'] = enable_ssl
    if enable_aec is not None:
        updates['enable_aec'] = enable_aec
    
    if not updates:
        print("No updates specified. Use --help to see available options.")
        return
    
    cli_manager = ConfigManagerCLI(ctx.obj['config_path'])
    asyncio.run(cli_manager.update_config(updates, description))


@cli.command()
@click.option('--steps', default=1, help='Number of versions to rollback')
@click.pass_context
def rollback(ctx, steps):
    """Rollback configuration to previous version."""
    cli_manager = ConfigManagerCLI(ctx.obj['config_path'])
    asyncio.run(cli_manager.rollback_config(steps))


@cli.command()
@click.argument('file_path')
@click.pass_context
def validate(ctx, file_path):
    """Validate a configuration file."""
    cli_manager = ConfigManagerCLI(ctx.obj['config_path'])
    asyncio.run(cli_manager.validate_config_file(file_path))


@cli.command()
@click.argument('export_path')
@click.pass_context
def export(ctx, export_path):
    """Export current configuration to file."""
    cli_manager = ConfigManagerCLI(ctx.obj['config_path'])
    asyncio.run(cli_manager.export_config(export_path))


@cli.command()
@click.pass_context
def reload(ctx):
    """Hot reload configuration from file."""
    cli_manager = ConfigManagerCLI(ctx.obj['config_path'])
    asyncio.run(cli_manager.hot_reload())


# Utility functions for programmatic use
async def create_config_manager(config_path: str = "config/audio_system.json") -> ConfigManager:
    """
    Create and initialize a ConfigManager instance.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Initialized ConfigManager instance
    """
    return ConfigManager(
        config_path=config_path,
        schema_model=AudioConfig,
        auto_save=True
    )


async def apply_config_preset(manager: ConfigManager, preset_name: str) -> None:
    """
    Apply a predefined configuration preset.
    
    Args:
        manager: ConfigManager instance
        preset_name: Name of the preset to apply
    """
    presets = {
        "high_quality": {
            "sample_rate": 48000,
            "frame_size": 480,
            "channels": 8,
            "enable_ssl": True,
            "enable_beamforming": True,
            "enable_aec": True,
            "enable_denoise": True,
            "enable_agc": True,
            "max_latency_ms": 40.0,
            "cpu_limit_percent": 80.0
        },
        "low_latency": {
            "sample_rate": 48000,
            "frame_size": 240,  # Smaller frame for lower latency
            "channels": 4,
            "enable_ssl": False,
            "enable_beamforming": False,
            "enable_aec": True,
            "enable_denoise": False,
            "enable_agc": True,
            "max_latency_ms": 20.0,
            "cpu_limit_percent": 60.0
        },
        "power_save": {
            "sample_rate": 16000,  # Lower sample rate
            "frame_size": 320,
            "channels": 2,
            "enable_ssl": False,
            "enable_beamforming": False,
            "enable_aec": False,
            "enable_denoise": False,
            "enable_agc": True,
            "max_latency_ms": 100.0,
            "cpu_limit_percent": 40.0
        }
    }
    
    if preset_name not in presets:
        raise ConfigError(f"Unknown preset: {preset_name}")
    
    preset_config = presets[preset_name]
    current_config = manager.get_current_config()
    new_config = current_config.copy()
    new_config.update(preset_config)
    
    await manager.apply_config(
        new_config,
        description=f"Applied {preset_name} preset",
        user="system"
    )


if __name__ == "__main__":
    cli()