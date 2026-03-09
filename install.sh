#!/bin/bash
#
# OpenClaw Keymaster Unified Auto-Installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/dommurphy155/Keymaster/main/install.sh | bash
#   OR
#   bash install.sh
#
# This script:
# 1. Checks prerequisites (Python 3.8+, systemd)
# 2. Creates isolated virtual environment
# 3. Installs all dependencies
# 4. Configures the unified systemd service
# 5. Installs the 'keymaster' management command
# 6. Starts everything together with unified logging

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
USER_NAME="${USER:-$(whoami)}"
HOME_DIR="${HOME}"
KEYMASTER_DIR="${HOME_DIR}/.openclaw/skills/keymaster"
VENV_DIR="${HOME_DIR}/.openclaw/keymaster_venv"
LOG_FILE="${HOME_DIR}/.openclaw/keymaster.log"
SERVICE_NAME="openclaw-keymaster"
SERVICE_FULL="${SERVICE_NAME}@${USER_NAME}"

# Print helpers
print_banner() {
    echo -e "${CYAN}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                                                                ║"
    echo "║          OpenClaw Keymaster - Unified Installer               ║"
    echo "║     Intelligent API Key Rotation for NVIDIA LLMs            ║"
    echo "║                                                                ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${BLUE}[Step $1/7]${NC} $2"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${CYAN}ℹ${NC} $1"
}

# Check if running with sudo
check_sudo() {
    if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
        print_error "This script should NOT be run with sudo"
        print_info "It will prompt for sudo only when needed for systemd"
        exit 1
    fi
}

# Step 1: Check prerequisites
check_prerequisites() {
    print_step "1" "Checking prerequisites..."

    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi

    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    print_success "Python ${PYTHON_VERSION} found"

    # Check systemd
    if ! command -v systemctl > /dev/null 2>&1; then
        print_warn "systemd not found - service mode unavailable"
        print_info "You can still run keymaster manually"
    else
        print_success "systemd available"
    fi

    # Check keymaster directory
    if [ ! -d "$KEYMASTER_DIR" ]; then
        print_error "Keymaster directory not found: ${KEYMASTER_DIR}"
        print_info "Please ensure keymaster is installed at ~/.openclaw/skills/keymaster"
        exit 1
    fi
    print_success "Keymaster directory found"
}

# Step 2: Create virtual environment
setup_venv() {
    print_step "2" "Setting up Python virtual environment..."

    if [ -d "$VENV_DIR" ]; then
        print_warn "Virtual environment already exists"
        print_info "Updating dependencies..."
    else
        print_info "Creating virtual environment at ${VENV_DIR}..."
        python3 -m venv "$VENV_DIR"
        print_success "Virtual environment created"
    fi

    # Upgrade pip
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip

    # Install dependencies
    print_info "Installing dependencies (this may take a minute)..."
    "$VENV_DIR/bin/pip" install --quiet \
        fastapi \
        uvicorn[standard] \
        httpx \
        requests \
        aiohttp

    print_success "Dependencies installed"
}

# Step 3: Check configuration
check_config() {
    print_step "3" "Checking configuration..."

    # Check auth-profiles.json
    AUTH_PROFILES="${HOME_DIR}/.openclaw/agents/main/agent/auth-profiles.json"
    if [ ! -f "$AUTH_PROFILES" ]; then
        print_error "auth-profiles.json not found!"
        print_info "Please create it with your NVIDIA API keys"
        print_info "Location: ${AUTH_PROFILES}"
        exit 1
    fi

    # Count keys
    KEY_COUNT=$(jq -r '.profiles | keys | map(select(startswith("nvidia:"))) | length' "$AUTH_PROFILES" 2>/dev/null || echo "0")

    if [ "$KEY_COUNT" -eq "0" ]; then
        print_error "No NVIDIA keys found in auth-profiles.json"
        exit 1
    fi

    print_success "Found ${KEY_COUNT} NVIDIA API keys"

    # Check openclaw.json
    if [ ! -f "${HOME_DIR}/.openclaw/openclaw.json" ]; then
        print_warn "openclaw.json not found"
        print_info "You may need to configure OpenClaw separately"
    else
        print_success "OpenClaw configuration found"
    fi
}

# Step 4: Install systemd service
install_service() {
    print_step "4" "Installing systemd service..."

    if ! command -v systemctl > /dev/null 2>&1; then
        print_warn "systemd not available - skipping service installation"
        return 0
    fi

    # Check if we have sudo access
    if ! sudo -n true 2>/dev/null; then
        print_warn "Sudo access required for service installation"
        print_info "Please enter your password when prompted..."
    fi

    # Install service file
    SERVICE_FILE="${KEYMASTER_DIR}/systemd/openclaw-keymaster@.service"
    if [ ! -f "$SERVICE_FILE" ]; then
        print_error "Service file not found: ${SERVICE_FILE}"
        exit 1
    fi

    sudo cp "$SERVICE_FILE" "/etc/systemd/system/"
    sudo systemctl daemon-reload

    print_success "Service file installed"
}

# Step 5: Configure OpenClaw
configure_openclaw() {
    print_step "5" "Configuring OpenClaw..."

    CONFIGURE_SCRIPT="${KEYMASTER_DIR}/scripts/configure_openclaw.py"
    if [ -f "$CONFIGURE_SCRIPT" ]; then
        "$VENV_DIR/bin/python" "$CONFIGURE_SCRIPT" --enable
        print_success "OpenClaw configured to use proxy"
    else
        print_warn "configure_openclaw.py not found"
    fi
}

# Step 6: Install keymaster command
install_command() {
    print_step "6" "Installing 'keymaster' command..."

    KEYMASTER_BIN="${KEYMASTER_DIR}/keymaster"

    if [ -f "$KEYMASTER_BIN" ]; then
        chmod +x "$KEYMASTER_BIN"

        # Try to create symlink
        if [ -w "/usr/local/bin" ]; then
            sudo ln -sf "$KEYMASTER_BIN" /usr/local/bin/keymaster 2>/dev/null || true
            print_success "'keymaster' command available globally"
        elif [ -d "${HOME_DIR}/.local/bin" ]; then
            mkdir -p "${HOME_DIR}/.local/bin"
            ln -sf "$KEYMASTER_BIN" "${HOME_DIR}/.local/bin/keymaster" 2>/dev/null || true
            print_success "'keymaster' command installed to ~/.local/bin"
            print_info "Make sure ~/.local/bin is in your PATH"
        else
            print_success "'keymaster' command available at: ${KEYMASTER_BIN}"
        fi
    else
        print_warn "keymaster binary not found"
    fi
}

# Step 7: Start service
start_service() {
    print_step "7" "Starting Keymaster service..."

    if ! command -v systemctl > /dev/null 2>&1; then
        print_warn "systemd not available - starting manually..."
        print_info "To start keymaster manually:"
        print_info "  ${KEYMASTER_DIR}/scripts/run_unified.sh"
        return 0
    fi

    # Enable and start
    sudo systemctl enable "$SERVICE_FULL"

    if sudo systemctl start "$SERVICE_FULL"; then
        print_success "Service started"

        # Wait for it to be ready
        print_info "Waiting for service to initialize..."
        for i in {1..10}; do
            sleep 1
            if curl -s http://127.0.0.1:8787/health >/dev/null 2>&1; then
                print_success "Proxy is responding!"
                return 0
            fi
            echo -n "."
        done
        echo
        print_warn "Service started but proxy not yet responding"
    else
        print_error "Failed to start service"
        return 1
    fi
}

# Show final summary
show_summary() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗"
    echo "║                     Installation Complete!                     ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""

    # Check service status
    if command -v systemctl > /dev/null 2>&1; then
        if systemctl is-active --quiet "$SERVICE_FULL" 2>/dev/null; then
            echo -e "Service Status: ${GREEN}● Running${NC}"
        else
            echo -e "Service Status: ${RED}● Stopped${NC}"
        fi

        if systemctl is-enabled --quiet "$SERVICE_FULL" 2>/dev/null; then
            echo -e "Auto-start: ${GREEN}● Enabled${NC}"
        else
            echo -e "Auto-start: ${YELLOW}● Disabled${NC}"
        fi
    fi

    # Check proxy
    if curl -s http://127.0.0.1:8787/health >/dev/null 2>&1; then
        echo -e "Proxy: ${GREEN}● Responding on port 8787${NC}"
    else
        echo -e "Proxy: ${YELLOW}● Not yet responding${NC}"
    fi

    echo ""
    echo -e "${CYAN}Quick Commands:${NC}"
    echo "  keymaster status    - Check service status"
    echo "  keymaster logs      - View unified logs"
    echo "  keymaster keys      - List API keys"
    echo "  keymaster health    - Run health check"
    echo ""
    echo -e "${CYAN}Logs:${NC}"
    echo "  tail -f ${LOG_FILE}"
    echo ""
    echo -e "${CYAN}Service Control:${NC}"
    echo "  keymaster start     - Start the service"
    echo "  keymaster stop      - Stop the service"
    echo "  keymaster restart   - Restart the service"
    echo ""
    echo -e "${GREEN}Keymaster is now running with unified logging!${NC}"
    echo -e "All logs go to: ${LOG_FILE}"
    echo -e "OpenClaw will automatically use the proxy for all NVIDIA API calls."
    echo ""
}

# Main installation flow
main() {
    print_banner

    check_sudo
    check_prerequisites
    setup_venv
    check_config
    install_service
    configure_openclaw
    install_command
    start_service
    show_summary
}

# Handle script interruption
trap 'print_error "Installation interrupted"; exit 1' INT TERM

# Run main
main
