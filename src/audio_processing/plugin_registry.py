"""
Plugin registry system for version management and metadata tracking.

This module provides comprehensive plugin registration, version control,
and dependency management capabilities.
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, asdict
from packaging import version
import structlog

from .exceptions import PluginError

logger = structlog.get_logger(__name__)


@dataclass
class PluginVersion:
    """Plugin version information."""
    major: int
    minor: int
    patch: int
    pre_release: Optional[str] = None
    build: Optional[str] = None
    
    def __str__(self) -> str:
        """String representation of version."""
        version_str = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre_release:
            version_str += f"-{self.pre_release}"
        if self.build:
            version_str += f"+{self.build}"
        return version_str
    
    @classmethod
    def from_string(cls, version_str: str) -> 'PluginVersion':
        """Create PluginVersion from string."""
        try:
            parsed = version.parse(version_str)
            return cls(
                major=parsed.major,
                minor=parsed.minor,
                patch=parsed.micro,
                pre_release=str(parsed.pre) if parsed.pre else None,
                build=str(parsed.local) if parsed.local else None
            )
        except Exception as e:
            raise PluginError(f"Invalid version string: {version_str}: {e}")
    
    def is_compatible_with(self, other: 'PluginVersion') -> bool:
        """Check if this version is compatible with another version."""
        # Same major version is compatible
        if self.major == other.major:
            return True
        
        # Major version 0 is only compatible with exact match
        if self.major == 0 or other.major == 0:
            return self == other
        
        return False
    
    def __eq__(self, other) -> bool:
        """Check version equality."""
        if not isinstance(other, PluginVersion):
            return False
        return (self.major == other.major and 
                self.minor == other.minor and 
                self.patch == other.patch and
                self.pre_release == other.pre_release)
    
    def __lt__(self, other) -> bool:
        """Check if this version is less than another."""
        if not isinstance(other, PluginVersion):
            return NotImplemented
        
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        if self.patch != other.patch:
            return self.patch < other.patch
        
        # Handle pre-release versions
        if self.pre_release and not other.pre_release:
            return True
        if not self.pre_release and other.pre_release:
            return False
        if self.pre_release and other.pre_release:
            return self.pre_release < other.pre_release
        
        return False


@dataclass
class PluginDependency:
    """Plugin dependency specification."""
    name: str
    version_spec: str  # e.g., ">=1.0.0,<2.0.0"
    optional: bool = False
    
    def is_satisfied_by(self, available_version: PluginVersion) -> bool:
        """Check if dependency is satisfied by available version."""
        try:
            # Simple version checking - in production use packaging.specifiers
            if self.version_spec.startswith(">="):
                min_version = PluginVersion.from_string(self.version_spec[2:])
                return available_version >= min_version
            elif self.version_spec.startswith("=="):
                exact_version = PluginVersion.from_string(self.version_spec[2:])
                return available_version == exact_version
            elif self.version_spec.startswith("~="):
                # Compatible release
                base_version = PluginVersion.from_string(self.version_spec[2:])
                return available_version.is_compatible_with(base_version)
            else:
                # Default to exact match
                target_version = PluginVersion.from_string(self.version_spec)
                return available_version == target_version
        except Exception:
            return False


@dataclass
class PluginMetadata:
    """Comprehensive plugin metadata."""
    name: str
    version: PluginVersion
    description: str
    author: str
    license: str
    homepage: Optional[str] = None
    repository: Optional[str] = None
    keywords: List[str] = None
    categories: List[str] = None
    dependencies: List[PluginDependency] = None
    
    # Technical metadata
    entry_point: str = "main"
    min_system_version: Optional[str] = None
    max_system_version: Optional[str] = None
    supported_platforms: List[str] = None
    
    # Registration metadata
    registration_time: Optional[datetime] = None
    file_hash: Optional[str] = None
    file_size: Optional[int] = None
    
    def __post_init__(self):
        """Initialize default values."""
        if self.keywords is None:
            self.keywords = []
        if self.categories is None:
            self.categories = []
        if self.dependencies is None:
            self.dependencies = []
        if self.supported_platforms is None:
            self.supported_platforms = ["any"]
        if self.registration_time is None:
            self.registration_time = datetime.now()


class PluginRegistry:
    """
    Comprehensive plugin registry with version management.
    
    Manages plugin metadata, versions, dependencies, and provides
    search and compatibility checking capabilities.
    """
    
    def __init__(self, registry_file: str = "plugin_registry.json"):
        self.registry_file = Path(registry_file)
        self._plugins: Dict[str, Dict[str, PluginMetadata]] = {}  # name -> version -> metadata
        self._load_registry()
    
    def register_plugin(self, metadata: PluginMetadata, 
                       plugin_file_path: Optional[str] = None) -> None:
        """
        Register a plugin with metadata.
        
        Args:
            metadata: Plugin metadata
            plugin_file_path: Path to plugin file for hash calculation
        """
        # Calculate file hash if path provided
        if plugin_file_path:
            metadata.file_hash = self._calculate_file_hash(plugin_file_path)
            metadata.file_size = Path(plugin_file_path).stat().st_size
        
        # Add to registry
        if metadata.name not in self._plugins:
            self._plugins[metadata.name] = {}
        
        version_str = str(metadata.version)
        self._plugins[metadata.name][version_str] = metadata
        
        logger.info(
            "Plugin registered",
            name=metadata.name,
            version=version_str,
            author=metadata.author
        )
        
        # Save registry
        self._save_registry()
    
    def unregister_plugin(self, name: str, version_str: Optional[str] = None) -> None:
        """
        Unregister a plugin or specific version.
        
        Args:
            name: Plugin name
            version_str: Specific version to unregister (None for all versions)
        """
        if name not in self._plugins:
            raise PluginError(f"Plugin not registered: {name}")
        
        if version_str:
            if version_str in self._plugins[name]:
                del self._plugins[name][version_str]
                logger.info("Plugin version unregistered", name=name, version=version_str)
            
            # Remove plugin entry if no versions left
            if not self._plugins[name]:
                del self._plugins[name]
        else:
            del self._plugins[name]
            logger.info("Plugin unregistered", name=name)
        
        self._save_registry()
    
    def get_plugin(self, name: str, version_str: Optional[str] = None) -> Optional[PluginMetadata]:
        """
        Get plugin metadata.
        
        Args:
            name: Plugin name
            version_str: Specific version (None for latest)
            
        Returns:
            Plugin metadata if found
        """
        if name not in self._plugins:
            return None
        
        versions = self._plugins[name]
        
        if version_str:
            return versions.get(version_str)
        else:
            # Return latest version
            if not versions:
                return None
            
            latest_version = max(
                versions.keys(),
                key=lambda v: PluginVersion.from_string(v)
            )
            return versions[latest_version]
    
    def list_plugins(self, category: Optional[str] = None, 
                    keyword: Optional[str] = None) -> List[PluginMetadata]:
        """
        List registered plugins with optional filtering.
        
        Args:
            category: Filter by category
            keyword: Filter by keyword
            
        Returns:
            List of plugin metadata (latest versions only)
        """
        plugins = []
        
        for name, versions in self._plugins.items():
            if not versions:
                continue
            
            # Get latest version
            latest_version = max(
                versions.keys(),
                key=lambda v: PluginVersion.from_string(v)
            )
            metadata = versions[latest_version]
            
            # Apply filters
            if category and category not in metadata.categories:
                continue
            
            if keyword and keyword not in metadata.keywords:
                continue
            
            plugins.append(metadata)
        
        return plugins
    
    def get_plugin_versions(self, name: str) -> List[PluginVersion]:
        """
        Get all available versions of a plugin.
        
        Args:
            name: Plugin name
            
        Returns:
            List of available versions, sorted newest first
        """
        if name not in self._plugins:
            return []
        
        versions = [
            PluginVersion.from_string(v) 
            for v in self._plugins[name].keys()
        ]
        
        return sorted(versions, reverse=True)
    
    def check_dependencies(self, name: str, 
                          version_str: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        Check if plugin dependencies are satisfied.
        
        Args:
            name: Plugin name
            version_str: Plugin version (None for latest)
            
        Returns:
            Tuple of (all_satisfied, missing_dependencies)
        """
        metadata = self.get_plugin(name, version_str)
        if not metadata:
            return False, [f"Plugin not found: {name}"]
        
        missing = []
        
        for dep in metadata.dependencies:
            if dep.optional:
                continue
            
            dep_metadata = self.get_plugin(dep.name)
            if not dep_metadata:
                missing.append(f"{dep.name} (not found)")
                continue
            
            if not dep.is_satisfied_by(dep_metadata.version):
                missing.append(f"{dep.name} {dep.version_spec} (have {dep_metadata.version})")
        
        return len(missing) == 0, missing
    
    def resolve_dependencies(self, name: str, 
                           version_str: Optional[str] = None) -> List[Tuple[str, str]]:
        """
        Resolve plugin dependencies in load order.
        
        Args:
            name: Plugin name
            version_str: Plugin version (None for latest)
            
        Returns:
            List of (plugin_name, version) tuples in dependency order
        """
        resolved = []
        visited = set()
        visiting = set()
        
        def visit(plugin_name: str, plugin_version: Optional[str] = None) -> None:
            if plugin_name in visiting:
                raise PluginError(f"Circular dependency detected: {plugin_name}")
            
            if plugin_name in visited:
                return
            
            visiting.add(plugin_name)
            
            metadata = self.get_plugin(plugin_name, plugin_version)
            if not metadata:
                raise PluginError(f"Plugin not found: {plugin_name}")
            
            # Visit dependencies first
            for dep in metadata.dependencies:
                if not dep.optional:
                    visit(dep.name)
            
            visiting.remove(plugin_name)
            visited.add(plugin_name)
            resolved.append((plugin_name, str(metadata.version)))
        
        visit(name, version_str)
        return resolved
    
    def search_plugins(self, query: str) -> List[PluginMetadata]:
        """
        Search plugins by name, description, or keywords.
        
        Args:
            query: Search query
            
        Returns:
            List of matching plugin metadata
        """
        query_lower = query.lower()
        matches = []
        
        for metadata in self.list_plugins():
            # Search in name
            if query_lower in metadata.name.lower():
                matches.append(metadata)
                continue
            
            # Search in description
            if query_lower in metadata.description.lower():
                matches.append(metadata)
                continue
            
            # Search in keywords
            if any(query_lower in keyword.lower() for keyword in metadata.keywords):
                matches.append(metadata)
                continue
        
        return matches
    
    def validate_plugin_compatibility(self, name: str, 
                                    system_version: str) -> bool:
        """
        Check if plugin is compatible with system version.
        
        Args:
            name: Plugin name
            system_version: Current system version
            
        Returns:
            True if compatible
        """
        metadata = self.get_plugin(name)
        if not metadata:
            return False
        
        sys_version = PluginVersion.from_string(system_version)
        
        # Check minimum version
        if metadata.min_system_version:
            min_version = PluginVersion.from_string(metadata.min_system_version)
            if sys_version < min_version:
                return False
        
        # Check maximum version
        if metadata.max_system_version:
            max_version = PluginVersion.from_string(metadata.max_system_version)
            if sys_version > max_version:
                return False
        
        return True
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics.
        
        Returns:
            Dictionary with registry statistics
        """
        total_plugins = len(self._plugins)
        total_versions = sum(len(versions) for versions in self._plugins.values())
        
        categories = set()
        keywords = set()
        authors = set()
        
        for metadata in self.list_plugins():
            categories.update(metadata.categories)
            keywords.update(metadata.keywords)
            authors.add(metadata.author)
        
        return {
            'total_plugins': total_plugins,
            'total_versions': total_versions,
            'unique_categories': len(categories),
            'unique_keywords': len(keywords),
            'unique_authors': len(authors),
            'categories': sorted(categories),
            'popular_keywords': sorted(keywords)[:10]  # Top 10
        }
    
    def export_registry(self, export_path: str) -> None:
        """
        Export registry to file.
        
        Args:
            export_path: Path to export file
        """
        export_data = {
            'export_time': datetime.now().isoformat(),
            'plugins': {}
        }
        
        for name, versions in self._plugins.items():
            export_data['plugins'][name] = {}
            for version_str, metadata in versions.items():
                export_data['plugins'][name][version_str] = self._metadata_to_dict(metadata)
        
        with open(export_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        logger.info("Registry exported", path=export_path)
    
    def import_registry(self, import_path: str, merge: bool = True) -> None:
        """
        Import registry from file.
        
        Args:
            import_path: Path to import file
            merge: Whether to merge with existing registry
        """
        with open(import_path, 'r') as f:
            import_data = json.load(f)
        
        if not merge:
            self._plugins.clear()
        
        plugins_data = import_data.get('plugins', {})
        for name, versions in plugins_data.items():
            if name not in self._plugins:
                self._plugins[name] = {}
            
            for version_str, metadata_dict in versions.items():
                metadata = self._dict_to_metadata(metadata_dict)
                self._plugins[name][version_str] = metadata
        
        self._save_registry()
        logger.info("Registry imported", path=import_path, merge=merge)
    
    def get_load_order(self) -> List[str]:
        """
        Get the load order of all registered plugins based on dependencies.
        
        Returns:
            List of plugin names in dependency order
        """
        load_order = []
        visited = set()
        visiting = set()
        
        def visit(plugin_name: str) -> None:
            if plugin_name in visiting:
                raise PluginError(f"Circular dependency detected: {plugin_name}")
            
            if plugin_name in visited:
                return
            
            visiting.add(plugin_name)
            
            metadata = self.get_plugin(plugin_name)
            if metadata:
                # Visit dependencies first
                for dep in metadata.dependencies:
                    if not dep.optional and dep.name in self._plugins:
                        visit(dep.name)
            
            visiting.remove(plugin_name)
            visited.add(plugin_name)
            load_order.append(plugin_name)
        
        # Visit all plugins
        for plugin_name in self._plugins.keys():
            if plugin_name not in visited:
                visit(plugin_name)
        
        return load_order

    def _load_registry(self) -> None:
        """Load registry from file."""
        if not self.registry_file.exists():
            logger.info("Registry file not found, starting with empty registry")
            return
        
        try:
            with open(self.registry_file, 'r') as f:
                data = json.load(f)
            
            for name, versions in data.items():
                self._plugins[name] = {}
                for version_str, metadata_dict in versions.items():
                    metadata = self._dict_to_metadata(metadata_dict)
                    self._plugins[name][version_str] = metadata
            
            logger.info("Registry loaded", plugins=len(self._plugins))
            
        except Exception as e:
            logger.error("Failed to load registry", error=str(e))
            self._plugins = {}
    
    def _save_registry(self) -> None:
        """Save registry to file."""
        try:
            # Ensure directory exists
            self.registry_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {}
            for name, versions in self._plugins.items():
                data[name] = {}
                for version_str, metadata in versions.items():
                    data[name][version_str] = self._metadata_to_dict(metadata)
            
            with open(self.registry_file, 'w') as f:
                json.dump(data, f, indent=2)
            
        except Exception as e:
            logger.error("Failed to save registry", error=str(e))
    
    def _metadata_to_dict(self, metadata: PluginMetadata) -> Dict[str, Any]:
        """Convert metadata to dictionary for serialization."""
        data = asdict(metadata)
        
        # Convert datetime to ISO string
        if data['registration_time']:
            data['registration_time'] = metadata.registration_time.isoformat()
        
        # Convert version to string
        data['version'] = str(metadata.version)
        
        # Convert dependencies to dictionaries
        data['dependencies'] = [asdict(dep) for dep in metadata.dependencies]
        
        return data
    
    def _dict_to_metadata(self, data: Dict[str, Any]) -> PluginMetadata:
        """Convert dictionary to metadata object."""
        # Convert version string to PluginVersion
        data['version'] = PluginVersion.from_string(data['version'])
        
        # Convert datetime string to datetime
        if data.get('registration_time'):
            data['registration_time'] = datetime.fromisoformat(data['registration_time'])
        
        # Convert dependencies to PluginDependency objects
        deps_data = data.get('dependencies', [])
        data['dependencies'] = [
            PluginDependency(**dep_data) for dep_data in deps_data
        ]
        
        return PluginMetadata(**data)
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()