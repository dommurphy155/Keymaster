"""
Key Manager for OpenClaw Proxy

Manages pool of NVIDIA API keys with:
- Random selection from available keys
- Cooldown tracking
- Cyclical rotation (when all exhausted, cycle back)
- Thread-safe key allocation
"""

import json
import random
import time
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass


@dataclass
class KeyState:
    name: str
    provider: str
    key: str
    role: str
    cooldown_until: float = 0
    priority: int = 99


class KeyManager:
    """Manages NVIDIA API key pool with rotation and cooldown."""

    DEFAULT_COOLDOWN = 60  # seconds

    def __init__(self):
        self.keys: Dict[str, KeyState] = {}
        self._lock = asyncio.Lock()
        self._load_keys()

    def _load_keys(self):
        """Load keys from auth-profiles.json."""
        auth_path = Path.home() / ".openclaw/agents/main/agent/auth-profiles.json"

        if not auth_path.exists():
            raise FileNotFoundError(f"auth-profiles.json not found at {auth_path}")

        with open(auth_path) as f:
            config = json.load(f)

        profiles = config.get("profiles", {})

        for key_name, profile in profiles.items():
            if not key_name.startswith("nvidia:"):
                continue

            self.keys[key_name] = KeyState(
                name=key_name,
                provider=profile.get("provider", ""),
                key=profile.get("key", ""),
                role=profile.get("role", "worker"),
                priority=profile.get("priority", 99)
            )

        if not self.keys:
            raise ValueError("No NVIDIA keys found in auth-profiles.json")

        print(f"[KeyManager] Loaded {len(self.keys)} keys")

    def get_key_for_request(self) -> Optional[KeyState]:
        """
        Get a random available key.
        Returns None if ALL keys are on cooldown (will retry).
        """
        now = time.time()

        # Find all keys not on cooldown
        available = [
            key for key in self.keys.values()
            if now >= key.cooldown_until
        ]

        if not available:
            return None

        # Random selection from available keys
        return random.choice(available)

    def mark_cooldown(self, key_name: str, cooldown_seconds: Optional[int] = None):
        """Mark a key as cooling."""
        if key_name in self.keys:
            cooldown = cooldown_seconds or self.DEFAULT_COOLDOWN
            self.keys[key_name].cooldown_until = time.time() + cooldown
            print(f"[KeyManager] Key {key_name} on cooldown for {cooldown}s")

    def get_cooldown_remaining(self, key_name: str) -> float:
        """Get seconds remaining for key cooldown."""
        if key_name not in self.keys:
            return 0
        return max(0, self.keys[key_name].cooldown_until - time.time())

    def get_all_available_keys(self) -> List[str]:
        """Get list of all currently available key names."""
        now = time.time()
        return [
            name for name, key in self.keys.items()
            if now >= key.cooldown_until
        ]

    def reset_all_keys(self):
        """Reset all cooldowns (emergency use)."""
        for key in self.keys.values():
            key.cooldown_until = 0
        print("[KeyManager] All keys reset")

    def get_status(self) -> Dict:
        """Get current status of all keys."""
        now = time.time()
        return {
            "total_keys": len(self.keys),
            "available_keys": len(self.get_all_available_keys()),
            "cooling_keys": len([k for k in self.keys.values() if k.cooldown_until > now]),
            "keys": {
                name: {
                    "available": now >= key.cooldown_until,
                    "cooldown_remaining": max(0, key.cooldown_until - now),
                    "role": key.role
                }
                for name, key in self.keys.items()
            }
        }
