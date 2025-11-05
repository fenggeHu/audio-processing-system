"""
Cross-Compilation Setup for Embedded Targets

Support for ARM64 and x86_64 embedded target platforms.
"""

import os
import sys
import platform
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class CrossCompileTarget:
    """Cross-compilation target configuration."""
    name: str
    arch: str
    toolchain_prefix: str
    sysroot: Optional[str] = None
    extra_cflags: List[str] = None
    extra_ldflags: List[str] = None
    python_config: Optional[str] = None
    
    def __post_init__(self):
        if self.extra_cflags is None:
            self.extra_cflags = []
        if self.extra_ldflags is None:
            self.extra_ldflags = []


class CrossCompileManager:
    """Manager for cross-compilation setup."""
    
    def __init__(self):
        self.targets = self._define_targets()
        self.host_platform = self._detect_host_platform()
    
    def _detect_host_platform(self) -> str:
        """Detect host platform for cross-compilation."""
        system = platform.system().lower()
        machine = platform.machine().lower()
        return f"{system}-{machine}"
    
    def _define_targets(self) -> Dict[str, CrossCompileTarget]:
        """Define supported cross-compilation targets."""
        return {
            "linux-arm64": CrossCompileTarget(
                name="linux-arm64",
                arch="aarch64",
                toolchain_prefix="aarch64-linux-gnu-",
                extra_cflags=[
                    "-march=armv8-a",
                    "-mtune=cortex-a72",
                    "-mfpu=neon-fp-armv8",
                    "-O3",
                    "-ffast-math",
                    "-DARM_NEON",
                ],
                extra_ldflags=[
                    "-Wl,--as-needed",
                    "-Wl,--gc-sections",
                ],
            ),
            
            "linux-arm32": CrossCompileTarget(
                name="linux-arm32",
                arch="armv7l",
                toolchain_prefix="arm-linux-gnueabihf-",
                extra_cflags=[
                    "-march=armv7-a",
                    "-mtune=cortex-a7",
                    "-mfpu=neon",
                    "-mfloat-abi=hard",
                    "-O3",
                    "-ffast-math",
                    "-DARM_NEON",
                ],
                extra_ldflags=[
                    "-Wl,--as-needed",
                    "-Wl,--gc-sections",
                ],
            ),
            
            "linux-x86_64": CrossCompileTarget(
                name="linux-x86_64",
                arch="x86_64",
                toolchain_prefix="x86_64-linux-gnu-",
                extra_cflags=[
                    "-march=x86-64",
                    "-mtune=generic",
                    "-msse4.2",
                    "-mavx2",
                    "-O3",
                    "-ffast-math",
                ],
                extra_ldflags=[
                    "-Wl,--as-needed",
                    "-Wl,--gc-sections",
                ],
            ),
            
            "raspberry-pi-4": CrossCompileTarget(
                name="raspberry-pi-4",
                arch="aarch64",
                toolchain_prefix="aarch64-rpi4-linux-gnu-",
                extra_cflags=[
                    "-march=armv8-a+crc",
                    "-mtune=cortex-a72",
                    "-mfpu=neon-fp-armv8",
                    "-O3",
                    "-ffast-math",
                    "-DARM_NEON",
                    "-DRASPBERRY_PI",
                ],
                extra_ldflags=[
                    "-Wl,--as-needed",
                    "-Wl,--gc-sections",
                ],
            ),
        }
    
    def setup_target(self, target_name: str) -> bool:
        """Setup cross-compilation for a specific target."""
        if target_name not in self.targets:
            print(f"Error: Unknown target '{target_name}'")
            print(f"Available targets: {list(self.targets.keys())}")
            return False
        
        target = self.targets[target_name]
        
        print(f"Setting up cross-compilation for {target.name}...")
        
        # Check toolchain availability
        if not self._check_toolchain(target):
            print(f"Error: Toolchain not found for {target.name}")
            return False
        
        # Setup environment variables
        self._setup_environment(target)
        
        # Create cross-compilation configuration
        self._create_cross_config(target)
        
        print(f"Cross-compilation setup complete for {target.name}")
        return True
    
    def _check_toolchain(self, target: CrossCompileTarget) -> bool:
        """Check if the required toolchain is available."""
        gcc_command = f"{target.toolchain_prefix}gcc"
        
        try:
            result = subprocess.run(
                [gcc_command, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def _setup_environment(self, target: CrossCompileTarget) -> None:
        """Setup environment variables for cross-compilation."""
        env_vars = {
            "CC": f"{target.toolchain_prefix}gcc",
            "CXX": f"{target.toolchain_prefix}g++",
            "AR": f"{target.toolchain_prefix}ar",
            "STRIP": f"{target.toolchain_prefix}strip",
            "RANLIB": f"{target.toolchain_prefix}ranlib",
            "CFLAGS": " ".join(target.extra_cflags),
            "CXXFLAGS": " ".join(target.extra_cflags),
            "LDFLAGS": " ".join(target.extra_ldflags),
        }
        
        if target.sysroot:
            env_vars["SYSROOT"] = target.sysroot
            env_vars["CFLAGS"] += f" --sysroot={target.sysroot}"
            env_vars["CXXFLAGS"] += f" --sysroot={target.sysroot}"
            env_vars["LDFLAGS"] += f" --sysroot={target.sysroot}"
        
        # Set environment variables
        for key, value in env_vars.items():
            os.environ[key] = value
            print(f"  {key}={value}")
    
    def _create_cross_config(self, target: CrossCompileTarget) -> None:
        """Create cross-compilation configuration files."""
        # Create setup.cfg for distutils
        setup_cfg_content = f"""[build_ext]
include_dirs = /usr/{target.toolchain_prefix.rstrip('-')}/include
library_dirs = /usr/{target.toolchain_prefix.rstrip('-')}/lib

[build]
build_base = build/{target.name}

[install]
install_base = dist/{target.name}
"""
        
        with open("setup.cfg", "w") as f:
            f.write(setup_cfg_content)
        
        # Create cross-compilation script
        cross_script_content = f"""#!/bin/bash
# Cross-compilation script for {target.name}

export CC="{target.toolchain_prefix}gcc"
export CXX="{target.toolchain_prefix}g++"
export AR="{target.toolchain_prefix}ar"
export STRIP="{target.toolchain_prefix}strip"
export RANLIB="{target.toolchain_prefix}ranlib"
export CFLAGS="{' '.join(target.extra_cflags)}"
export CXXFLAGS="{' '.join(target.extra_cflags)}"
export LDFLAGS="{' '.join(target.extra_ldflags)}"

{f'export SYSROOT="{target.sysroot}"' if target.sysroot else ''}
{f'export CFLAGS="$CFLAGS --sysroot={target.sysroot}"' if target.sysroot else ''}
{f'export CXXFLAGS="$CXXFLAGS --sysroot={target.sysroot}"' if target.sysroot else ''}
{f'export LDFLAGS="$LDFLAGS --sysroot={target.sysroot}"' if target.sysroot else ''}

echo "Cross-compiling for {target.name}..."
python setup.py build_ext --inplace
python setup.py bdist_wheel --plat-name {target.name.replace('-', '_')}
"""
        
        script_path = Path(f"cross_compile_{target.name.replace('-', '_')}.sh")
        with open(script_path, "w") as f:
            f.write(cross_script_content)
        
        # Make script executable
        script_path.chmod(0o755)
        
        print(f"  Created cross-compilation script: {script_path}")
    
    def install_toolchains(self) -> None:
        """Install cross-compilation toolchains."""
        print("Installing cross-compilation toolchains...")
        
        # Detect package manager and install toolchains
        if self._command_exists("apt-get"):
            self._install_debian_toolchains()
        elif self._command_exists("yum"):
            self._install_redhat_toolchains()
        elif self._command_exists("brew"):
            self._install_macos_toolchains()
        else:
            print("Warning: Could not detect package manager for toolchain installation")
            self._print_manual_installation_instructions()
    
    def _command_exists(self, command: str) -> bool:
        """Check if a command exists in PATH."""
        try:
            subprocess.run([command, "--version"], capture_output=True, timeout=5)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def _install_debian_toolchains(self) -> None:
        """Install toolchains on Debian/Ubuntu systems."""
        packages = [
            "gcc-aarch64-linux-gnu",
            "g++-aarch64-linux-gnu",
            "gcc-arm-linux-gnueabihf",
            "g++-arm-linux-gnueabihf",
            "libc6-dev-arm64-cross",
            "libc6-dev-armhf-cross",
        ]
        
        cmd = ["sudo", "apt-get", "install", "-y"] + packages
        print(f"Running: {' '.join(cmd)}")
        
        try:
            subprocess.run(cmd, check=True)
            print("Toolchains installed successfully")
        except subprocess.CalledProcessError as e:
            print(f"Error installing toolchains: {e}")
    
    def _install_redhat_toolchains(self) -> None:
        """Install toolchains on RedHat/CentOS systems."""
        packages = [
            "gcc-aarch64-linux-gnu",
            "gcc-c++-aarch64-linux-gnu",
            "gcc-arm-linux-gnu",
            "gcc-c++-arm-linux-gnu",
        ]
        
        cmd = ["sudo", "yum", "install", "-y"] + packages
        print(f"Running: {' '.join(cmd)}")
        
        try:
            subprocess.run(cmd, check=True)
            print("Toolchains installed successfully")
        except subprocess.CalledProcessError as e:
            print(f"Error installing toolchains: {e}")
    
    def _install_macos_toolchains(self) -> None:
        """Install toolchains on macOS systems."""
        # macOS cross-compilation is more complex and typically requires custom toolchains
        print("macOS cross-compilation setup:")
        print("1. Install Docker for containerized cross-compilation")
        print("2. Use crosstool-ng for custom toolchain building")
        print("3. Consider using multiarch/crossbuild Docker images")
    
    def _print_manual_installation_instructions(self) -> None:
        """Print manual installation instructions."""
        print("\nManual toolchain installation instructions:")
        print("\nFor Debian/Ubuntu:")
        print("  sudo apt-get install gcc-aarch64-linux-gnu g++-aarch64-linux-gnu")
        print("  sudo apt-get install gcc-arm-linux-gnueabihf g++-arm-linux-gnueabihf")
        print("\nFor RedHat/CentOS:")
        print("  sudo yum install gcc-aarch64-linux-gnu gcc-c++-aarch64-linux-gnu")
        print("  sudo yum install gcc-arm-linux-gnu gcc-c++-arm-linux-gnu")
        print("\nFor other systems:")
        print("  Install appropriate cross-compilation toolchains for your distribution")


def main():
    """Main entry point for cross-compilation setup."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Cross-compilation setup for embedded targets")
    parser.add_argument("--target", help="Target platform for cross-compilation")
    parser.add_argument("--list-targets", action="store_true", help="List available targets")
    parser.add_argument("--install-toolchains", action="store_true", help="Install cross-compilation toolchains")
    
    args = parser.parse_args()
    
    manager = CrossCompileManager()
    
    if args.list_targets:
        print("Available cross-compilation targets:")
        for name, target in manager.targets.items():
            print(f"  {name}: {target.arch} ({target.toolchain_prefix})")
        return
    
    if args.install_toolchains:
        manager.install_toolchains()
        return
    
    if args.target:
        success = manager.setup_target(args.target)
        sys.exit(0 if success else 1)
    
    # Interactive mode
    print("Cross-compilation setup for Production Audio System")
    print(f"Host platform: {manager.host_platform}")
    print("\nAvailable targets:")
    for name in manager.targets.keys():
        print(f"  {name}")
    
    target_name = input("\nEnter target name (or 'quit' to exit): ").strip()
    
    if target_name.lower() in ['quit', 'exit', 'q']:
        return
    
    if target_name:
        success = manager.setup_target(target_name)
        if success:
            print(f"\nTo cross-compile, run:")
            print(f"  ./cross_compile_{target_name.replace('-', '_')}.sh")


if __name__ == "__main__":
    main()