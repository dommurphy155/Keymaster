#!/bin/bash
# Install OpenClaw Keymaster as a unified systemd service with isolated venv
# Usage: sudo ./install-systemd.sh

set -e

USER_NAME="${SUDO_USER:-$USER}"
HOME_DIR="/home/$USER_NAME"
SERVICE_NAME="openclaw-keymaster"
SERVICE_FULL="${SERVICE_NAME}@${USER_NAME}"

if [ "$EUID" -ne 0 ]; then
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║  This script must be run with sudo                      ║"
    echo "║  Usage: sudo ./install-systemd.sh                       ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    exit 1
fi

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║     OpenClaw Keymaster Systemd Installer                 ║"
echo "║     (Self-contained with isolated venv)                  ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
echo "User: $USER_NAME"
echo "Home: $HOME_DIR"
echo ""

# Verify keymaster directory exists
KEYMASTER_DIR="$HOME_DIR/.openclaw/skills/keymaster"
if [ ! -d "$KEYMASTER_DIR" ]; then
    echo "✗ Keymaster not found at $KEYMASTER_DIR"
    echo "  Please ensure keymaster is installed in ~/.openclaw/skills/keymaster"
    exit 1
fi

echo "[1/5] Checking Python availability..."
if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 not found. Please install Python 3.8+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "  ✓ Python $PYTHON_VERSION found"

echo ""
echo "[2/5] Installing service file..."
SERVICE_FILE="$KEYMASTER_DIR/systemd/openclaw-keymaster.service"
if [ ! -f "$SERVICE_FILE" ]; then
    echo "✗ Service file not found: $SERVICE_FILE"
    exit 1
fi

cp "$SERVICE_FILE" "/etc/systemd/system/"
echo "  ✓ Service file installed"

# Reload systemd
echo ""
echo "[3/5] Reloading systemd..."
systemctl daemon-reload
echo "  ✓ Systemd reloaded"

echo ""
echo "[4/5] Creating unified management command..."
KEYMASTER_BIN="$KEYMASTER_DIR/keymaster"
if [ -f "$KEYMASTER_BIN" ]; then
    chmod +x "$KEYMASTER_BIN"
    # Create symlink if possible
    if [ -d "/usr/local/bin" ]; then
        ln -sf "$KEYMASTER_BIN" /usr/local/bin/keymaster 2>/dev/null || true
        echo "  ✓ 'keymaster' command available globally"
    else
        echo "  ✓ 'keymaster' command available at: $KEYMASTER_BIN"
    fi
else
    echo "  ⚠ Management script not found at $KEYMASTER_BIN"
fi

echo ""
echo "[5/5] Starting service (will create venv and install deps on first run)..."
systemctl enable "$SERVICE_FULL"

# Start the service
if systemctl start "$SERVICE_FULL"; then
    echo "  ✓ Service started"
else
    echo "  ⚠ Service start command issued (may still be initializing)"
fi

echo ""
echo "Waiting for service to initialize (10 seconds)..."
sleep 3
echo "  Still initializing..."
sleep 3
echo "  Almost there..."
sleep 4

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║              Installation Summary                         ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Check status
if systemctl is-active --quiet "$SERVICE_FULL"; then
    echo "Status: ✓ RUNNING"
else
    echo "Status: ✗ NOT RUNNING"
fi

if systemctl is-enabled --quiet "$SERVICE_FULL" 2>/dev/null; then
    echo "Auto-start: ✓ Enabled"
else
    echo "Auto-start: ✗ Disabled"
fi

# Check if venv was created
VENV_DIR="$HOME_DIR/.openclaw/keymaster_venv"
if [ -d "$VENV_DIR" ]; then
    echo "Virtual env: ✓ Created at $VENV_DIR"
else
    echo "Virtual env: ⏳ Will be created on first successful start"
fi

# Check proxy
if curl -s http://127.0.0.1:8787/health > /dev/null 2>&1; then
    echo "Proxy: ✓ Responding on port 8787"
else
    echo "Proxy: ⚠ Not yet responding (check logs)"
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                  Next Steps                               ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
echo "View unified logs:"
echo "  $KEYMASTER_DIR/keymaster logs"
echo "  # or"
echo "  tail -f $HOME_DIR/.openclaw/keymaster.log"
echo ""
echo "Check status:"
echo "  $KEYMASTER_DIR/keymaster status"
echo "  # or"
echo "  sudo systemctl status $SERVICE_FULL"
echo ""
echo "View key status:"
echo "  $KEYMASTER_DIR/keymaster keys"
echo ""
echo "If the service failed to start, check for errors:"
echo "  sudo journalctl -u $SERVICE_FULL -f"
echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║               Installation Complete                       ║"
echo "╚═══════════════════════════════════════════════════════════╝"
