#!/usr/bin/env python3
"""
Keymaster Activation Script

Ensures Keymaster is properly configured and active in OpenClaw.
Run this after installation or to verify setup.
"""

import json
import os
from pathlib import Path

SKILL_PATH = Path.home() / ".openclaw" / "skills" / "keymaster"
AUTH_PROFILES_PATH = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"


def check_skill_exists():
    """Verify skill files exist."""
    required_files = [
        "SKILL.md",
        "scripts/key_pool_manager.py",
        "scripts/request_wrapper.py",
        "scripts/context_compactor.py",
        "scripts/state_manager.py"
    ]

    missing = []
    for file in required_files:
        if not (SKILL_PATH / file).exists():
            missing.append(file)

    if missing:
        print(f"[Keymaster] MISSING FILES: {missing}")
        return False

    print("[Keymaster] All skill files present")
    return True


def check_auth_profiles():
    """Verify auth profiles have keymaster config."""
    if not AUTH_PROFILES_PATH.exists():
        print(f"[Keymaster] ERROR: auth-profiles.json not found")
        return False

    with open(AUTH_PROFILES_PATH, 'r') as f:
        profiles = json.load(f)

    # Check for keymaster config
    if 'keymaster' not in profiles:
        print("[Keymaster] Adding keymaster config to auth-profiles...")
        profiles['keymaster'] = {
            "enabled": True,
            "auto_rotation": True,
            "context_compaction": True,
            "compaction_threshold": 0.8,
            "cooldown_seconds": 60,
            "max_retries_per_key": 3,
            "state_persistence": True
        }

        with open(AUTH_PROFILES_PATH, 'w') as f:
            json.dump(profiles, f, indent=2)

        print("[Keymaster] Config added")
    else:
        print("[Keymaster] Config present in auth-profiles")

    # Check for all 5 keys
    required_keys = [
        "nvidia:primary",
        "nvidia:secondary",
        "nvidia:tertiary",
        "nvidia:quaternary",
        "nvidia:quinary"
    ]

    for key in required_keys:
        if key not in profiles.get('profiles', {}):
            print(f"[Keymaster] WARNING: Missing key {key}")

    return True


def check_openclaw_config():
    """Verify OpenClaw config references only NVIDIA keys."""
    if not OPENCLAW_CONFIG.exists():
        print(f"[Keymaster] WARNING: openclaw.json not found")
        return False

    with open(OPENCLAW_CONFIG, 'r') as f:
        config = json.load(f)

    # Check auth profiles
    auth_profiles = config.get('auth', {}).get('profiles', {})
    nvidia_only = all(
        'nvidia' in key for key in auth_profiles.keys()
    )

    if nvidia_only:
        print("[Keymaster] OpenClaw config: NVIDIA keys only")
    else:
        print("[Keymaster] WARNING: Non-NVIDIA keys detected in config")

    return True


def test_key_rotation():
    """Test key rotation logic."""
    try:
        import sys
        sys.path.insert(0, str(SKILL_PATH / "scripts"))
        from key_pool_manager import KeyPoolManager

        manager = KeyPoolManager()
        stats = manager.get_stats()

        print(f"[Keymaster] Current key: {stats['current_key']}")
        print(f"[Keymaster] Available keys: {stats['available_keys']}/5")
        print(f"[Keymaster] Total rotations: {stats['total_rotations']}")

        return True
    except Exception as e:
        print(f"[Keymaster] ERROR testing rotation: {e}")
        return False


def main():
    """Run all activation checks."""
    print("=" * 50)
    print("Keymaster Activation Check")
    print("=" * 50)

    checks = [
        ("Skill Files", check_skill_exists),
        ("Auth Profiles", check_auth_profiles),
        ("OpenClaw Config", check_openclaw_config),
        ("Key Rotation", test_key_rotation)
    ]

    results = []
    for name, check_fn in checks:
        print(f"\n[{name}] Checking...")
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            print(f"[{name}] ERROR: {e}")
            results.append((name, False))

    print("\n" + "=" * 50)
    print("Activation Summary")
    print("=" * 50)

    all_passed = True
    for name, result in results:
        status = "OK" if result else "FAIL"
        symbol = " " if result else " "
        print(f"{symbol} {name}: {status}")
        if not result:
            all_passed = False

    print("=" * 50)

    if all_passed:
        print("[Keymaster] ACTIVATION SUCCESSFUL")
        print("[Keymaster] Keymaster is ready to use")
        print("\nUsage:")
        print("  from keymaster.scripts import keymaster_request")
        print("  response = keymaster_request(messages)")
    else:
        print("[Keymaster] Some checks failed - review output above")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
