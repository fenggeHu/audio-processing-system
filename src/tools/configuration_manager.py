"""
Configuration Management Interface

This module provides comprehensive configuration management including:
- Configuration save/load/import/export
- Configuration validation
- Configuration versioning
- Configuration templates
- Backup and restore functionality
"""

import json
import os
import shutil
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib

from ..config.system_config import SystemConfig


@dataclass
class ConfigurationVersion:
    """Configuration version information"""
    version_id: str
    timestamp: datetime
    description: str
    config_hash: str
    author: str = "system"
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass
class ConfigurationTemplate:
    """Configuration template"""
    template_id: str
    name: str
    description: str
    category: str
    config_data: Dict[str, Any]
    created_at: datetime
    author: str = "system"
    
    def __post_init__(self):
        if not hasattr(self, 'created_at') or self.created_at is None:
            self.created_at = datetime.now()


class ConfigurationManager:
    """Comprehensive configuration management interface"""
    
    def __init__(self, config_dir: str = "configs"):
        self.logger = logging.getLogger(__name__)
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        # Subdirectories
        self.versions_dir = self.config_dir / "versions"
        self.templates_dir = self.config_dir / "templates"
        self.backups_dir = self.config_dir / "backups"
        
        for dir_path in [self.versions_dir, self.templates_dir, self.backups_dir]:
            dir_path.mkdir(exist_ok=True)
        
        self.current_config: Dict[str, Any] = {}
        self.config_versions: List[ConfigurationVersion] = []
        self.config_templates: Dict[str, ConfigurationTemplate] = {}
        
        self._load_versions()
        self._load_templates()
    
    def save_configuration(self, config: Dict[str, Any], 
                          description: str = "", 
                          create_version: bool = True) -> bool:
        """Save current configuration"""
        try:
            # Calculate config hash
            config_str = json.dumps(config, sort_keys=True)
            config_hash = hashlib.md5(config_str.encode()).hexdigest()
            
            # Save main config file
            config_file = self.config_dir / "current_config.json"
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2, default=str)
            
            self.current_config = config.copy()
            
            # Create version if requested
            if create_version:
                version_id = f"v_{int(datetime.now().timestamp())}"
                version = ConfigurationVersion(
                    version_id=version_id,
                    timestamp=datetime.now(),
                    description=description or "Configuration saved",
                    config_hash=config_hash
                )
                
                # Save version file
                version_file = self.versions_dir / f"{version_id}.json"
                version_data = {
                    "version_info": asdict(version),
                    "config_data": config
                }
                
                with open(version_file, 'w') as f:
                    json.dump(version_data, f, indent=2, default=str)
                
                self.config_versions.append(version)
                self.config_versions.sort(key=lambda v: v.timestamp, reverse=True)
            
            self.logger.info(f"Configuration saved successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save configuration: {e}")
            return False
    
    def load_configuration(self, version_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Load configuration (current or specific version)"""
        try:
            if version_id:
                # Load specific version
                version_file = self.versions_dir / f"{version_id}.json"
                if not version_file.exists():
                    self.logger.error(f"Version {version_id} not found")
                    return None
                
                with open(version_file, 'r') as f:
                    version_data = json.load(f)
                
                config = version_data["config_data"]
                self.logger.info(f"Loaded configuration version {version_id}")
                
            else:
                # Load current configuration
                config_file = self.config_dir / "current_config.json"
                if not config_file.exists():
                    self.logger.warning("No current configuration found")
                    return {}
                
                with open(config_file, 'r') as f:
                    config = json.load(f)
                
                self.logger.info("Loaded current configuration")
            
            self.current_config = config
            return config
            
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            return None
    
    def import_configuration(self, file_path: str, 
                           validate: bool = True) -> bool:
        """Import configuration from file"""
        try:
            with open(file_path, 'r') as f:
                imported_config = json.load(f)
            
            if validate and not self.validate_configuration(imported_config):
                self.logger.error("Configuration validation failed")
                return False
            
            # Create backup before importing
            self.create_backup("pre_import_backup")
            
            # Save imported configuration
            description = f"Imported from {os.path.basename(file_path)}"
            return self.save_configuration(imported_config, description)
            
        except Exception as e:
            self.logger.error(f"Failed to import configuration: {e}")
            return False
    
    def export_configuration(self, file_path: str, 
                           version_id: Optional[str] = None,
                           include_metadata: bool = True) -> bool:
        """Export configuration to file"""
        try:
            config = self.load_configuration(version_id)
            if config is None:
                return False
            
            export_data = {"config_data": config}
            
            if include_metadata:
                export_data["metadata"] = {
                    "export_time": datetime.now().isoformat(),
                    "version_id": version_id,
                    "exported_by": "ConfigurationManager"
                }
            
            with open(file_path, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            self.logger.info(f"Configuration exported to {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export configuration: {e}")
            return False
    
    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        """Validate configuration structure and values"""
        try:
            # Basic structure validation
            required_sections = ["audio", "processing", "system"]
            for section in required_sections:
                if section not in config:
                    self.logger.error(f"Missing required section: {section}")
                    return False
            
            # Audio section validation
            audio_config = config.get("audio", {})
            if "sample_rate" in audio_config:
                sample_rate = audio_config["sample_rate"]
                if not isinstance(sample_rate, int) or sample_rate not in [44100, 48000, 96000]:
                    self.logger.error(f"Invalid sample rate: {sample_rate}")
                    return False
            
            # Processing section validation
            processing_config = config.get("processing", {})
            if "buffer_size" in processing_config:
                buffer_size = processing_config["buffer_size"]
                if not isinstance(buffer_size, int) or buffer_size < 64 or buffer_size > 8192:
                    self.logger.error(f"Invalid buffer size: {buffer_size}")
                    return False
            
            # System section validation
            system_config = config.get("system", {})
            if "max_cpu_usage" in system_config:
                max_cpu = system_config["max_cpu_usage"]
                if not isinstance(max_cpu, (int, float)) or max_cpu < 0 or max_cpu > 100:
                    self.logger.error(f"Invalid max CPU usage: {max_cpu}")
                    return False
            
            self.logger.info("Configuration validation passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Configuration validation error: {e}")
            return False
    
    def create_template(self, name: str, description: str, 
                       category: str = "custom",
                       config: Optional[Dict[str, Any]] = None) -> str:
        """Create configuration template"""
        template_id = f"template_{int(datetime.now().timestamp())}"
        
        if config is None:
            config = self.current_config.copy()
        
        template = ConfigurationTemplate(
            template_id=template_id,
            name=name,
            description=description,
            category=category,
            config_data=config,
            created_at=datetime.now()
        )
        
        # Save template file
        template_file = self.templates_dir / f"{template_id}.json"
        with open(template_file, 'w') as f:
            json.dump(asdict(template), f, indent=2, default=str)
        
        self.config_templates[template_id] = template
        self.logger.info(f"Created template {name} with ID {template_id}")
        
        return template_id
    
    def load_template(self, template_id: str) -> bool:
        """Load configuration from template"""
        if template_id not in self.config_templates:
            self.logger.error(f"Template {template_id} not found")
            return False
        
        template = self.config_templates[template_id]
        description = f"Loaded from template: {template.name}"
        
        return self.save_configuration(template.config_data, description)
    
    def list_templates(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List available configuration templates"""
        templates = []
        for template in self.config_templates.values():
            if category is None or template.category == category:
                templates.append({
                    "template_id": template.template_id,
                    "name": template.name,
                    "description": template.description,
                    "category": template.category,
                    "created_at": template.created_at.isoformat()
                })
        
        return sorted(templates, key=lambda t: t["created_at"], reverse=True)
    
    def create_backup(self, backup_name: Optional[str] = None) -> str:
        """Create system backup"""
        if backup_name is None:
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        backup_dir = self.backups_dir / backup_name
        backup_dir.mkdir(exist_ok=True)
        
        try:
            # Backup current config
            if self.current_config:
                backup_config_file = backup_dir / "config.json"
                with open(backup_config_file, 'w') as f:
                    json.dump(self.current_config, f, indent=2, default=str)
            
            # Backup versions
            versions_backup_dir = backup_dir / "versions"
            if self.versions_dir.exists():
                shutil.copytree(self.versions_dir, versions_backup_dir, dirs_exist_ok=True)
            
            # Backup templates
            templates_backup_dir = backup_dir / "templates"
            if self.templates_dir.exists():
                shutil.copytree(self.templates_dir, templates_backup_dir, dirs_exist_ok=True)
            
            # Create backup metadata
            metadata = {
                "backup_name": backup_name,
                "created_at": datetime.now().isoformat(),
                "config_versions_count": len(self.config_versions),
                "templates_count": len(self.config_templates)
            }
            
            metadata_file = backup_dir / "backup_metadata.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            self.logger.info(f"Created backup: {backup_name}")
            return backup_name
            
        except Exception as e:
            self.logger.error(f"Failed to create backup: {e}")
            return ""
    
    def restore_backup(self, backup_name: str) -> bool:
        """Restore from backup"""
        backup_dir = self.backups_dir / backup_name
        if not backup_dir.exists():
            self.logger.error(f"Backup {backup_name} not found")
            return False
        
        try:
            # Create current backup before restore
            self.create_backup("pre_restore_backup")
            
            # Restore config
            backup_config_file = backup_dir / "config.json"
            if backup_config_file.exists():
                with open(backup_config_file, 'r') as f:
                    restored_config = json.load(f)
                self.save_configuration(restored_config, f"Restored from backup: {backup_name}")
            
            # Restore versions
            versions_backup_dir = backup_dir / "versions"
            if versions_backup_dir.exists():
                if self.versions_dir.exists():
                    shutil.rmtree(self.versions_dir)
                shutil.copytree(versions_backup_dir, self.versions_dir)
                self._load_versions()
            
            # Restore templates
            templates_backup_dir = backup_dir / "templates"
            if templates_backup_dir.exists():
                if self.templates_dir.exists():
                    shutil.rmtree(self.templates_dir)
                shutil.copytree(templates_backup_dir, self.templates_dir)
                self._load_templates()
            
            self.logger.info(f"Restored from backup: {backup_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to restore backup: {e}")
            return False
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """List available backups"""
        backups = []
        
        for backup_dir in self.backups_dir.iterdir():
            if backup_dir.is_dir():
                metadata_file = backup_dir / "backup_metadata.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                        backups.append(metadata)
                    except:
                        # Fallback for backups without metadata
                        backups.append({
                            "backup_name": backup_dir.name,
                            "created_at": datetime.fromtimestamp(backup_dir.stat().st_mtime).isoformat()
                        })
        
        return sorted(backups, key=lambda b: b["created_at"], reverse=True)
    
    def get_configuration_diff(self, version1_id: str, version2_id: str) -> Dict[str, Any]:
        """Get differences between two configuration versions"""
        config1 = self.load_configuration(version1_id)
        config2 = self.load_configuration(version2_id)
        
        if config1 is None or config2 is None:
            return {"error": "One or both configurations not found"}
        
        diff = {
            "version1_id": version1_id,
            "version2_id": version2_id,
            "differences": self._calculate_config_diff(config1, config2)
        }
        
        return diff
    
    def _load_versions(self):
        """Load configuration versions from disk"""
        self.config_versions.clear()
        
        for version_file in self.versions_dir.glob("*.json"):
            try:
                with open(version_file, 'r') as f:
                    version_data = json.load(f)
                
                version_info = version_data["version_info"]
                version = ConfigurationVersion(
                    version_id=version_info["version_id"],
                    timestamp=datetime.fromisoformat(version_info["timestamp"]),
                    description=version_info["description"],
                    config_hash=version_info["config_hash"],
                    author=version_info.get("author", "system"),
                    tags=version_info.get("tags", [])
                )
                
                self.config_versions.append(version)
                
            except Exception as e:
                self.logger.error(f"Failed to load version from {version_file}: {e}")
        
        self.config_versions.sort(key=lambda v: v.timestamp, reverse=True)
    
    def _load_templates(self):
        """Load configuration templates from disk"""
        self.config_templates.clear()
        
        for template_file in self.templates_dir.glob("*.json"):
            try:
                with open(template_file, 'r') as f:
                    template_data = json.load(f)
                
                template = ConfigurationTemplate(
                    template_id=template_data["template_id"],
                    name=template_data["name"],
                    description=template_data["description"],
                    category=template_data["category"],
                    config_data=template_data["config_data"],
                    created_at=datetime.fromisoformat(template_data["created_at"]),
                    author=template_data.get("author", "system")
                )
                
                self.config_templates[template.template_id] = template
                
            except Exception as e:
                self.logger.error(f"Failed to load template from {template_file}: {e}")
    
    def _calculate_config_diff(self, config1: Dict[str, Any], 
                             config2: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Calculate differences between two configurations"""
        differences = []
        
        def compare_dicts(d1, d2, path=""):
            for key in set(d1.keys()) | set(d2.keys()):
                current_path = f"{path}.{key}" if path else key
                
                if key not in d1:
                    differences.append({
                        "type": "added",
                        "path": current_path,
                        "value": d2[key]
                    })
                elif key not in d2:
                    differences.append({
                        "type": "removed",
                        "path": current_path,
                        "value": d1[key]
                    })
                elif isinstance(d1[key], dict) and isinstance(d2[key], dict):
                    compare_dicts(d1[key], d2[key], current_path)
                elif d1[key] != d2[key]:
                    differences.append({
                        "type": "modified",
                        "path": current_path,
                        "old_value": d1[key],
                        "new_value": d2[key]
                    })
        
        compare_dicts(config1, config2)
        return differences