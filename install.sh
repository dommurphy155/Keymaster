#!/bin/bash
#
# OpenClaw Keymaster Auto-Installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/dommurphy155/Keymaster/main/install.sh | bash
#   OR
#   bash install.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Config
REPO_URL="https://github.com/dommurphy155/Keymaster.git"
INSTALL_DIR="$HOME/.openclaw/skills/keymaster"
PROXY_PORT=8787

# Logging
log() { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }

# Check if running as root (we don't want that)
if [ "$EUID" -eq 0 ]; then
   error "Please don't run as root"
   exit 1
fi

log "OpenClaw Keymaster Auto-Installer"
echo "=================================="
echo ""

# Check prerequisites
log "Checking prerequisites..."

# Check Python
if ! command -v python3 &> /dev/null; then
    error "Python 3 is required but not installed"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d ' ' -f 2 | cut -d '.' -f 1-2)
log "Python version: $PYTHON_VERSION"

# Check if OpenClaw exists
if [ ! -d "$HOME/.openclaw" ]; then
    warn "OpenClaw not found at $HOME/.openclaw"
    warn "Please install OpenClaw first: https://openclaw.dev"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Install Python dependencies
log "Installing Python dependencies..."

pip3 install --user fastapi uvicorn httpx 2>/dev/null || {
    warn "pip install failed, trying with --break-system-packages..."
    pip3 install fastapi uvicorn httpx --break-system-packages 2>/dev/null || {
        error "Failed to install dependencies"
        exit 1
    }
}

success "Dependencies installed"

# Clone or update repository
log "Installing Keymaster..."

if [ -d "$INSTALL_DIR" ]; then
    log "Keymaster already exists, updating..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    log "Cloning Keymaster repository..."
    mkdir -p "$HOME/.openclaw/skills"
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

success "Keymaster installed at $INSTALL_DIR"

# Check if auth-profiles.json exists
AUTH_FILE="$HOME/.openclaw/agents/main/agent/auth-profiles.json"
if [ ! -f "$AUTH_FILE" ]; then
    warn "auth-profiles.json not found!"
    warn "Please configure your NVIDIA API keys first."
    echo ""
    echo "See: $INSTALL_DIR/SETUP.md for instructions"
    echo ""
    read -p "Continue with setup? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Configure OpenClaw to use proxy
log "Configuring OpenClaw..."

python3 "$INSTALL_DIR/scripts/configure_openclaw.py" --enable

success "OpenClaw configured to use proxy"

# Install systemd service (if systemd is available)
if command -v systemctl &> /dev/null; then
    log "Installing systemd service..."

    SERVICE_FILE="$INSTALL_DIR/systemd/openclaw-proxy.service"
    USER_SERVICE_DIR="$HOME/.config/systemd/user"

    # Create user service directory
    mkdir -p "$USER_SERVICE_DIR"

    # Replace template variables
    sed -e "s|%USER%|$USER|g" \
        -e "s|%HOME%|$HOME|g" \
        -e "s|%PYTHON%|$(which python3)|g" \
        "$SERVICE_FILE" > "$USER_SERVICE_DIR/openclaw-proxy.service"

    # Reload systemd
    systemctl --user daemon-reload

    # Enable service
    systemctl --user enable openclaw-proxy.service

    success "Systemd service installed"

    # Start service
    log "Starting proxy service..."
    systemctl --user start openclaw-proxy.service

    # Wait for service to start
    sleep 2

    # Check status
    if systemctl --user is-active --quiet openclaw-proxy.service; then
        success "Proxy service is running!"
    else
        error "Failed to start proxy service"
        systemctl --user status openclaw-proxy.service
        exit 1
    fi
else
    warn "systemd not available, using manual start..."

    # Start proxy manually
    log "Starting proxy..."
    python3 "$INSTALL_DIR/scripts/start_proxy.py" --daemon

    # Add to .bashrc for auto-start
    if ! grep -q "keymaster/scripts/start_proxy.py" "$HOME/.bashrc" 2>/dev/null; then
        echo "" >> "$HOME/.bashrc"
        echo "# Start OpenClaw Keymaster Proxy" >> "$HOME/.bashrc"
        echo "python3 $INSTALL_DIR/scripts/start_proxy.py --daemon 2>/dev/null || true" >> "$HOME/.bashrc"
        success "Added auto-start to .bashrc"
    fi
fi

# Verify installation
echo ""
log "Verifying installation..."

# Check proxy health
for i in 1 2 3; do
    if curl -s http://127.0.0.1:$PROXY_PORT/health > /dev/null 2>&1; then
        success "Proxy is responding on port $PROXY_PORT"
        break
    fi
    if [ $i -eq 3 ]; then
        error "Proxy health check failed"
        warn "Check logs: systemctl --user status openclaw-proxy"
    fi
    sleep 1
done

# Show status
if command -v systemctl &> /dev/null; then
    echo ""
    log "Service status:"
    systemctl --user status openclaw-proxy.service --no-pager -l
fi

# Final message
echo ""
echo "=================================="
success "Keymaster installation complete!"
echo ""
echo "Commands:"
echo "  systemctl --user status openclaw-proxy    # Check status"
echo "  systemctl --user stop openclaw-proxy      # Stop proxy"
echo "  systemctl --user start openclaw-proxy     # Start proxy"
echo "  systemctl --user restart openclaw-proxy   # Restart proxy"
echo ""
echo "Proxy URL: http://127.0.0.1:$PROXY_PORT"
echo ""
success "OpenClaw will now automatically rotate through your API keys!"
echo ""
echo "Try it:"
echo "  openclaw 'Create a complex dashboard'"
