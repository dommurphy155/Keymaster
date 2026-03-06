#!/bin/bash
# Service setup script - creates venv and configures OpenClaw
# Called by systemd ExecStartPre

set -e

HOME_DIR="${HOME}"
VENV_DIR="${HOME}/.openclaw/keymaster_venv"
LOG_FILE="${HOME}/.openclaw/keymaster.log"
KEYMASTER_DIR="${HOME}/.openclaw/skills/keymaster"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ============================================"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Keymaster Service Setup"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] User: $(whoami)"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ============================================"

# Check if venv exists and has dependencies
if [ ! -d "$VENV_DIR" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SETUP] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SETUP] Virtual environment created"
fi

# Check dependencies
if ! "$VENV_DIR/bin/python" -c "import fastapi, uvicorn, httpx, requests" 2>/dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SETUP] Installing dependencies..."
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    "$VENV_DIR/bin/pip" install -q fastapi uvicorn[standard] httpx requests
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SETUP] Dependencies installed"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SETUP] Dependencies already installed"
fi

# Configure OpenClaw
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SETUP] Configuring OpenClaw to use proxy..."
if [ -f "$KEYMASTER_DIR/scripts/configure_openclaw.py" ]; then
    "$VENV_DIR/bin/python" "$KEYMASTER_DIR/scripts/configure_openclaw.py" --enable
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SETUP] OpenClaw configured"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SETUP] Error: configure_openclaw.py not found"
fi

# Reset stale state
rm -f "${HOME}/.openclaw/keymaster_state.json"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SETUP] Setup complete, starting service..."
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ============================================"
