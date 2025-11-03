"""
Test data generator for creating realistic Python projects with cleanup opportunities.

This module generates various types of Python projects with known patterns of
unused code, imports, files, and dependencies for comprehensive testing.
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ProjectStructure:
    """Configuration for generated project structure."""
    files: int = 10
    modules: int = 3
    unused_imports_per_file: int = 2
    dead_functions_per_file: int = 1
    orphaned_files: int = 2
    unused_dependencies: int = 2


class TestDataGenerator:
    """Generate realistic test projects with various cleanup opportunities."""
    
    # Common Python imports that might be unused
    COMMON_IMPORTS = [
        'os', 'sys', 'json', 'time', 'datetime', 'pathlib', 'collections',
        'itertools', 'functools', 'operator', 'math', 'random', 'string',
        'typing', 'dataclasses', 'enum', 'abc', 'contextlib', 'warnings'
    ]
    
    # Typing imports that are often unused
    TYPING_IMPORTS = [
        'Dict', 'List', 'Tuple', 'Set', 'Optional', 'Union', 'Any', 'Callable',
        'Iterator', 'Generator', 'TypeVar', 'Generic', 'Protocol'
    ]
    
    # Third-party packages that might be unused
    THIRD_PARTY_PACKAGES = [
        'requests', 'numpy', 'pandas', 'matplotlib', 'scipy', 'sklearn',
        'flask', 'django', 'fastapi', 'click', 'pydantic', 'sqlalchemy'
    ]
    
    # Common function name patterns
    FUNCTION_PATTERNS = [
        'process_data', 'validate_input', 'format_output', 'calculate_result',
        'parse_config', 'handle_error', 'log_message', 'send_notification',
        'update_status', 'check_permission', 'generate_report', 'cleanup_temp'
    ]
    
    # Class name patterns
    CLASS_PATTERNS = [
        'DataProcessor', 'ConfigManager', 'ErrorHandler', 'Logger',
        'NotificationService', 'StatusUpdater', 'PermissionChecker',
        'ReportGenerator', 'TempCleaner', 'ValidationService'
    ]
    
    def __init__(self, config_file: Optional[str] = None):
        """Initialize generator with optional configuration."""
        self.config = {}
        if config_file:
            with open(config_file, 'r') as f:
                self.config = json.load(f)
    
    def generate_unused_imports(self, count: int) -> List[str]:
        """Generate a list of unused import statements."""
        imports = []
        
        # Standard library imports
        std_imports = random.sample(self.COMMON_IMPORTS, min(count // 2, len(self.COMMON_IMPORTS)))
        imports.extend(f"import {imp}" for imp in std_imports)
        
        # Typing imports
        if count > len(std_imports):
            remaining = count - len(std_imports)
            typing_imports = random.sample(self.TYPING_IMPORTS, min(remaining, len(self.TYPING_IMPORTS)))
            if typing_imports:
                imports.append(f"from typing import {', '.join(typing_imports)}")
        
        return imports[:count]
    
    def generate_used_imports(self, count: int) -> Tuple[List[str], List[str]]:
        """Generate imports that will be used in the code."""
        imports = []
        used_names = []
        
        # Always include some basic imports that will be used
        basic_imports = ['json', 'sys', 'os'][:count]
        imports.extend(f"import {imp}" for imp in basic_imports)
        used_names.extend(basic_imports)
        
        return imports, used_names
    
    def generate_function(self, name: str, is_used: bool = True) -> str:
        """Generate a function definition."""
        params = random.choice([
            '', 'x', 'data', 'value', 'config', 'x, y', 'data, config'
        ])
        
        return_type = random.choice(['str', 'int', 'bool', 'Dict[str, Any]', 'Optional[str]'])
        
        if is_used:
            # Simple implementation that might use imports
            body_options = [
                'return json.dumps({"result": "success"})',
                'return str(value) if value else "default"',
                'return len(data) if data else 0',
                'print("Processing..."); return True'
            ]
        else:
            # Unused function with more complex body
            body_options = [
                'return "unused_result"',
                'complex_calculation = sum(range(100)); return complex_calculation',
                'import math; return math.sqrt(42)',
                'return {"unused": True, "complexity": "high"}'
            ]
        
        body = random.choice(body_options)
        
        return f'''def {name}({params}) -> {return_type}:
    """{'Used' if is_used else 'Unused'} function: {name}."""
    {body}'''
    
    def generate_class(self, name: str, is_used: bool = True) -> str:
        """Generate a class definition."""
        methods = []
        
        # Always include __init__
        methods.append('''    def __init__(self, config: Optional[Dict] = None):
        """Initialize the class."""
        self.config = config or {}''')
        
        # Add some methods
        method_count = random.randint(1, 3)
        for i in range(method_count):
            method_name = f"method_{i + 1}"
            if is_used and i == 0:
                # First method will be used
                methods.append(f'''    def {method_name}(self) -> str:
        """Used method."""
        return json.dumps(self.config)''')
            else:
                methods.append(f'''    def {method_name}(self) -> str:
        """{'Used' if is_used else 'Unused'} method."""
        return "result_{i + 1}"''')
        
        methods_str = '\n\n'.join(methods)
        
        return f'''class {name}:
    """{'Used' if is_used else 'Unused'} class: {name}."""

{methods_str}'''
    
    def generate_python_file(self, 
                           module_name: str, 
                           structure: ProjectStructure,
                           used_functions: Optional[List[str]] = None,
                           used_classes: Optional[List[str]] = None) -> Tuple[str, Dict[str, Any]]:
        """Generate a complete Python file with imports, functions, and classes."""
        
        used_functions = used_functions or []
        used_classes = used_classes or []
        
        lines = []
        metadata = {
            'unused_imports': [],
            'dead_functions': [],
            'dead_classes': [],
            'used_functions': used_functions,
            'used_classes': used_classes
        }
        
        # Generate imports
        unused_imports = self.generate_unused_imports(structure.unused_imports_per_file)
        used_imports, used_names = self.generate_used_imports(2)
        
        all_imports = unused_imports + used_imports
        random.shuffle(all_imports)
        
        lines.extend(all_imports)
        lines.append('')  # Empty line after imports
        
        metadata['unused_imports'] = [imp for imp in unused_imports]
        
        # Generate functions
        function_count = structure.dead_functions_per_file + len(used_functions)
        
        for i in range(function_count):
            if i < len(used_functions):
                func_name = used_functions[i]
                func_code = self.generate_function(func_name, is_used=True)
            else:
                func_name = f"unused_{random.choice(self.FUNCTION_PATTERNS).lower()}_{i}"
                func_code = self.generate_function(func_name, is_used=False)
                metadata['dead_functions'].append(func_name)
            
            lines.append(func_code)
            lines.append('')  # Empty line after function
        
        # Generate classes
        class_count = 1 + len(used_classes)  # At least one unused class
        
        for i in range(class_count):
            if i < len(used_classes):
                class_name = used_classes[i]
                class_code = self.generate_class(class_name, is_used=True)
            else:
                class_name = f"Unused{random.choice(self.CLASS_PATTERNS)}{i}"
                class_code = self.generate_class(class_name, is_used=False)
                metadata['dead_classes'].append(class_name)
            
            lines.append(class_code)
            lines.append('')  # Empty line after class
        
        # Add some code that uses the used functions/classes
        if used_functions or used_classes:
            lines.append('# Usage of functions and classes')
            
            for func_name in used_functions:
                lines.append(f'result_{func_name} = {func_name}()')
            
            for class_name in used_classes:
                lines.append(f'instance_{class_name.lower()} = {class_name}()')
                lines.append(f'output_{class_name.lower()} = instance_{class_name.lower()}.method_1()')
        
        return '\n'.join(lines), metadata
    
    def generate_requirements_file(self, structure: ProjectStructure) -> Tuple[str, List[str]]:
        """Generate requirements.txt with unused dependencies."""
        used_packages = random.sample(self.THIRD_PARTY_PACKAGES, 3)
        unused_packages = random.sample(
            [pkg for pkg in self.THIRD_PARTY_PACKAGES if pkg not in used_packages],
            structure.unused_dependencies
        )
        
        all_packages = used_packages + unused_packages
        
        requirements = []
        for package in all_packages:
            version = f"{random.randint(1, 3)}.{random.randint(0, 10)}.{random.randint(0, 5)}"
            requirements.append(f"{package}=={version}")
        
        return '\n'.join(requirements), unused_packages
    
    def generate_pyproject_toml(self, structure: ProjectStructure) -> Tuple[str, List[str]]:
        """Generate pyproject.toml with dependencies."""
        used_packages = ['requests', 'click']
        unused_packages = random.sample(
            [pkg for pkg in self.THIRD_PARTY_PACKAGES if pkg not in used_packages],
            structure.unused_dependencies
        )
        
        all_packages = used_packages + unused_packages
        
        dependencies = [f'"{pkg}>={random.randint(1, 3)}.{random.randint(0, 10)}.0"' 
                       for pkg in all_packages]
        
        toml_content = f'''[build-system]
requires = ["setuptools", "wheel"]

[project]
name = "test-project"
version = "0.1.0"
dependencies = [
    {',\n    '.join(dependencies)}
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "black>=22.0.0"
]
'''
        
        return toml_content, unused_packages
    
    def generate_orphaned_files(self, project_dir: Path, count: int) -> List[str]:
        """Generate orphaned files that aren't referenced anywhere."""
        orphaned_files = []
        
        for i in range(count):
            # Generate different types of orphaned files
            file_types = [
                ('config', '.json', '{"orphaned": true}'),
                ('test', '.py', 'def test_nonexistent(): pass'),
                ('data', '.txt', 'orphaned data file'),
                ('script', '.py', 'print("orphaned script")')
            ]
            
            file_type, ext, content = random.choice(file_types)
            filename = f"orphaned_{file_type}_{i}{ext}"
            
            file_path = project_dir / filename
            file_path.write_text(content)
            orphaned_files.append(str(file_path))
        
        return orphaned_files
    
    def create_test_project(self, 
                          project_dir: Path, 
                          structure: ProjectStructure,
                          project_name: str = "test_project") -> Dict[str, Any]:
        """Create a complete test project with known cleanup opportunities."""
        
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Create source directory structure
        src_dir = project_dir / "src" / project_name
        src_dir.mkdir(parents=True, exist_ok=True)
        
        tests_dir = project_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        
        metadata = {
            'project_name': project_name,
            'structure': structure,
            'files': {},
            'orphaned_files': [],
            'unused_dependencies': [],
            'expected_cleanup_items': {
                'unused_imports': 0,
                'dead_functions': 0,
                'dead_classes': 0,
                'orphaned_files': 0,
                'unused_dependencies': 0
            }
        }
        
        # Generate modules
        for module_idx in range(structure.modules):
            module_name = f"module_{module_idx}"
            module_dir = src_dir / module_name
            module_dir.mkdir(exist_ok=True)
            
            # Create __init__.py
            (module_dir / "__init__.py").write_text("")
            
            # Generate files in module
            files_per_module = structure.files // structure.modules
            if module_idx == 0:
                files_per_module += structure.files % structure.modules  # Add remainder to first module
            
            for file_idx in range(files_per_module):
                file_name = f"file_{file_idx}.py"
                
                # Determine what functions/classes will be used
                used_functions = []
                used_classes = []
                
                if file_idx == 0:  # First file in each module has used items
                    used_functions = [f"process_{module_idx}_{file_idx}"]
                    used_classes = [f"Handler{module_idx}{file_idx}"]
                
                file_content, file_metadata = self.generate_python_file(
                    f"{module_name}.{file_name[:-3]}",  # Remove .py extension
                    structure,
                    used_functions,
                    used_classes
                )
                
                file_path = module_dir / file_name
                file_path.write_text(file_content)
                
                metadata['files'][str(file_path)] = file_metadata
                
                # Update expected cleanup counts
                metadata['expected_cleanup_items']['unused_imports'] += len(file_metadata['unused_imports'])
                metadata['expected_cleanup_items']['dead_functions'] += len(file_metadata['dead_functions'])
                metadata['expected_cleanup_items']['dead_classes'] += len(file_metadata['dead_classes'])
        
        # Create main entry point that uses some functions
        main_content = f'''#!/usr/bin/env python3
"""Main entry point for {project_name}."""

import sys
from src.{project_name}.module_0.file_0 import process_0_0, Handler00

def main():
    """Main function."""
    result = process_0_0()
    handler = Handler00()
    output = handler.method_1()
    print(f"Result: {{result}}, Output: {{output}}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''
        
        (project_dir / "main.py").write_text(main_content)
        
        # Generate requirements files
        requirements_content, unused_deps = self.generate_requirements_file(structure)
        (project_dir / "requirements.txt").write_text(requirements_content)
        
        pyproject_content, unused_pyproject_deps = self.generate_pyproject_toml(structure)
        (project_dir / "pyproject.toml").write_text(pyproject_content)
        
        metadata['unused_dependencies'] = list(set(unused_deps + unused_pyproject_deps))
        metadata['expected_cleanup_items']['unused_dependencies'] = len(metadata['unused_dependencies'])
        
        # Generate orphaned files
        orphaned_files = self.generate_orphaned_files(project_dir, structure.orphaned_files)
        metadata['orphaned_files'] = orphaned_files
        metadata['expected_cleanup_items']['orphaned_files'] = len(orphaned_files)
        
        # Create __init__.py files
        (src_dir / "__init__.py").write_text("")
        (src_dir.parent / "__init__.py").write_text("")
        (tests_dir / "__init__.py").write_text("")
        
        return metadata
    
    def create_project_from_config(self, 
                                 project_dir: Path, 
                                 environment_name: str = "standard") -> Dict[str, Any]:
        """Create a test project based on configuration."""
        
        if environment_name not in self.config.get('test_environments', {}):
            raise ValueError(f"Unknown environment: {environment_name}")
        
        env_config = self.config['test_environments'][environment_name]
        structure_config = env_config['project_structure']
        
        structure = ProjectStructure(
            files=structure_config.get('files', 10),
            modules=structure_config.get('modules', 3),
            unused_imports_per_file=structure_config.get('unused_imports_per_file', 2),
            dead_functions_per_file=structure_config.get('dead_functions_per_file', 1),
            orphaned_files=structure_config.get('orphaned_files', 2),
            unused_dependencies=structure_config.get('unused_dependencies', 2)
        )
        
        return self.create_test_project(project_dir, structure, f"test_project_{environment_name}")


# Convenience function for creating test projects
def create_test_project(project_dir: Path, 
                       environment: str = "standard",
                       config_file: Optional[str] = None) -> Dict[str, Any]:
    """Create a test project with the specified environment configuration."""
    
    if config_file is None:
        config_file = Path(__file__).parent / "test_config.json"
    
    generator = TestDataGenerator(str(config_file))
    return generator.create_project_from_config(project_dir, environment)


if __name__ == "__main__":
    # Example usage
    import tempfile
    import shutil
    
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        print(f"Creating test project in: {temp_dir}")
        
        metadata = create_test_project(temp_dir, "standard")
        
        print(f"Project created successfully!")
        print(f"Expected cleanup items:")
        for item_type, count in metadata['expected_cleanup_items'].items():
            print(f"  {item_type}: {count}")
        
        print(f"\nProject structure:")
        for file_path in metadata['files'].keys():
            print(f"  {file_path}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)