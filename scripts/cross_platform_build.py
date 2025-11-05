#!/usr/bin/env python3
"""
Cross-platform build and test script for Production Audio System
Supports Linux, macOS, and Windows development environments
"""

import os
import sys
import subprocess
import platform
import argparse
import shutil
from pathlib import Path
from typing import List, Dict, Optional

class CrossPlatformBuilder:
    """Cross-platform build and test manager"""
    
    def __init__(self):
        self.platform = platform.system().lower()
        self.project_root = Path(__file__).parent.parent
        self.venv_path = self._get_venv_path()
        self.python_exe = self._get_python_executable()
        
    def _get_venv_path(self) -> Path:
        """Get virtual environment path for current platform"""
        if self.platform == "windows":
            return self.project_root / "venv"
        else:
            return self.project_root / "venv"
    
    def _get_python_executable(self) -> Path:
        """Get Python executable path for current platform"""
        if self.platform == "windows":
            return self.venv_path / "Scripts" / "python.exe"
        else:
            return self.venv_path / "bin" / "python"
    
    def _run_command(self, cmd: List[str], cwd: Optional[Path] = None) -> int:
        """Run command and return exit code"""
        if cwd is None:
            cwd = self.project_root
            
        print(f"Running: {' '.join(cmd)}")
        print(f"Working directory: {cwd}")
        
        try:
            result = subprocess.run(cmd, cwd=cwd, check=False)
            return result.returncode
        except FileNotFoundError:
            print(f"Error: Command not found: {cmd[0]}")
            return 1
    
    def setup_environment(self) -> bool:
        """Set up development environment for current platform"""
        print(f"Setting up environment for {self.platform}...")
        
        if self.platform == "linux":
            return self._setup_linux()
        elif self.platform == "darwin":  # macOS
            return self._setup_macos()
        elif self.platform == "windows":
            return self._setup_windows()
        else:
            print(f"Unsupported platform: {self.platform}")
            return False
    
    def _setup_linux(self) -> bool:
        """Set up Linux development environment"""
        # Check if running in production environment
        if os.path.exists("/opt/production-audio-system"):
            print("Production environment detected, skipping setup")
            return True
            
        # Install system dependencies (requires sudo)
        deps_cmd = [
            "sudo", "apt-get", "install", "-y",
            "portaudio19-dev", "libasound2-dev", "python3-dev",
            "python3-pip", "python3-venv", "build-essential"
        ]
        
        if self._run_command(deps_cmd) != 0:
            print("Warning: Failed to install system dependencies")
            print("Please run manually: sudo apt-get install portaudio19-dev libasound2-dev python3-dev")
        
        return self._setup_python_env("requirements-linux.txt")
    
    def _setup_macos(self) -> bool:
        """Set up macOS development environment"""
        # Check if Homebrew is available
        if shutil.which("brew") is None:
            print("Homebrew not found. Please install from https://brew.sh")
            return False
        
        # Install dependencies via Homebrew
        deps_cmd = ["brew", "install", "portaudio", "python@3.10"]
        if self._run_command(deps_cmd) != 0:
            print("Warning: Failed to install Homebrew dependencies")
        
        return self._setup_python_env("requirements-macos.txt")
    
    def _setup_windows(self) -> bool:
        """Set up Windows development environment"""
        print("Windows setup - please ensure Python 3.10+ is installed")
        return self._setup_python_env("requirements-windows.txt")
    
    def _setup_python_env(self, requirements_file: str) -> bool:
        """Set up Python virtual environment"""
        # Create virtual environment
        if not self.venv_path.exists():
            print("Creating virtual environment...")
            cmd = [sys.executable, "-m", "venv", str(self.venv_path)]
            if self._run_command(cmd) != 0:
                print("Failed to create virtual environment")
                return False
        
        # Upgrade pip
        pip_cmd = [str(self.python_exe), "-m", "pip", "install", "--upgrade", "pip"]
        if self._run_command(pip_cmd) != 0:
            print("Failed to upgrade pip")
            return False
        
        # Install requirements
        req_file = self.project_root / requirements_file
        if req_file.exists():
            install_cmd = [str(self.python_exe), "-m", "pip", "install", "-r", str(req_file)]
            if self._run_command(install_cmd) != 0:
                print(f"Failed to install requirements from {requirements_file}")
                return False
        
        # Install development dependencies
        dev_deps = [
            "pytest", "pytest-cov", "pytest-asyncio",
            "black", "flake8", "mypy", "pre-commit"
        ]
        dev_cmd = [str(self.python_exe), "-m", "pip", "install"] + dev_deps
        if self._run_command(dev_cmd) != 0:
            print("Warning: Failed to install development dependencies")
        
        return True
    
    def run_tests(self, coverage: bool = True, verbose: bool = True) -> bool:
        """Run test suite"""
        print("Running tests...")
        
        if not self.python_exe.exists():
            print("Python executable not found. Please run setup first.")
            return False
        
        # Set environment variables
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.project_root / "src")
        
        # Build test command
        cmd = [str(self.python_exe), "-m", "pytest", "tests/"]
        
        if verbose:
            cmd.append("-v")
        
        if coverage:
            cmd.extend(["--cov=src", "--cov-report=html", "--cov-report=term"])
        
        # Run tests
        result = subprocess.run(cmd, cwd=self.project_root, env=env)
        return result.returncode == 0
    
    def run_linting(self) -> bool:
        """Run code linting and formatting checks"""
        print("Running linting...")
        
        if not self.python_exe.exists():
            print("Python executable not found. Please run setup first.")
            return False
        
        success = True
        
        # Run flake8
        print("Running flake8...")
        flake8_cmd = [str(self.python_exe), "-m", "flake8", "src/", "tests/"]
        if self._run_command(flake8_cmd) != 0:
            print("Flake8 linting failed")
            success = False
        
        # Run mypy
        print("Running mypy...")
        mypy_cmd = [str(self.python_exe), "-m", "mypy", "src/"]
        if self._run_command(mypy_cmd) != 0:
            print("MyPy type checking failed")
            success = False
        
        # Run black check
        print("Running black...")
        black_cmd = [str(self.python_exe), "-m", "black", "--check", "src/", "tests/"]
        if self._run_command(black_cmd) != 0:
            print("Black formatting check failed")
            success = False
        
        return success
    
    def format_code(self) -> bool:
        """Format code using black"""
        print("Formatting code...")
        
        if not self.python_exe.exists():
            print("Python executable not found. Please run setup first.")
            return False
        
        black_cmd = [str(self.python_exe), "-m", "black", "src/", "tests/"]
        return self._run_command(black_cmd) == 0
    
    def build_package(self) -> bool:
        """Build distribution package"""
        print("Building package...")
        
        if not self.python_exe.exists():
            print("Python executable not found. Please run setup first.")
            return False
        
        # Clean previous builds
        dist_dir = self.project_root / "dist"
        if dist_dir.exists():
            shutil.rmtree(dist_dir)
        
        build_dir = self.project_root / "build"
        if build_dir.exists():
            shutil.rmtree(build_dir)
        
        # Build package
        build_cmd = [str(self.python_exe), "-m", "build"]
        return self._run_command(build_cmd) == 0
    
    def run_dev_server(self) -> bool:
        """Run development server"""
        print("Starting development server...")
        
        if not self.python_exe.exists():
            print("Python executable not found. Please run setup first.")
            return False
        
        # Set environment variables
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.project_root / "src")
        env["FLASK_ENV"] = "development"
        env["FLASK_DEBUG"] = "1"
        
        # Determine config file
        config_file = f"config/development_{self.platform}.yaml"
        if self.platform == "darwin":
            config_file = "config/development_macos.yaml"
        
        env["AUDIO_CONFIG"] = config_file
        
        # Run server
        cmd = [str(self.python_exe), "-m", "src.main", "--config", config_file, "--debug"]
        result = subprocess.run(cmd, cwd=self.project_root, env=env)
        return result.returncode == 0
    
    def clean(self) -> bool:
        """Clean build artifacts"""
        print("Cleaning build artifacts...")
        
        patterns = [
            "**/__pycache__",
            "**/*.pyc",
            "**/*.pyo",
            "**/.pytest_cache",
            "**/.mypy_cache",
            "dist/",
            "build/",
            "*.egg-info/",
            ".coverage",
            "htmlcov/",
        ]
        
        for pattern in patterns:
            for path in self.project_root.glob(pattern):
                if path.is_dir():
                    shutil.rmtree(path)
                    print(f"Removed directory: {path}")
                elif path.is_file():
                    path.unlink()
                    print(f"Removed file: {path}")
        
        return True

def main():
    parser = argparse.ArgumentParser(description="Cross-platform build and test script")
    parser.add_argument("command", choices=[
        "setup", "test", "lint", "format", "build", "dev", "clean", "all"
    ], help="Command to run")
    parser.add_argument("--no-coverage", action="store_true", help="Skip coverage reporting")
    parser.add_argument("--quiet", action="store_true", help="Reduce output verbosity")
    
    args = parser.parse_args()
    
    builder = CrossPlatformBuilder()
    success = True
    
    if args.command == "setup":
        success = builder.setup_environment()
    elif args.command == "test":
        success = builder.run_tests(coverage=not args.no_coverage, verbose=not args.quiet)
    elif args.command == "lint":
        success = builder.run_linting()
    elif args.command == "format":
        success = builder.format_code()
    elif args.command == "build":
        success = builder.build_package()
    elif args.command == "dev":
        success = builder.run_dev_server()
    elif args.command == "clean":
        success = builder.clean()
    elif args.command == "all":
        success = (
            builder.setup_environment() and
            builder.run_linting() and
            builder.run_tests(coverage=not args.no_coverage, verbose=not args.quiet) and
            builder.build_package()
        )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()