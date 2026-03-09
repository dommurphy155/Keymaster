#!/bin/bash
# Keymaster Service Manager
# Usage: ./service.sh [start|stop|restart|status|logs|enable|disable]

USER_NAME="${USER:-ubuntu}"
SERVICE_NAME="openclaw-proxy"
SERVICE_FULL="${SERVICE_NAME}@${USER_NAME}"

show_help() {
    echo "Keymaster Service Manager"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start    - Start the proxy service"
    echo "  stop     - Stop the proxy service"
    echo "  restart  - Restart the proxy service"
    echo "  status   - Check service status"
    echo "  logs     - View service logs"
    echo "  enable   - Enable auto-start on boot"
    echo "  disable  - Disable auto-start on boot"
    echo "  install  - Install systemd service (requires sudo)"
    echo "  health   - Check proxy health"
    echo ""
}

check_sudo() {
    if [ "$EUID" -ne 0 ]; then
        echo "This command requires sudo. Running with sudo..."
        sudo "$0" "$@"
        exit $?
    fi
}

start_service() {
    check_sudo "$@"
    echo "Starting ${SERVICE_FULL}..."
    systemctl start "$SERVICE_FULL"
    sleep 1
    status_service
}

stop_service() {
    check_sudo "$@"
    echo "Stopping ${SERVICE_FULL}..."
    systemctl stop "$SERVICE_FULL"
    echo "Also disabling proxy in OpenClaw config..."
    python3 ~/.openclaw/skills/keymaster/scripts/configure_openclaw.py --disable 2>/dev/null || true
}

restart_service() {
    check_sudo "$@"
    echo "Restarting ${SERVICE_FULL}..."
    systemctl restart "$SERVICE_FULL"
    sleep 1
    status_service
}

status_service() {
    if systemctl is-active --quiet "$SERVICE_FULL" 2>/dev/null; then
        echo "✓ Service is running"
        systemctl status "$SERVICE_FULL" --no-pager
    else
        echo "✗ Service is not running"
        systemctl status "$SERVICE_FULL" --no-pager 2>&1 || true
    fi
}

view_logs() {
    LOG_FILE="$HOME/.openclaw/keymaster_service.log"
    if [ -f "$LOG_FILE" ]; then
        echo "Viewing logs (Ctrl+C to exit):"
        tail -f "$LOG_FILE"
    else
        echo "Log file not found: $LOG_FILE"
        echo "Checking journalctl instead..."
        sudo journalctl -u "$SERVICE_FULL" -f
    fi
}

enable_service() {
    check_sudo "$@"
    echo "Enabling ${SERVICE_FULL} to start on boot..."
    systemctl enable "$SERVICE_FULL"
    echo "Done!"
}

disable_service() {
    check_sudo "$@"
    echo "Disabling ${SERVICE_FULL}..."
    systemctl disable "$SERVICE_FULL"
    echo "Done!"
}

install_service() {
    check_sudo "$@"
    if [ -f "$HOME/.openclaw/skills/keymaster/install-service.sh" ]; then
        cd "$HOME/.openclaw/skills/keymaster"
        ./install-service.sh
    else
        echo "Install script not found!"
        exit 1
    fi
}

health_check() {
    echo "Checking proxy health..."
    if curl -s http://127.0.0.1:8787/health 2>/dev/null; then
        echo ""
        echo "✓ Proxy is responding"
    else
        echo "✗ Proxy is not responding on http://127.0.0.1:8787"
        echo "  Is the service running? Try: $0 start"
    fi
}

# Main
case "${1:-status}" in
    start)
        start_service "$@"
        ;;
    stop)
        stop_service "$@"
        ;;
    restart)
        restart_service "$@"
        ;;
    status)
        status_service
        ;;
    logs)
        view_logs
        ;;
    enable)
        enable_service "$@"
        ;;
    disable)
        disable_service "$@"
        ;;
    install)
        install_service "$@"
        ;;
    health)
        health_check
        ;;
    -h|--help|help)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
