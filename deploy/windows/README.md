# Windows Development Environment Setup

This directory contains setup scripts and configuration for developing the Production Audio System on Windows 10/11.

## Quick Setup

1. **Ensure Python 3.10+ is installed:**
   - Download from https://python.org
   - Make sure to check "Add Python to PATH" during installation

2. **Run the setup script:**
   ```cmd
   setup_dev.bat
   ```

3. **Start development:**
   ```cmd
   cd %USERPROFILE%\Development\production-audio-system
   run_dev.bat
   ```

## Manual Setup

If you prefer manual setup or encounter issues:

### Prerequisites

1. **Python 3.10 or later**
   - Download from https://python.org
   - Verify installation: `python --version`

2. **Git (optional but recommended)**
   - Download from https://git-scm.com/

3. **Visual Studio Build Tools (for some packages)**
   - Download "Build Tools for Visual Studio" from Microsoft
   - Or install Visual Studio Community with C++ development tools

### Installation Steps

1. **Create development directory:**
   ```cmd
   mkdir %USERPROFILE%\Development\production-audio-system
   cd %USERPROFILE%\Development\production-audio-system
   ```

2. **Create virtual environment:**
   ```cmd
   python -m venv venv
   venv\Scripts\activate.bat
   ```

3. **Install dependencies:**
   ```cmd
   python -m pip install --upgrade pip
   pip install -r requirements-windows.txt
   pip install pytest pytest-cov black flake8 mypy
   ```

4. **Copy configuration:**
   ```cmd
   copy config\development_windows.yaml config\local_config.yaml
   ```

## Audio System Configuration

### WASAPI (Recommended)
Windows Audio Session API provides the best performance and lowest latency:
- Supported on Windows Vista and later
- Exclusive and shared modes available
- Low-latency audio processing

### DirectSound (Fallback)
Legacy audio API with broader compatibility:
- Supported on all Windows versions
- Higher latency but more stable
- Good for development and testing

### MME (Legacy)
Multimedia Extensions for basic audio:
- Highest compatibility
- Highest latency
- Use only if other APIs fail

## Development Tools

### VS Code Integration
The setup script creates VS Code configuration files:
- `.vscode/settings.json` - Editor settings and Python configuration
- `.vscode/launch.json` - Debug configurations
- `.vscode/tasks.json` - Build and test tasks

### PyCharm Integration
Use the development tools script to generate PyCharm configuration:
```cmd
python scripts\dev_tools.py pycharm
```

## Common Issues and Solutions

### PyAudio Installation Issues
If PyAudio installation fails:
```cmd
pip install pipwin
pipwin install pyaudio
```

Or use the binary wheel:
```cmd
pip install pyaudio-binary
```

### Permission Errors
If you encounter permission errors:
1. Run Command Prompt as Administrator
2. Or use PowerShell with execution policy:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```

### Audio Device Access
If audio devices are not accessible:
1. Check Windows audio settings
2. Ensure no other applications are using exclusive mode
3. Run the application as Administrator if needed

### Build Tools Missing
If compilation fails for native packages:
1. Install Visual Studio Build Tools
2. Or install Visual Studio Community with C++ tools
3. Restart command prompt after installation

## Testing Audio System

Test your audio setup:
```cmd
python -c "import pyaudio; pa = pyaudio.PyAudio(); print('Audio devices:', pa.get_device_count()); pa.terminate()"
```

List available audio devices:
```cmd
python -c "import pyaudio; pa = pyaudio.PyAudio(); [print(f'Device {i}: {pa.get_device_info_by_index(i)[\"name\"]}') for i in range(pa.get_device_count())]; pa.terminate()"
```

## Development Workflow

1. **Start development server:**
   ```cmd
   run_dev.bat
   ```

2. **Run tests:**
   ```cmd
   run_tests.bat
   ```

3. **Format code:**
   ```cmd
   venv\Scripts\activate.bat
   black src\ tests\
   ```

4. **Check code quality:**
   ```cmd
   venv\Scripts\activate.bat
   flake8 src\ tests\
   mypy src\
   ```

## Configuration Files

- `config/development_windows.yaml` - Main development configuration
- `config/local_config.yaml` - Local overrides (created by setup)

## Troubleshooting

### Virtual Environment Issues
If virtual environment activation fails:
```cmd
python -m venv --clear venv
venv\Scripts\activate.bat
```

### Package Installation Issues
If pip installation fails:
```cmd
python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -r requirements-windows.txt
```

### Audio Latency Issues
For better audio performance:
1. Use WASAPI exclusive mode
2. Reduce buffer sizes in configuration
3. Close other audio applications
4. Use ASIO drivers if available

### Windows Defender Issues
If Windows Defender blocks the application:
1. Add exception for the development directory
2. Add exception for Python executable
3. Temporarily disable real-time protection during development

## Performance Optimization

### Windows Audio Optimization
1. Disable Windows audio enhancements
2. Set audio devices to exclusive mode
3. Use high-performance power plan
4. Disable Windows audio ducking

### Development Performance
1. Use SSD for development directory
2. Exclude development directory from antivirus scans
3. Use Windows Terminal for better console performance
4. Enable Windows Subsystem for Linux (WSL) for Linux-like development