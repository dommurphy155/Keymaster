#!/bin/bash
# Install OpenClaw Keymaster Proxy as a systemd service
# Usage: sudo ./install-service.sh [username]

set -e

USER_NAME="${1:-$SUDO_USER}"
if [ -z "$USER_NAME" ]; then
    USER_NAME="$(whoami)"
fi

HOME_DIR="/home/$USER_NAME"
SERVICE_NAME="openclaw-proxy"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}@.service"

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo ./install-service.sh"
    exit 1
fi

echo "Installing OpenClaw Keymaster Proxy Service..."
echo "User: $USER_NAME"
echo "Home: $HOME_DIR"
echo ""

# Check if keymaster is installed
if [ ! -d "$HOME_DIR/.openclaw/skills/keymaster" ]; then
    echo "ERROR: Keymaster not found at $HOME_DIR/.openclaw/skills/keymaster"
    echo "Please install keymaster first."
    exit 1
fi

# Check for auth-profiles.json
if [ ! -f "$HOME_DIR/.openclaw/agents/main/agent/auth-profiles.json" ]; then
    echo "WARNING: auth-profiles.json not found!"
    echo "You need to set up your API keys first."
fi

# Check for openclaw.json
if [ ! -f "$HOME_DIR/.openclaw/openclaw.json" ]; then
    echo "WARNING: openclaw.json not found!"
    echo "You need to configure OpenClaw first."
fi

# Create systemd service file
cat > "$SERVICE_FILE" << 'EOF'
[Unit]
Description=OpenClaw Keymaster Proxy
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=%i
WorkingDirectory=/home/%i/.openclaw/skills/keymaster
Environment=PYTHONPATH=/home/%i/.openclaw/skills/keymaster
Environment=HOME=/home/%i
Environment=PATH=/usr/local/bin:/usr/bin:/bin:/home/%i/.local/bin

# Ensure .openclaw directory exists
ExecStartPre=/bin/mkdir -p /home/%i/.openclaw

# Pre-start: Configure OpenClaw to use proxy
ExecStartPre=/bin/bash -c 'echo "[$(date '+%Y-%m-%d %H:%M:%S')] Keymaster: Configuring OpenClaw..." >> /home/%i/.openclaw/keymaster_service.log'
ExecStartPre=/usr/bin/python3 /home/%i/.openclaw/skills/keymaster/scripts/configure_openclaw.py --enable

# Start the proxy
ExecStart=/usr/bin/python3 -m uvicorn proxy.server:app --host 127.0.0.1 --port 8787 --loop uvloop --log-level info

# Logging
StandardOutput=append:/home/%i/.openclaw/keymaster_service.log
StandardError=append:/home/%i/.openclaw/keymaster_service.log

# Restart on failure
Restart=always
RestartSec=5
StartLimitInterval=60s
StartLimitBurst=3

# Graceful shutdown
TimeoutStopSec=30
KillSignal=SIGTERM

# File descriptor and process limits
LimitNOFILE=65535
LimitNPROC=4096
TasksMax=infinity

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=false
ReadWritePaths=/home/%i/.openclaw

[Install]
WantedBy=multi-user.target
EOF

# Copy service template
cp "$HOME_DIR/.openclaw/skills/keymaster/systemd/openclaw-proxy.service" \
   "$HOME_DIR/.openclaw/skills/keymaster/systemd/openclaw-proxy@.service.backup" 2>/dev/null || true

echo "Created systemd service: $SERVICE_FILE"

# Reload systemd
systemctl daemon-reload

echo ""
echo "Systemd service installed successfully!"
echo ""
echo "To enable and start the service:"
echo "  sudo systemctl enable ${SERVICE_NAME}@${USER_NAME}"
echo "  sudo systemctl start ${SERVICE_NAME}@${USER_NAME}"
echo ""
echo "To check status:"
echo "  sudo systemctl status ${SERVICE_NAME}@${USER_NAME}"
echo ""
echo "To view logs:"
echo "  sudo tail -f /home/${USER_NAME}/.openclaw/keymaster_service.log"
echo ""

# Ask if user wants to enable and start now
read -p "Enable and start the service now? [Y/n] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
    echo "Enabling service..."
    systemctl enable "${SERVICE_NAME}@${USER_NAME}"

    echo "Starting service..."
    systemctl start "${SERVICE_NAME}@${USER_NAME}"

    sleep 2

    # Check status
    if systemctl is-active --quiet "${SERVICE_NAME}@${USER_NAME}"; then
        echo ""
        echo "✓ Service is running!"
        systemctl status "${SERVICE_NAME}@${USER_NAME}" --no-pager
    else
        echo ""
        echo "✗ Service failed to start. Check logs:"
        echo "  sudo systemctl status ${SERVICE_NAME}@${USER_NAME}"
        echo "  sudo tail -n 50 /home/${USER_NAME}/.openclaw/keymaster_service.log"
    fi
fi

echo ""
echo "Done!"
