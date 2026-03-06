#!/bin/bash
# OpenClaw Keymaster - One-Command Installer
# Usage: sudo ./install-systemd.sh

set -e

USER_NAME="${SUDO_USER:-$USER}"
HOME_DIR="/home/$USER_NAME"
SERVICE_NAME="openclaw-keymaster"
SERVICE_FULL="${SERVICE_NAME}@${USER_NAME}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${CYAN}[STEP $1/6]${NC} $2"
}

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  This script must be run with sudo                      ║${NC}"
    echo -e "${RED}║  Usage: sudo ./install-systemd.sh                       ║${NC}"
    echo -e "${RED}╚═══════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi

echo -e "${CYAN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║     OpenClaw Keymaster Installer                         ║"
echo "║     Self-contained with isolated venv                     ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo "User: $USER_NAME"
echo "Home: $HOME_DIR"
echo ""

# Verify keymaster directory
KEYMASTER_DIR="$HOME_DIR/Keymaster/keymaster"
if [ ! -d "$KEYMASTER_DIR" ]; then
    KEYMASTER_DIR="$HOME_DIR/.openclaw/skills/keymaster"
    if [ ! -d "$KEYMASTER_DIR" ]; then
        log_error "Keymaster not found at $HOME_DIR/Keymaster/keymaster or $KEYMASTER_DIR"
        log_info "Please clone the repository first:"
        log_info "  cd ~ && git clone https://github.com/dommurphy155/Keymaster.git"
        exit 1
    fi
fi

log_step "1" "Checking Python availability..."
if ! command -v python3 &> /dev/null; then
    log_error "Python 3 not found. Please install Python 3.8+"
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
log_info "Python $PYTHON_VERSION found"

log_step "2" "Installing systemd service file..."
SERVICE_FILE="$KEYMASTER_DIR/systemd/openclaw-keymaster@.service"
if [ ! -f "$SERVICE_FILE" ]; then
    log_error "Service file not found: $SERVICE_FILE"
    exit 1
fi

cp "$SERVICE_FILE" "/etc/systemd/system/"
log_info "Service file installed"

log_step "3" "Creating unified management command..."
KEYMASTER_BIN="$KEYMASTER_DIR/keymaster"
if [ -f "$KEYMASTER_BIN" ]; then
    chmod +x "$KEYMASTER_BIN"
    ln -sf "$KEYMASTER_BIN" /usr/local/bin/keymaster 2>/dev/null || true
    log_info "'keymaster' command available"
else
    log_warn "Management script not found"
fi

log_step "4" "Reloading systemd..."
systemctl daemon-reload
log_info "Systemd reloaded"

log_step "5" "Enabling and starting service..."
systemctl enable "$SERVICE_FULL"

if systemctl start "$SERVICE_FULL"; then
    log_info "Service started"
else
    log_warn "Service may still be initializing"
fi

log_step "6" "Waiting for initialization..."
echo "  This may take 30-60 seconds on first run (creating venv + installing deps)..."

for i in {1..12}; do
    sleep 3
    if curl -s http://127.0.0.1:8787/health > /dev/null 2>&1; then
        break
    fi
    echo "  Still initializing... ($i/12)"
done

echo ""
echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              Installation Summary                         ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check final status
if systemctl is-active --quiet "$SERVICE_FULL" 2>/dev/null; then
    echo -e "${GREEN}✓ Service is RUNNING${NC}"
else
    echo -e "${YELLOW}⚠ Service status: CHECKING${NC}"
fi

if systemctl is-enabled --quiet "$SERVICE_FULL" 2>/dev/null; then
    echo -e "${GREEN}✓ Auto-start enabled${NC}"
fi

VENV_DIR="$HOME_DIR/.openclaw/keymaster_venv"
if [ -d "$VENV_DIR" ]; then
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

if curl -s http://127.0.0.1:8787/health > /tmp/health.json 2>/dev/null; then
    TOTAL=$(jq -r '.total_keys // 0' /tmp/health.json)
    AVAILABLE=$(jq -r '.available_keys // 0' /tmp/health.json)
    echo -e "${GREEN}✓ Proxy responding${NC} - $AVAILABLE/$TOTAL keys ready"
    rm -f /tmp/health.json
else
    echo -e "${YELLOW}⚠ Proxy not yet responding (may still be starting)${NC}"
fi

echo ""
echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                  Quick Commands                           ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "View logs:        keymaster logs"
echo "Check status:     keymaster status"
echo "View keys:        keymaster keys"
echo "Health check:   keymaster health"
echo ""
echo "Systemd:"
echo "  sudo systemctl status $SERVICE_FULL"
echo "  sudo systemctl restart $SERVICE_FULL"
echo ""
echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║            Installation Complete!                         ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
