#!/usr/bin/env python3
"""
Development tools and utilities for Production Audio System
Provides common development tasks and IDE integration helpers
"""

import os
import sys
import json
import yaml
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional

class DevTools:
    """Development tools and utilities"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.src_dir = self.project_root / "src"
        self.tests_dir = self.project_root / "tests"
        self.config_dir = self.project_root / "config"
    
    def generate_vscode_config(self) -> bool:
        """Generate VS Code configuration files"""
        print("Generating VS Code configuration...")
        
        vscode_dir = self.project_root / ".vscode"
        vscode_dir.mkdir(exist_ok=True)
        
        # Settings
        settings = {
            "python.defaultInterpreterPath": "./venv/bin/python",
            "python.linting.enabled": True,
            "python.linting.flake8Enabled": True,
            "python.linting.mypyEnabled": True,
            "python.formatting.provider": "black",
            "python.testing.pytestEnabled": True,
            "python.testing.pytestArgs": ["tests"],
            "files.exclude": {
                "**/__pycache__": True,
                "**/.pytest_cache": True,
                "**/venv": True,
                "**/.mypy_cache": True,
                "**/*.pyc": True
            },
            "editor.formatOnSave": True,
            "editor.codeActionsOnSave": {
                "source.organizeImports": True
            },
            "python.analysis.typeCheckingMode": "basic",
            "python.analysis.autoImportCompletions": True
        }
        
        # Platform-specific Python path
        if os.name == "nt":  # Windows
            settings["python.defaultInterpreterPath"] = "./venv/Scripts/python.exe"
        
        with open(vscode_dir / "settings.json", "w") as f:
            json.dump(settings, f, indent=4)
        
        # Launch configurations
        launch_config = {
            "version": "0.2.0",
            "configurations": [
                {
                    "name": "Python: Audio System",
                    "type": "python",
                    "request": "launch",
                    "module": "src.main",
                    "args": ["--config", "config/development_linux.yaml", "--debug"],
                    "console": "integratedTerminal",
                    "env": {
                        "PYTHONPATH": "${workspaceFolder}/src",
                        "AUDIO_CONFIG": "config/development_linux.yaml"
                    }
                },
                {
                    "name": "Python: Tests",
                    "type": "python",
                    "request": "launch",
                    "module": "pytest",
                    "args": ["tests/", "-v"],
                    "console": "integratedTerminal",
                    "env": {
                        "PYTHONPATH": "${workspaceFolder}/src"
                    }
                },
                {
                    "name": "Python: Single Test",
                    "type": "python",
                    "request": "launch",
                    "module": "pytest",
                    "args": ["${file}", "-v"],
                    "console": "integratedTerminal",
                    "env": {
                        "PYTHONPATH": "${workspaceFolder}/src"
                    }
                }
            ]
        }
        
        with open(vscode_dir / "launch.json", "w") as f:
            json.dump(launch_config, f, indent=4)
        
        # Tasks
        tasks_config = {
            "version": "2.0.0",
            "tasks": [
                {
                    "label": "Run Tests",
                    "type": "shell",
                    "command": "python",
                    "args": ["-m", "pytest", "tests/", "-v"],
                    "group": "test",
                    "presentation": {
                        "echo": True,
                        "reveal": "always",
                        "focus": False,
                        "panel": "shared"
                    },
                    "env": {
                        "PYTHONPATH": "${workspaceFolder}/src"
                    }
                },
                {
                    "label": "Format Code",
                    "type": "shell",
                    "command": "python",
                    "args": ["-m", "black", "src/", "tests/"],
                    "group": "build",
                    "presentation": {
                        "echo": True,
                        "reveal": "always",
                        "focus": False,
                        "panel": "shared"
                    }
                },
                {
                    "label": "Lint Code",
                    "type": "shell",
                    "command": "python",
                    "args": ["-m", "flake8", "src/", "tests/"],
                    "group": "build",
                    "presentation": {
                        "echo": True,
                        "reveal": "always",
                        "focus": False,
                        "panel": "shared"
                    }
                }
            ]
        }
        
        with open(vscode_dir / "tasks.json", "w") as f:
            json.dump(tasks_config, f, indent=4)
        
        print("VS Code configuration generated successfully")
        return True
    
    def generate_pycharm_config(self) -> bool:
        """Generate PyCharm configuration files"""
        print("Generating PyCharm configuration...")
        
        idea_dir = self.project_root / ".idea"
        idea_dir.mkdir(exist_ok=True)
        
        # Run configurations
        runconfigs_dir = idea_dir / "runConfigurations"
        runconfigs_dir.mkdir(exist_ok=True)
        
        # Main application run config
        main_config = """<component name="ProjectRunConfigurationManager">
  <configuration default="false" name="Audio System" type="PythonConfigurationType" factoryName="Python">
    <module name="production-audio-system" />
    <option name="INTERPRETER_OPTIONS" value="" />
    <option name="PARENT_ENVS" value="true" />
    <envs>
      <env name="PYTHONPATH" value="$PROJECT_DIR$/src" />
      <env name="AUDIO_CONFIG" value="config/development_linux.yaml" />
    </envs>
    <option name="SDK_HOME" value="$PROJECT_DIR$/venv/bin/python" />
    <option name="WORKING_DIRECTORY" value="$PROJECT_DIR$" />
    <option name="IS_MODULE_SDK" value="false" />
    <option name="ADD_CONTENT_ROOTS" value="true" />
    <option name="ADD_SOURCE_ROOTS" value="true" />
    <option name="SCRIPT_NAME" value="$PROJECT_DIR$/src/main.py" />
    <option name="PARAMETERS" value="--config config/development_linux.yaml --debug" />
    <option name="SHOW_COMMAND_LINE" value="false" />
    <option name="EMULATE_TERMINAL" value="false" />
    <option name="MODULE_MODE" value="true" />
    <option name="REDIRECT_INPUT" value="false" />
    <option name="INPUT_FILE" value="" />
    <method v="2" />
  </configuration>
</component>"""
        
        with open(runconfigs_dir / "Audio_System.xml", "w") as f:
            f.write(main_config)
        
        # Test run config
        test_config = """<component name="ProjectRunConfigurationManager">
  <configuration default="false" name="Tests" type="tests" factoryName="py.test">
    <module name="production-audio-system" />
    <option name="INTERPRETER_OPTIONS" value="" />
    <option name="PARENT_ENVS" value="true" />
    <envs>
      <env name="PYTHONPATH" value="$PROJECT_DIR$/src" />
    </envs>
    <option name="SDK_HOME" value="$PROJECT_DIR$/venv/bin/python" />
    <option name="WORKING_DIRECTORY" value="$PROJECT_DIR$" />
    <option name="IS_MODULE_SDK" value="false" />
    <option name="ADD_CONTENT_ROOTS" value="true" />
    <option name="ADD_SOURCE_ROOTS" value="true" />
    <option name="_new_keywords" value="&quot;&quot;" />
    <option name="_new_parameters" value="&quot;&quot;" />
    <option name="_new_additionalArguments" value="&quot;-v&quot;" />
    <option name="_new_target" value="&quot;$PROJECT_DIR$/tests&quot;" />
    <option name="_new_targetType" value="&quot;PATH&quot;" />
    <method v="2" />
  </configuration>
</component>"""
        
        with open(runconfigs_dir / "Tests.xml", "w") as f:
            f.write(test_config)
        
        print("PyCharm configuration generated successfully")
        return True
    
    def validate_config(self, config_file: str) -> bool:
        """Validate configuration file"""
        print(f"Validating configuration: {config_file}")
        
        config_path = self.config_dir / config_file
        if not config_path.exists():
            print(f"Configuration file not found: {config_path}")
            return False
        
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            
            # Basic validation
            required_sections = ["system", "audio", "processing", "web_interface", "logging"]
            for section in required_sections:
                if section not in config:
                    print(f"Missing required section: {section}")
                    return False
            
            # Validate audio configuration
            audio_config = config.get("audio", {})
            if "input" not in audio_config or "output" not in audio_config:
                print("Missing audio input/output configuration")
                return False
            
            print("Configuration validation passed")
            return True
            
        except yaml.YAMLError as e:
            print(f"YAML parsing error: {e}")
            return False
        except Exception as e:
            print(f"Configuration validation error: {e}")
            return False
    
    def generate_requirements(self) -> bool:
        """Generate platform-specific requirements files"""
        print("Generating requirements files...")
        
        # Base requirements
        base_requirements = [
            "numpy>=1.21.0",
            "scipy>=1.7.0",
            "PyYAML>=6.0",
            "flask>=2.0.0",
            "flask-socketio>=5.0.0",
            "python-socketio>=5.0.0",
            "matplotlib>=3.5.0",
            "plotly>=5.0.0",
            "dash>=2.0.0",
            "pandas>=1.3.0",
            "pydantic>=1.8.0",
            "click>=8.0.0",
            "colorlog>=6.0.0",
            "psutil>=5.8.0",
            "watchdog>=2.1.0",
        ]
        
        # Linux-specific requirements
        linux_requirements = base_requirements + [
            "PyAudio>=0.2.11",
            "webrtcvad>=2.0.10",
            "pyroomacoustics>=0.7.0",
            "soundfile>=0.10.0",
            "librosa>=0.9.0",
        ]
        
        # macOS-specific requirements
        macos_requirements = base_requirements + [
            "PyAudio>=0.2.11",
            "webrtcvad>=2.0.10",
            "pyroomacoustics>=0.7.0",
            "soundfile>=0.10.0",
            "librosa>=0.9.0",
            "pyobjc-framework-CoreAudio>=8.0",
        ]
        
        # Windows-specific requirements
        windows_requirements = base_requirements + [
            "pyaudio-binary>=0.2.11",
            "webrtcvad-wheels>=2.0.10",
            "soundfile>=0.10.0",
            "librosa>=0.9.0",
            "pywin32>=227",
        ]
        
        # Write requirements files
        with open(self.project_root / "requirements-linux.txt", "w") as f:
            f.write("\n".join(linux_requirements))
        
        with open(self.project_root / "requirements-macos.txt", "w") as f:
            f.write("\n".join(macos_requirements))
        
        with open(self.project_root / "requirements-windows.txt", "w") as f:
            f.write("\n".join(windows_requirements))
        
        print("Requirements files generated successfully")
        return True
    
    def check_dependencies(self) -> bool:
        """Check if all dependencies are installed"""
        print("Checking dependencies...")
        
        try:
            import pkg_resources
            
            # Read requirements for current platform
            platform_map = {
                "linux": "requirements-linux.txt",
                "darwin": "requirements-macos.txt",
                "win32": "requirements-windows.txt"
            }
            
            req_file = platform_map.get(sys.platform, "requirements-linux.txt")
            req_path = self.project_root / req_file
            
            if not req_path.exists():
                print(f"Requirements file not found: {req_path}")
                return False
            
            with open(req_path, "r") as f:
                requirements = f.read().splitlines()
            
            missing = []
            for requirement in requirements:
                if requirement.strip() and not requirement.startswith("#"):
                    try:
                        pkg_resources.require(requirement)
                    except pkg_resources.DistributionNotFound:
                        missing.append(requirement)
                    except pkg_resources.VersionConflict as e:
                        print(f"Version conflict: {e}")
                        missing.append(requirement)
            
            if missing:
                print("Missing dependencies:")
                for dep in missing:
                    print(f"  - {dep}")
                return False
            
            print("All dependencies are installed")
            return True
            
        except ImportError:
            print("pkg_resources not available")
            return False
    
    def create_dev_scripts(self) -> bool:
        """Create development scripts for current platform"""
        print("Creating development scripts...")
        
        if os.name == "nt":  # Windows
            # run_dev.bat
            with open(self.project_root / "run_dev.bat", "w") as f:
                f.write("""@echo off
call venv\\Scripts\\activate.bat
set PYTHONPATH=%cd%\\src
set AUDIO_CONFIG=config\\development_windows.yaml
set FLASK_ENV=development
set FLASK_DEBUG=1
python -m src.main --config config\\development_windows.yaml --debug
""")
            
            # run_tests.bat
            with open(self.project_root / "run_tests.bat", "w") as f:
                f.write("""@echo off
call venv\\Scripts\\activate.bat
set PYTHONPATH=%cd%\\src
pytest tests\\ -v --cov=src --cov-report=html --cov-report=term
""")
        else:  # Linux/macOS
            # run_dev.sh
            with open(self.project_root / "run_dev.sh", "w") as f:
                f.write("""#!/bin/bash
source venv/bin/activate
export PYTHONPATH="$(pwd)/src"
export AUDIO_CONFIG="config/development_linux.yaml"
export FLASK_ENV="development"
export FLASK_DEBUG=1
python -m src.main --config config/development_linux.yaml --debug
""")
            
            # run_tests.sh
            with open(self.project_root / "run_tests.sh", "w") as f:
                f.write("""#!/bin/bash
source venv/bin/activate
export PYTHONPATH="$(pwd)/src"
pytest tests/ -v --cov=src --cov-report=html --cov-report=term
""")
            
            # Make scripts executable
            os.chmod(self.project_root / "run_dev.sh", 0o755)
            os.chmod(self.project_root / "run_tests.sh", 0o755)
        
        print("Development scripts created successfully")
        return True

def main():
    parser = argparse.ArgumentParser(description="Development tools and utilities")
    parser.add_argument("command", choices=[
        "vscode", "pycharm", "validate", "requirements", "deps", "scripts", "all"
    ], help="Command to run")
    parser.add_argument("--config", help="Configuration file to validate")
    
    args = parser.parse_args()
    
    tools = DevTools()
    success = True
    
    if args.command == "vscode":
        success = tools.generate_vscode_config()
    elif args.command == "pycharm":
        success = tools.generate_pycharm_config()
    elif args.command == "validate":
        config_file = args.config or "development_linux.yaml"
        success = tools.validate_config(config_file)
    elif args.command == "requirements":
        success = tools.generate_requirements()
    elif args.command == "deps":
        success = tools.check_dependencies()
    elif args.command == "scripts":
        success = tools.create_dev_scripts()
    elif args.command == "all":
        success = (
            tools.generate_requirements() and
            tools.generate_vscode_config() and
            tools.generate_pycharm_config() and
            tools.create_dev_scripts()
        )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()