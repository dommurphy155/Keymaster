#!/usr/bin/env python3
"""
Enable Proxy Mode for OpenClaw

Updates openclaw.json to route requests through the local proxy.
This allows automatic key rotation.
"""

import json
import sys
from pathlib import Path


def enable_proxy_mode():
    """Update openclaw.json to use local proxy."""
    config_path = Path.home() / ".openclaw/openclaw.json"

    if not config_path.exists():
        print(f"[enable_proxy] Error: {config_path} not found!")
        sys.exit(1)

    print(f"[enable_proxy] Reading {config_path}")

    with open(config_path) as f:
        config = json.load(f)

    # Backup original
    backup_path = config_path.with_suffix(".json.backup")
    with open(backup_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"[enable_proxy] Backup created: {backup_path}")

    # Check if proxy is already enabled
    providers = config.get("models", {}).get("providers", {})

    proxy_enabled = False
    for provider_name, provider_config in providers.items():
        if provider_name.startswith("nvidia-key-"):
            base_url = provider_config.get("baseUrl", "")
            if "localhost" in base_url or "127.0.0.1" in base_url:
                proxy_enabled = True
                break

    if proxy_enabled:
        print("[enable_proxy] Proxy mode already enabled!")
        print("[enable_proxy] Your config is already using the proxy.")
        return

    # Update each nvidia-key provider
    updated_count = 0
    for provider_name, provider_config in providers.items():
        if provider_name.startswith("nvidia-key-"):
            original_url = provider_config.get("baseUrl", "")

            # Store original URL in metadata
            if "originalBaseUrl" not in provider_config:
                provider_config["originalBaseUrl"] = original_url

            # Point to proxy
            provider_config["baseUrl"] = "http://127.0.0.1:8787/v1"
            updated_count += 1
            print(f"[enable_proxy] {provider_name}: {original_url} → http://127.0.0.1:8787/v1")

    if updated_count == 0:
        print("[enable_proxy] Warning: No nvidia-key providers found!")
        sys.exit(1)

    # Save updated config
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print()
    print(f"[enable_proxy] ✓ Updated {updated_count} providers to use proxy")
    print()
    print("Next steps:")
    print("  1. Start the proxy:")
    print("     python3 ~/.openclaw/skills/keymaster/scripts/start_proxy.py")
    print()
    print("  2. Use OpenClaw normally - it will now rotate keys automatically!")
    print()
    print("To disable proxy mode and restore direct connections:")
    print("  python3 ~/.openclaw/skills/keymaster/scripts/disable_proxy.py")


def disable_proxy_mode():
    """Restore original direct connections to NVIDIA."""
    config_path = Path.home() / ".openclaw/openclaw.json"

    if not config_path.exists():
        print(f"[disable_proxy] Error: {config_path} not found!")
        sys.exit(1)

    print(f"[disable_proxy] Reading {config_path}")

    with open(config_path) as f:
        config = json.load(f)

    # Restore each nvidia-key provider
    providers = config.get("models", {}).get("providers", {})
    restored_count = 0

    for provider_name, provider_config in providers.items():
        if provider_name.startswith("nvidia-key-"):
            original_url = provider_config.get("originalBaseUrl")

            if original_url:
                provider_config["baseUrl"] = original_url
                del provider_config["originalBaseUrl"]
                restored_count += 1
                print(f"[disable_proxy] {provider_name}: restored to {original_url}")
            else:
                print(f"[disable_proxy] {provider_name}: no original URL found")

    if restored_count == 0:
        print("[disable_proxy] Warning: No providers to restore!")
        return

    # Save updated config
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print()
    print(f"[disable_proxy] ✓ Restored {restored_count} providers to direct connections")
    print()
    print("You can now stop the proxy:")
    print("  python3 ~/.openclaw/skills/keymaster/scripts/start_proxy.py --stop")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--disable":
        disable_proxy_mode()
    else:
        enable_proxy_mode()
