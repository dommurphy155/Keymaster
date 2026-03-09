#!/bin/bash
# Unified Keymaster Runner - Single entry point for all components
# This script runs everything together with unified logging

set -e

# Setup paths
HOME_DIR="${HOME}"
KEYMASTER_DIR="${HOME_DIR}/.openclaw/skills/keymaster"
VENV_DIR="${HOME_DIR}/.openclaw/keymaster_venv"
LOG_FILE="${HOME_DIR}/.openclaw/keymaster.log"

# Logging function - everything goes to stdout (captured by systemd)
log() {
    local level="$1"
    shift
    local msg="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S.%3N')
    echo "[${timestamp}] [${level}] ${msg}"
}

log_info() { log "INFO" "$@"; }
log_warn() { log "WARN" "$@"; }
log_error() { log "ERROR" "$@"; }
log_init() { log "INIT" "$@"; }
log_proxy() { log "PROXY" "$@"; }

# Cleanup function
cleanup() {
    log_warn "Received shutdown signal, cleaning up..."
    # Kill any child processes
    pkill -P $$ 2>/dev/null || true
    exit 0
}

trap cleanup SIGTERM SIGINT

# Header
log_init "=========================================="
log_init "Keymaster Unified Service Starting"
log_init "User: $(whoami)"
log_init "Home: ${HOME_DIR}"
log_init "=========================================="

# Verify virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    log_error "Virtual environment not found at ${VENV_DIR}"
    log_error "Run setup first: ${KEYMASTER_DIR}/scripts/service-setup.sh"
    exit 1
fi

# Set up environment
export PATH="${VENV_DIR}/bin:${PATH}"
export PYTHONPATH="${KEYMASTER_DIR}"
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Verify Python and key dependencies
if ! command -v python3 &> /dev/null; then
    log_error "Python3 not found"
    exit 1
fi

# Check critical dependencies
log_init "Checking dependencies..."
MISSING_DEPS=""

for dep in fastapi uvicorn httpx; do
    if ! python3 -c "import ${dep}" 2>/dev/null; then
        MISSING_DEPS="${MISSING_DEPS} ${dep}"
    fi
done

if [ -n "$MISSING_DEPS" ]; then
    log_warn "Missing dependencies:${MISSING_DEPS}"
    log_init "Installing missing dependencies..."
    pip install --quiet ${MISSING_DEPS} || {
        log_error "Failed to install dependencies"
        exit 1
    }
fi

log_init "Dependencies OK"

# Verify configuration files exist
log_init "Checking configuration..."

if [ ! -f "${HOME_DIR}/.openclaw/agents/main/agent/auth-profiles.json" ]; then
    log_error "auth-profiles.json not found!"
    log_error "Please configure your NVIDIA API keys first"
    exit 1
fi

KEY_COUNT=$(jq -r '.profiles | keys | map(select(startswith("nvidia:"))) | length' \
    "${HOME_DIR}/.openclaw/agents/main/agent/auth-profiles.json" 2>/dev/null || echo "0")

if [ "$KEY_COUNT" -eq "0" ]; then
    log_error "No NVIDIA keys found in auth-profiles.json"
    exit 1
fi

log_init "Configuration OK - Found ${KEY_COUNT} NVIDIA keys"

# Configure OpenClaw to use proxy
log_init "Configuring OpenClaw to use proxy..."
python3 "${KEYMASTER_DIR}/scripts/configure_openclaw.py" --enable 2>&1 | while read line; do
    log_init "Config: ${line}"
done

# Start the proxy server
log_init "=========================================="
log_init "Starting Proxy Server on port 8787"
log_init "=========================================="

# Change to keymaster directory for proper module resolution
cd "${KEYMASTER_DIR}"

# Run the proxy with unbuffered output
# Using exec to replace this script with the proxy process
# This allows systemd to manage the proxy directly
exec python3 -u -m uvicorn proxy.server:app \
    --host 127.0.0.1 \
    --port 8787 \
    --loop uvloop \
    --log-level info \
    --no-access-log \
    --proxy-headers
