#!/usr/bin/env python3
"""
Start the OpenClaw Keymaster Proxy

Usage:
    python3 start_proxy.py                    # Start in foreground
    python3 start_proxy.py --daemon           # Start as daemon
    python3 start_proxy.py --stop             # Stop daemon
    python3 start_proxy.py --status           # Check status
    python3 start_proxy.py --install-systemd  # Install systemd service
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# PID file location
PID_FILE = Path.home() / ".openclaw/keymaster_proxy.pid"
LOG_FILE = Path.home() / ".openclaw/keymaster_proxy.log"


def is_proxy_running() -> bool:
    """Check if proxy is already running."""
    if not PID_FILE.exists():
        return False

    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())

        # Check if process exists
        os.kill(pid, 0)
        return True
    except (ValueError, OSError, ProcessLookupError):
        # PID file stale
        PID_FILE.unlink(missing_ok=True)
        return False


def get_pid() -> int:
    """Get proxy PID from file."""
    with open(PID_FILE) as f:
        return int(f.read().strip())


def start_proxy(foreground=False):
    """Start the proxy server."""
    if is_proxy_running():
        print("[start_proxy] Proxy is already running!")
        return

    proxy_path = Path(__file__).parent.parent / "proxy" / "server.py"

    if foreground:
        print("[start_proxy] Starting proxy in foreground...")
        print("[start_proxy] Press Ctrl+C to stop")
        print(f"[start_proxy] URL: http://127.0.0.1:8787")
        print()

        try:
            import uvicorn
            uvicorn.run(
                "proxy.server:app",
                host="127.0.0.1",
                port=8787,
                log_level="info",
                loop="uvloop"
            )
        except KeyboardInterrupt:
            print("\n[start_proxy] Stopped")
    else:
        print("[start_proxy] Starting proxy as daemon...")

        # Start with nohup
        log = open(LOG_FILE, "a")

        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "proxy.server:app",
             "--host", "127.0.0.1", "--port", "8787",
             "--loop", "uvloop", "--log-level", "info"],
            cwd=proxy_path.parent.parent,
            stdout=log,
            stderr=log,
            start_new_session=True
        )

        # Write PID file
        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))

        # Wait a moment to check if it started
        time.sleep(1)

        if proc.poll() is None:
            print(f"[start_proxy] Proxy started (PID: {proc.pid})")
            print(f"[start_proxy] URL: http://127.0.0.1:8787")
            print(f"[start_proxy] Logs: {LOG_FILE}")
            print()
            print("To stop: python3 start_proxy.py --stop")
            print("To check: python3 start_proxy.py --status")
        else:
            print("[start_proxy] Failed to start proxy!")
            print(f"[start_proxy] Check logs: {LOG_FILE}")
            PID_FILE.unlink(missing_ok=True)


def stop_proxy():
    """Stop the proxy server."""
    if not is_proxy_running():
        print("[start_proxy] Proxy is not running")
        PID_FILE.unlink(missing_ok=True)
        return

    pid = get_pid()
    print(f"[start_proxy] Stopping proxy (PID: {pid})...")

    try:
        # Try graceful shutdown first
        os.kill(pid, signal.SIGTERM)

        # Wait up to 5 seconds
        for _ in range(50):
            if not is_proxy_running():
                break
            time.sleep(0.1)

        # Force kill if still running
        if is_proxy_running():
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)

        PID_FILE.unlink(missing_ok=True)
        print("[start_proxy] Proxy stopped")
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        print("[start_proxy] Proxy was not running")


def check_status():
    """Check proxy status."""
    if is_proxy_running():
        pid = get_pid()
        print(f"[start_proxy] Proxy is running (PID: {pid})")
        print(f"[start_proxy] URL: http://127.0.0.1:8787")
        print(f"[start_proxy] Logs: {LOG_FILE}")

        # Try health check
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:8787/health", timeout=2) as resp:
                data = json.loads(resp.read())
                print(f"[start_proxy] Available keys: {data.get('available_keys', '?')}")
                print(f"[start_proxy] Cooling keys: {data.get('cooling_keys', '?')}")
        except Exception as e:
            print(f"[start_proxy] Health check failed: {e}")
    else:
        print("[start_proxy] Proxy is not running")


def install_systemd():
    """Install systemd service for auto-start."""
    service_content = f"""[Unit]
Description=OpenClaw Keymaster Proxy
After=network.target

[Service]
Type=simple
User={os.getlogin() if hasattr(os, 'getlogin') else 'ubuntu'}
WorkingDirectory={Path(__file__).parent.parent}
Environment=PYTHONPATH={Path(__file__).parent.parent}
ExecStart={sys.executable} -m uvicorn proxy.server:app --host 127.0.0.1 --port 8787 --loop uvloop
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

    service_path = "/etc/systemd/system/openclaw-proxy.service"

    print("[start_proxy] Installing systemd service...")
    print(f"[start_proxy] Service file: {service_path}")
    print()
    print("Run these commands as root:")
    print(f"  sudo tee {service_path} << 'EOF'")
    print(service_content)
    print("EOF")
    print("  sudo systemctl daemon-reload")
    print("  sudo systemctl enable openclaw-proxy")
    print("  sudo systemctl start openclaw-proxy")


def main():
    parser = argparse.ArgumentParser(description="OpenClaw Keymaster Proxy")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--stop", action="store_true", help="Stop daemon")
    parser.add_argument("--status", action="store_true", help="Check status")
    parser.add_argument("--install-systemd", action="store_true", help="Install systemd service")

    args = parser.parse_args()

    # Ensure .openclaw directory exists
    Path.home().joinpath(".openclaw").mkdir(exist_ok=True)

    if args.stop:
        stop_proxy()
    elif args.status:
        check_status()
    elif args.install_systemd:
        install_systemd()
    elif args.daemon:
        start_proxy(foreground=False)
    else:
        start_proxy(foreground=True)


if __name__ == "__main__":
    import json
    main()
