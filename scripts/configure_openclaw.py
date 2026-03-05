#!/usr/bin/env python3
"""
Configure OpenClaw to use the Keymaster Proxy

This script modifies ~/.openclaw/openclaw.json to route API calls
through the local proxy instead of directly to NVIDIA.

Usage:
    python3 configure_openclaw.py --enable    # Enable proxy
    python3 configure_openclaw.py --disable   # Disable proxy (direct to NVIDIA)
    python3 configure_openclaw.py --status    # Check current config
"""

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, Any

PROXY_URL = "http://127.0.0.1:8787"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1"

CONFIG_PATH = Path.home() / ".openclaw/openclaw.json"
BACKUP_PATH = Path.home() / ".openclaw/openclaw.json.backup"


def load_config() -> Dict[str, Any]:
    """Load OpenClaw config."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(config: Dict[str, Any]):
    """Save OpenClaw config."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def backup_config():
    """Backup current config."""
    if CONFIG_PATH.exists():
        shutil.copy(CONFIG_PATH, BACKUP_PATH)
        print(f"[configure] Backed up config to {BACKUP_PATH}")


def enable_proxy():
    """Configure OpenClaw to use the proxy."""
    if not CONFIG_PATH.exists():
        print(f"[configure] Error: Config not found at {CONFIG_PATH}")
        return False

    backup_config()

    config = load_config()

    # Modify provider URLs
    providers = config.get("models", {}).get("providers", {})

    modified = False
    for provider_name, provider_config in providers.items():
        if provider_name.startswith("nvidia-key-"):
            old_url = provider_config.get("baseUrl", "")
            if NVIDIA_URL in old_url:
                provider_config["baseUrl"] = PROXY_URL
                print(f"[configure] {provider_name}: {old_url} -> {PROXY_URL}")
                modified = True
            elif PROXY_URL in old_url:
                print(f"[configure] {provider_name}: Already using proxy")
            else:
                provider_config["baseUrl"] = PROXY_URL
                print(f"[configure] {provider_name}: Set to {PROXY_URL}")
                modified = True

    if modified:
        save_config(config)
        print()
        print("[configure] ✓ OpenClaw configured to use proxy!")
        print(f"[configure] Proxy URL: {PROXY_URL}")
        print()
        print("Next steps:")
        print("  1. Start proxy: python3 start_proxy.py")
        print("  2. Use openclaw normally - keys will rotate automatically!")
    else:
        print("[configure] No changes needed")

    return True


def disable_proxy():
    """Revert OpenClaw to direct NVIDIA connection."""
    if not CONFIG_PATH.exists():
        print(f"[configure] Error: Config not found at {CONFIG_PATH}")
        return False

    backup_config()

    config = load_config()

    # Revert provider URLs
    providers = config.get("models", {}).get("providers", {})

    modified = False
    for provider_name, provider_config in providers.items():
        if provider_name.startswith("nvidia-key-"):
            old_url = provider_config.get("baseUrl", "")
            if PROXY_URL in old_url:
                provider_config["baseUrl"] = NVIDIA_URL
                print(f"[configure] {provider_name}: {old_url} -> {NVIDIA_URL}")
                modified = True
            elif NVIDIA_URL in old_url:
                print(f"[configure] {provider_name}: Already direct to NVIDIA")
            else:
                provider_config["baseUrl"] = NVIDIA_URL
                print(f"[configure] {provider_name}: Set to {NVIDIA_URL}")
                modified = True

    if modified:
        save_config(config)
        print()
        print("[configure] ✓ OpenClaw reverted to direct NVIDIA connection")
        print()
        print("Note: Remember to stop the proxy if running:")
        print("  python3 start_proxy.py --stop")
    else:
        print("[configure] No changes needed")

    return True


def check_status():
    """Check current configuration."""
    if not CONFIG_PATH.exists():
        print(f"[configure] Error: Config not found at {CONFIG_PATH}")
        return

    config = load_config()
    providers = config.get("models", {}).get("providers", {})

    using_proxy = False

    print("[configure] Current configuration:")
    print()

    for provider_name, provider_config in providers.items():
        if provider_name.startswith("nvidia-key-"):
            url = provider_config.get("baseUrl", "N/A")
            key_preview = provider_config.get("apiKey", "N/A")[:20] + "..."

            if PROXY_URL in url:
                status = "→ PROXY"
                using_proxy = True
            elif NVIDIA_URL in url:
                status = "→ NVIDIA (direct)"
            else:
                status = f"→ {url}"

            print(f"  {provider_name}: {status}")

    print()
    if using_proxy:
        print("[configure] OpenClaw is configured to use the proxy")
        print(f"[configure] Proxy should be running at {PROXY_URL}")
    else:
        print("[configure] OpenClaw connects directly to NVIDIA")
        print("[configure] Proxy is not being used")


def main():
    parser = argparse.ArgumentParser(
        description="Configure OpenClaw to use Keymaster Proxy"
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        help="Enable proxy (route through localhost:8787)"
    )
    parser.add_argument(
        "--disable",
        action="store_true",
        help="Disable proxy (direct to NVIDIA)"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check current configuration"
    )

    args = parser.parse_args()

    if args.enable:
        enable_proxy()
    elif args.disable:
        disable_proxy()
    else:
        check_status()


if __name__ == "__main__":
    main()
