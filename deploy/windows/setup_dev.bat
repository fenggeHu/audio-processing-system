@echo off
REM Production Audio System - Windows Development Environment Setup
REM Supports Windows 10/11 with WASAPI integration

echo Production Audio System - Windows Development Setup
echo ===================================================

REM Check Windows version
for /f "tokens=4-5 delims=. " %%i in ('ver') do set VERSION=%%i.%%j
echo Detected Windows version: %VERSION%

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10 or later from https://python.org
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo Python version: %PYTHON_VERSION%

REM Check if pip is available
pip --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip is not available
    echo Please ensure pip is installed with Python
    pause
    exit /b 1
)

REM Check if Git is installed
git --version >nul 2>&1
if errorlevel 1 (
    echo WARNING: Git is not installed
    echo Please install Git from https://git-scm.com/
)

REM Create development directory
set DEV_DIR=%USERPROFILE%\Development\production-audio-system
echo Creating development directory: %DEV_DIR%
if not exist "%DEV_DIR%" mkdir "%DEV_DIR%"

REM Change to development directory
cd /d "%DEV_DIR%"

REM Create Python virtual environment
echo Setting up Python virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip setuptools wheel

REM Install Windows-specific dependencies
echo Installing Windows audio dependencies...
pip install pyaudio-binary
if errorlevel 1 (
    echo Trying alternative PyAudio installation...
    pip install pipwin
    pipwin install pyaudio
)

REM Install development dependencies
echo Installing Python development dependencies...
pip install -r requirements-windows.txt

REM Install development tools
echo Installing development tools...
pip install pytest pytest-cov pytest-asyncio black flake8 mypy pre-commit jupyter ipython

REM Create development configuration
echo Creating development configuration...
copy config\development_windows.yaml config\local_config.yaml

REM Create development scripts
echo Creating development scripts...

REM Create run_dev.bat
echo @echo off > run_dev.bat
echo call venv\Scripts\activate.bat >> run_dev.bat
echo set PYTHONPATH=%cd%\src >> run_dev.bat
echo set AUDIO_CONFIG=config\development_windows.yaml >> run_dev.bat
echo set FLASK_ENV=development >> run_dev.bat
echo set FLASK_DEBUG=1 >> run_dev.bat
echo python -m src.main --config config\development_windows.yaml --debug >> run_dev.bat

REM Create run_tests.bat
echo @echo off > run_tests.bat
echo call venv\Scripts\activate.bat >> run_tests.bat
echo set PYTHONPATH=%cd%\src >> run_tests.bat
echo echo Running tests with coverage... >> run_tests.bat
echo pytest tests\ -v --cov=src --cov-report=html --cov-report=term >> run_tests.bat
echo echo Running type checking... >> run_tests.bat
echo mypy src\ >> run_tests.bat
echo echo Running linting... >> run_tests.bat
echo flake8 src\ tests\ >> run_tests.bat
echo echo Running formatting check... >> run_tests.bat
echo black --check src\ tests\ >> run_tests.bat

REM Create VS Code configuration
echo Creating VS Code configuration...
if not exist ".vscode" mkdir ".vscode"

REM Create settings.json
echo { > .vscode\settings.json
echo     "python.defaultInterpreterPath": "./venv/Scripts/python.exe", >> .vscode\settings.json
echo     "python.linting.enabled": true, >> .vscode\settings.json
echo     "python.linting.flake8Enabled": true, >> .vscode\settings.json
echo     "python.linting.mypyEnabled": true, >> .vscode\settings.json
echo     "python.formatting.provider": "black", >> .vscode\settings.json
echo     "python.testing.pytestEnabled": true, >> .vscode\settings.json
echo     "python.testing.pytestArgs": [ >> .vscode\settings.json
echo         "tests" >> .vscode\settings.json
echo     ], >> .vscode\settings.json
echo     "files.exclude": { >> .vscode\settings.json
echo         "**/__pycache__": true, >> .vscode\settings.json
echo         "**/.pytest_cache": true, >> .vscode\settings.json
echo         "**/venv": true, >> .vscode\settings.json
echo         "**/.mypy_cache": true >> .vscode\settings.json
echo     }, >> .vscode\settings.json
echo     "editor.formatOnSave": true, >> .vscode\settings.json
echo     "editor.codeActionsOnSave": { >> .vscode\settings.json
echo         "source.organizeImports": true >> .vscode\settings.json
echo     } >> .vscode\settings.json
echo } >> .vscode\settings.json

REM Create launch.json
echo { > .vscode\launch.json
echo     "version": "0.2.0", >> .vscode\launch.json
echo     "configurations": [ >> .vscode\launch.json
echo         { >> .vscode\launch.json
echo             "name": "Python: Audio System", >> .vscode\launch.json
echo             "type": "python", >> .vscode\launch.json
echo             "request": "launch", >> .vscode\launch.json
echo             "module": "src.main", >> .vscode\launch.json
echo             "args": ["--config", "config/development_windows.yaml", "--debug"], >> .vscode\launch.json
echo             "console": "integratedTerminal", >> .vscode\launch.json
echo             "env": { >> .vscode\launch.json
echo                 "PYTHONPATH": "${workspaceFolder}/src", >> .vscode\launch.json
echo                 "AUDIO_CONFIG": "config/development_windows.yaml" >> .vscode\launch.json
echo             } >> .vscode\launch.json
echo         }, >> .vscode\launch.json
echo         { >> .vscode\launch.json
echo             "name": "Python: Tests", >> .vscode\launch.json
echo             "type": "python", >> .vscode\launch.json
echo             "request": "launch", >> .vscode\launch.json
echo             "module": "pytest", >> .vscode\launch.json
echo             "args": ["tests/", "-v"], >> .vscode\launch.json
echo             "console": "integratedTerminal", >> .vscode\launch.json
echo             "env": { >> .vscode\launch.json
echo                 "PYTHONPATH": "${workspaceFolder}/src" >> .vscode\launch.json
echo             } >> .vscode\launch.json
echo         } >> .vscode\launch.json
echo     ] >> .vscode\launch.json
echo } >> .vscode\launch.json

REM Test audio system
echo Testing audio system...
python -c "import pyaudio; pa = pyaudio.PyAudio(); print(f'PortAudio version: {pa.get_version_text()}'); print(f'Available audio devices: {pa.get_device_count()}'); [print(f'  Device {i}: {pa.get_device_info_by_index(i)[\"name\"]} ({pa.get_device_info_by_index(i)[\"maxInputChannels\"]} in, {pa.get_device_info_by_index(i)[\"maxOutputChannels\"]} out)') for i in range(pa.get_device_count())]; pa.terminate(); print('Audio system test: PASSED')"

if errorlevel 1 (
    echo WARNING: Audio system test failed
    echo Please check your audio drivers and PyAudio installation
)

echo.
echo Windows development environment setup completed!
echo.
echo Development environment ready:
echo - Python virtual environment: %DEV_DIR%\venv
echo - Development server: run_dev.bat
echo - Run tests: run_tests.bat
echo - VS Code configuration created
echo.
echo Next steps:
echo 1. cd %DEV_DIR%
echo 2. run_dev.bat
echo.
pause