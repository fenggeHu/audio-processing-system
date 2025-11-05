#!/bin/bash
# Production Audio System - macOS Development Environment Setup
# Supports macOS 11+ with CoreAudio integration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Production Audio System - macOS Development Setup${NC}"
echo "=================================================="

# Check macOS version
MACOS_VERSION=$(sw_vers -productVersion)
MACOS_MAJOR=$(echo $MACOS_VERSION | cut -d. -f1)
MACOS_MINOR=$(echo $MACOS_VERSION | cut -d. -f2)

echo "Detected macOS version: $MACOS_VERSION"

if [ "$MACOS_MAJOR" -lt 11 ]; then
    echo -e "${RED}macOS 11 or later is required${NC}"
    exit 1
fi

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo -e "${YELLOW}Installing Homebrew...${NC}"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Update Homebrew
echo -e "${YELLOW}Updating Homebrew...${NC}"
brew update

# Install system dependencies
echo -e "${YELLOW}Installing system dependencies...${NC}"
brew install \
    portaudio \
    python@3.10 \
    python@3.11 \
    python@3.12 \
    pkg-config \
    cmake \
    git \
    curl \
    wget

# Install development tools
echo -e "${YELLOW}Installing development tools...${NC}"
brew install \
    pyenv \
    pipenv \
    poetry \
    black \
    flake8 \
    mypy

# Install optional audio tools
echo -e "${YELLOW}Installing audio development tools...${NC}"
brew install \
    sox \
    ffmpeg \
    audacity \
    jack

# Check Python installation
PYTHON_PATH=$(brew --prefix python@3.10)/bin/python3
if [ ! -f "$PYTHON_PATH" ]; then
    echo -e "${RED}Python 3.10 installation failed${NC}"
    exit 1
fi

echo "Python path: $PYTHON_PATH"
echo "Python version: $($PYTHON_PATH --version)"

# Create development directory
DEV_DIR="$HOME/Development/production-audio-system"
echo -e "${YELLOW}Creating development directory: $DEV_DIR${NC}"
mkdir -p "$DEV_DIR"

# Set up Python virtual environment
echo -e "${YELLOW}Setting up Python virtual environment...${NC}"
cd "$DEV_DIR"
$PYTHON_PATH -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install development dependencies
echo -e "${YELLOW}Installing Python development dependencies...${NC}"
pip install -r requirements-macos.txt

# Install development tools
pip install \
    pytest \
    pytest-cov \
    pytest-asyncio \
    black \
    flake8 \
    mypy \
    pre-commit \
    jupyter \
    ipython

# Configure CoreAudio permissions
echo -e "${YELLOW}Configuring CoreAudio permissions...${NC}"
# Add current user to audio group (if it exists)
if dscl . -read /Groups/audio &> /dev/null; then
    sudo dscl . -append /Groups/audio GroupMembership $(whoami)
fi

# Create development configuration
echo -e "${YELLOW}Creating development configuration...${NC}"
cp config/development_macos.yaml config/local_config.yaml

# Set up pre-commit hooks
echo -e "${YELLOW}Setting up pre-commit hooks...${NC}"
pre-commit install

# Create development scripts
echo -e "${YELLOW}Creating development scripts...${NC}"
cat > run_dev.sh << 'EOF'
#!/bin/bash
# Development server runner for macOS

source venv/bin/activate
export PYTHONPATH="$(pwd)/src"
export AUDIO_CONFIG="config/development_macos.yaml"
export FLASK_ENV="development"
export FLASK_DEBUG=1

python -m src.main --config config/development_macos.yaml --debug
EOF

chmod +x run_dev.sh

cat > run_tests.sh << 'EOF'
#!/bin/bash
# Test runner for macOS development

source venv/bin/activate
export PYTHONPATH="$(pwd)/src"

# Run tests with coverage
pytest tests/ -v --cov=src --cov-report=html --cov-report=term

# Run type checking
mypy src/

# Run linting
flake8 src/ tests/

# Run formatting check
black --check src/ tests/
EOF

chmod +x run_tests.sh

# Create VS Code configuration
echo -e "${YELLOW}Creating VS Code configuration...${NC}"
mkdir -p .vscode

cat > .vscode/settings.json << EOF
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.linting.mypyEnabled": true,
    "python.formatting.provider": "black",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": [
        "tests"
    ],
    "files.exclude": {
        "**/__pycache__": true,
        "**/.pytest_cache": true,
        "**/venv": true,
        "**/.mypy_cache": true
    },
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    }
}
EOF

cat > .vscode/launch.json << EOF
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Audio System",
            "type": "python",
            "request": "launch",
            "module": "src.main",
            "args": ["--config", "config/development_macos.yaml", "--debug"],
            "console": "integratedTerminal",
            "env": {
                "PYTHONPATH": "\${workspaceFolder}/src",
                "AUDIO_CONFIG": "config/development_macos.yaml"
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
                "PYTHONPATH": "\${workspaceFolder}/src"
            }
        }
    ]
}
EOF

# Test audio system
echo -e "${YELLOW}Testing audio system...${NC}"
python -c "
import pyaudio
import sys

try:
    pa = pyaudio.PyAudio()
    print(f'PortAudio version: {pa.get_version_text()}')
    print(f'Available audio devices: {pa.get_device_count()}')
    
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        print(f'  Device {i}: {info[\"name\"]} ({info[\"maxInputChannels\"]} in, {info[\"maxOutputChannels\"]} out)')
    
    pa.terminate()
    print('Audio system test: PASSED')
except Exception as e:
    print(f'Audio system test: FAILED - {e}')
    sys.exit(1)
"

echo -e "${GREEN}macOS development environment setup completed!${NC}"
echo ""
echo "Development environment ready:"
echo "- Python virtual environment: $DEV_DIR/venv"
echo "- Development server: ./run_dev.sh"
echo "- Run tests: ./run_tests.sh"
echo "- VS Code configuration created"
echo "- Pre-commit hooks installed"
echo ""
echo "Next steps:"
echo "1. cd $DEV_DIR"
echo "2. source venv/bin/activate"
echo "3. ./run_dev.sh"