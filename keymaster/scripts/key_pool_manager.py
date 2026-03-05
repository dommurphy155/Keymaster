#!/usr/bin/env python3
"""
Key Pool Manager - Manages rotation and cooldown of NVIDIA API keys.

Reads from:
- ~/.openclaw/openclaw.json (for provider configs with actual API keys)
- ~/.openclaw/agents/main/agent/auth-profiles.json (for key metadata, roles, fallback chains)

Maintains state in ~/.openclaw/keymaster_state.json
"""

import json
import os
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

# Config paths
OPENCLAW_CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"
AUTH_PROFILES_PATH = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
STATE_PATH = Path.home() / ".openclaw" / "keymaster_state.json"


@dataclass
class KeyStatus:
    name: str
    available: bool
    cooldown_until: Optional[float]
    error_count: int
    last_used: Optional[float]
    priority: int
    role: str


@dataclass
class KeymasterState:
    current_key: str
    key_status: Dict[str, KeyStatus]
    last_rotation: Optional[float]
    rotation_count: int
    compaction_history: List[Dict[str, Any]]


class KeyPoolManager:
    """Manages the pool of NVIDIA API keys with rotation and cooldown."""

    # Key mapping from auth-profiles to openclaw.json providers
    KEY_NAME_MAP = {
        "nvidia:primary": "nvidia-key-1",
        "nvidia:secondary": "nvidia-key-2",
        "nvidia:tertiary": "nvidia-key-3",
        "nvidia:quaternary": "nvidia-key-4",
        "nvidia:quinary": "nvidia-key-5"
    }

    REVERSE_KEY_MAP = {v: k for k, v in KEY_NAME_MAP.items()}

    DEFAULT_COOLDOWN_SECONDS = 60

    def __init__(self):
        self.openclaw_config = self._load_openclaw_config()
        self.auth_profiles = self._load_auth_profiles()
        self.state = self._load_state()

    def _load_openclaw_config(self) -> dict:
        """Load OpenClaw configuration with API keys."""
        if not OPENCLAW_CONFIG_PATH.exists():
            raise FileNotFoundError(f"OpenClaw config not found at {OPENCLAW_CONFIG_PATH}")

        with open(OPENCLAW_CONFIG_PATH, 'r') as f:
            return json.load(f)

    def _load_auth_profiles(self) -> dict:
        """Load authentication profiles with metadata."""
        if not AUTH_PROFILES_PATH.exists():
            raise FileNotFoundError(f"Auth profiles not found at {AUTH_PROFILES_PATH}")

        with open(AUTH_PROFILES_PATH, 'r') as f:
            return json.load(f)

    def _get_provider_config(self, key_name: str) -> Optional[dict]:
        """Get provider config from openclaw.json for a key."""
        provider_name = self.KEY_NAME_MAP.get(key_name)
        if not provider_name:
            return None

        providers = self.openclaw_config.get('models', {}).get('providers', {})
        return providers.get(provider_name)

    def _load_state(self) -> KeymasterState:
        """Load or initialize Keymaster state."""
        if STATE_PATH.exists():
            try:
                with open(STATE_PATH, 'r') as f:
                    data = json.load(f)
                    # Convert dict back to KeyStatus objects
                    key_status = {}
                    for k, v in data.get('key_status', {}).items():
                        key_status[k] = KeyStatus(
                            name=v['name'],
                            available=v['available'],
                            cooldown_until=v.get('cooldown_until'),
                            error_count=v.get('error_count', 0),
                            last_used=v.get('last_used'),
                            priority=v.get('priority', 99),
                            role=v.get('role', 'unknown')
                        )
                    return KeymasterState(
                        current_key=data.get('current_key', 'nvidia:primary'),
                        key_status=key_status,
                        last_rotation=data.get('last_rotation'),
                        rotation_count=data.get('rotation_count', 0),
                        compaction_history=data.get('compaction_history', [])
                    )
            except Exception as e:
                print(f"[Keymaster] Error loading state: {e}, initializing fresh state")

        # Initialize fresh state from auth profiles
        key_status = {}
        profiles = self.auth_profiles.get('profiles', {})

        for key_name, provider_id in self.KEY_NAME_MAP.items():
            profile = profiles.get(key_name, {})
            key_status[key_name] = KeyStatus(
                name=key_name,
                available=True,
                cooldown_until=None,
                error_count=0,
                last_used=None,
                priority=profile.get('priority', 99),
                role=profile.get('role', 'worker')
            )

        return KeymasterState(
            current_key='nvidia:primary',
            key_status=key_status,
            last_rotation=None,
            rotation_count=0,
            compaction_history=[]
        )

    def _save_state(self):
        """Save current state to disk."""
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Convert KeyStatus objects to dicts for JSON serialization
        state_dict = {
            'current_key': self.state.current_key,
            'key_status': {
                k: {
                    **asdict(v),
                    'provider': self.KEY_NAME_MAP.get(k)
                }
                for k, v in self.state.key_status.items()
            },
            'last_rotation': self.state.last_rotation,
            'rotation_count': self.state.rotation_count,
            'compaction_history': self.state.compaction_history[-100:]  # Keep last 100
        }

        with open(STATE_PATH, 'w') as f:
            json.dump(state_dict, f, indent=2)

    def get_current_key(self) -> str:
        """Get the current active key name (auth profile name)."""
        self._update_key_availability()
        return self.state.current_key

    def get_current_provider_id(self) -> str:
        """Get the current provider ID for OpenClaw (e.g., nvidia-key-1)."""
        return self.KEY_NAME_MAP.get(self.state.current_key, 'nvidia-key-1')

    def get_key_config(self, key_name: str) -> Optional[dict]:
        """Get auth profile configuration for a specific key."""
        return self.auth_profiles.get('profiles', {}).get(key_name)

    def get_key_api_key(self, key_name: str) -> Optional[str]:
        """Get the actual API key string for a key from openclaw.json."""
        provider_config = self._get_provider_config(key_name)
        return provider_config.get('apiKey') if provider_config else None

    def get_key_base_url(self, key_name: str) -> Optional[str]:
        """Get the base URL for a key's provider."""
        provider_config = self._get_provider_config(key_name)
        return provider_config.get('baseUrl') if provider_config else None

    def _update_key_availability(self):
        """Update availability status based on cooldowns."""
        current_time = time.time()

        for key_name, status in self.state.key_status.items():
            if status.cooldown_until and current_time >= status.cooldown_until:
                status.available = True
                status.cooldown_until = None

    def mark_key_cooldown(self, key_name: str, cooldown_seconds: Optional[int] = None):
        """Mark a key as cooling down (unavailable)."""
        if key_name not in self.state.key_status:
            return

        if cooldown_seconds is None:
            cooldown_seconds = self._get_cooldown_setting()

        self.state.key_status[key_name].available = False
        self.state.key_status[key_name].cooldown_until = time.time() + cooldown_seconds
        self.state.key_status[key_name].error_count += 1
        self._save_state()

    def _get_cooldown_setting(self) -> int:
        """Get cooldown duration from config."""
        return self.auth_profiles.get('keymaster', {}).get('cooldown_seconds', self.DEFAULT_COOLDOWN_SECONDS)

    def get_fallback_chain(self, from_key: Optional[str] = None) -> List[str]:
        """Get the fallback chain starting from a specific key from auth-profiles.json."""
        if from_key is None:
            from_key = self.state.current_key

        profile = self.get_key_config(from_key)
        if profile and 'fallback_chain' in profile:
            return profile['fallback_chain']

        # Default round-robin fallback
        keys = list(self.KEY_NAME_MAP.keys())
        idx = keys.index(from_key) if from_key in keys else 0
        return keys[idx+1:] + keys[:idx]

    def rotate_to_next_key(self, reason: str = "rotation") -> Optional[str]:
        """
        Rotate to the next available key in the fallback chain.

        Returns:
            Name of the new key, or None if no keys available.
        """
        self._update_key_availability()

        fallback_chain = self.get_fallback_chain(self.state.current_key)

        for next_key in fallback_chain:
            status = self.state.key_status.get(next_key)
            if status and status.available:
                # Mark current key as cooling down
                self.mark_key_cooldown(self.state.current_key)

                # Switch to new key
                old_key = self.state.current_key
                self.state.current_key = next_key
                self.state.key_status[next_key].last_used = time.time()
                self.state.last_rotation = time.time()
                self.state.rotation_count += 1

                # Log rotation event
                self._log_rotation(old_key, next_key, reason)
                self._save_state()

                return next_key

        # No available keys
        return None

    def _log_rotation(self, from_key: str, to_key: str, reason: str):
        """Log a key rotation event."""
        rotation_event = {
            'timestamp': time.time(),
            'from': from_key,
            'to': to_key,
            'reason': reason,
            'from_provider': self.KEY_NAME_MAP.get(from_key),
            'to_provider': self.KEY_NAME_MAP.get(to_key)
        }
        print(f"[Keymaster] Rotated {from_key} -> {to_key} ({reason})")

    def get_all_available_keys(self) -> List[str]:
        """Get list of all currently available keys."""
        self._update_key_availability()
        return [k for k, v in self.state.key_status.items() if v.available]

    def reset_all_keys(self):
        """Reset all keys to available state."""
        for key_name in self.KEY_NAME_MAP.keys():
            self.state.key_status[key_name].available = True
            self.state.key_status[key_name].cooldown_until = None
        self._save_state()

    def get_stats(self) -> dict:
        """Get usage statistics."""
        return {
            'current_key': self.state.current_key,
            'current_provider': self.get_current_provider_id(),
            'total_rotations': self.state.rotation_count,
            'available_keys': len(self.get_all_available_keys()),
            'total_keys': len(self.KEY_NAME_MAP),
            'key_details': {
                k: {
                    'available': v.available,
                    'error_count': v.error_count,
                    'cooldown_until': v.cooldown_until,
                    'role': v.role,
                    'provider': self.KEY_NAME_MAP.get(k)
                }
                for k, v in self.state.key_status.items()
            }
        }

    def get_key_role(self, key_name: str) -> str:
        """Get the role of a key (coordinator, strategist, etc.)."""
        status = self.state.key_status.get(key_name)
        return status.role if status else 'unknown'

    def is_coordinator_key(self, key_name: str) -> bool:
        """Check if a key can act as coordinator."""
        profile = self.get_key_config(key_name)
        return profile.get('can_act_as_coordinator', False) if profile else False


def main():
    """CLI interface for key pool manager."""
    import sys

    manager = KeyPoolManager()

    if len(sys.argv) < 2:
        print("Usage: key_pool_manager.py <action> [args]")
        print("Actions:")
        print("  current              - Show current key")
        print("  provider             - Show current provider ID")
        print("  rotate [reason]      - Rotate to next available key")
        print("  cooldown <key> [secs] - Put key on cooldown")
        print("  reset                - Reset all keys")
        print("  stats                - Show statistics")
        print("  available            - List available keys")
        print("  role <key>           - Show key role")
        sys.exit(1)

    action = sys.argv[1]

    if action == "current":
        print(manager.get_current_key())

    elif action == "provider":
        print(manager.get_current_provider_id())

    elif action == "rotate":
        reason = sys.argv[2] if len(sys.argv) > 2 else "manual"
        new_key = manager.rotate_to_next_key(reason)
        if new_key:
            print(f"Rotated to: {new_key} (provider: {manager.get_current_provider_id()})")
        else:
            print("No available keys!")
            sys.exit(1)

    elif action == "cooldown":
        if len(sys.argv) < 3:
            print("Usage: cooldown <key> [seconds]")
            sys.exit(1)
        key = sys.argv[2]
        secs = int(sys.argv[3]) if len(sys.argv) > 3 else None
        manager.mark_key_cooldown(key, secs)
        print(f"Key {key} on cooldown")

    elif action == "reset":
        manager.reset_all_keys()
        print("All keys reset")

    elif action == "stats":
        import pprint
        pprint.pprint(manager.get_stats())

    elif action == "available":
        keys = manager.get_all_available_keys()
        print("Available keys:", ", ".join(keys))

    elif action == "role":
        if len(sys.argv) < 3:
            print("Usage: role <key>")
            sys.exit(1)
        key = sys.argv[2]
        print(f"Role: {manager.get_key_role(key)}")
        print(f"Coordinator: {manager.is_coordinator_key(key)}")

    else:
        print(f"Unknown action: {action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
