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
from datetime import datetime


def log_key(msg: str):
    """Log with timestamp."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] [KEY] {msg}")


@dataclass
class KeyState:
    name: str
    provider: str
    key: str
    role: str
    cooldown_until: float = 0
    priority: int = 99
    semaphore: asyncio.Semaphore = None  # Concurrency limit per key
    active_requests: int = 0  # Track active request count
    _lock: asyncio.Lock = None  # Lock for updating active_requests

    def __post_init__(self):
        if self.semaphore is None:
            # Allow 2 concurrent requests per key (reduced from 5 for stability)
            self.semaphore = asyncio.Semaphore(2)
        if self._lock is None:
            self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Atomically acquire the key semaphore and increment active count."""
        acquired = await self.semaphore.acquire()
        if acquired:
            async with self._lock:
                self.active_requests += 1
        return acquired

    async def release(self):
        """Release the key semaphore and decrement active count."""
        async with self._lock:
            self.active_requests = max(0, self.active_requests - 1)
        self.semaphore.release()

    def is_available(self, now: float = None) -> bool:
        """Check if key is available (not cooling and not at capacity)."""
        if now is None:
            now = time.time()
        if self.cooldown_until > now:
            return False
        # Check if we can acquire without blocking (has capacity)
        # locked() returns True if semaphore counter is 0 (can't acquire)
        return not self.semaphore.locked()


class KeyManager:
    """Manages NVIDIA API key pool with rotation and cooldown."""

    DEFAULT_COOLDOWN = 60  # seconds

    def __init__(self):
        self.keys: Dict[str, KeyState] = {}
        self._lock = asyncio.Lock()
        self._key_index = 0  # Round-robin pointer
        self._key_list: List[str] = []  # Ordered list of key names
        self._index_lock = asyncio.Lock()  # Separate lock for index
        self._load_keys()

    async def _get_next_key_index(self) -> int:
        """Get next key index for round-robin selection (thread-safe)."""
        async with self._index_lock:
            idx = self._key_index
            self._key_index = (self._key_index + 1) % len(self._key_list)
            return idx

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

        # Build ordered list for round-robin
        self._key_list = sorted(self.keys.keys())
        log_key(f"Loaded {len(self.keys)} keys")

    async def get_key_for_request(self) -> Optional[KeyState]:
        """
        Get next available key using round-robin with atomic acquisition.
        Returns None if ALL keys are on cooldown or at capacity.
        """
        now = time.time()

        # Try each key in round-robin order
        for _ in range(len(self._key_list)):
            idx = await self._get_next_key_index()
            key_name = self._key_list[idx]
            key = self.keys[key_name]

            # Skip if cooling
            if now < key.cooldown_until:
                continue

            # Try to acquire (atomically checks capacity)
            if await key.acquire():
                log_key(f"{key_name} acquired (active: {key.active_requests})")
                return key

        # No keys available with capacity
        return None

    async def get_next_available_key(self, exclude_keys: set = None) -> Optional[KeyState]:
        """
        Get next available key for recovery with atomic acquisition.
        Optionally excludes certain keys.
        """
        now = time.time()
        exclude_keys = exclude_keys or set()

        # Try round-robin order first
        for _ in range(len(self._key_list)):
            idx = await self._get_next_key_index()
            key_name = self._key_list[idx]
            key = self.keys[key_name]

            if key_name in exclude_keys:
                continue
            if now < key.cooldown_until:
                continue

            # Try to acquire
            if await key.acquire():
                log_key(f"{key_name} acquired for recovery (active: {key.active_requests})")
                return key

        # Fallback: any available key not in exclude
        for name in self._key_list:
            if name in exclude_keys:
                continue
            key = self.keys[name]
            if now < key.cooldown_until:
                continue
            if await key.acquire():
                log_key(f"{name} acquired for recovery (active: {key.active_requests})")
                return key

        return None

    async def get_key_round_robin(self) -> Optional[KeyState]:
        """
        Get next available key using round-robin.
        Returns None if ALL keys are on cooldown.
        """
        now = time.time()
        num_keys = len(self._key_list)

        if num_keys == 0:
            return None

        # Try each key in round-robin order
        for _ in range(num_keys):
            idx = await self._get_next_key_index()
            key_name = self._key_list[idx]
            key = self.keys.get(key_name)

            if key and now >= key.cooldown_until:
                return key

        # All keys cooling
        return None

    def mark_cooldown(self, key_name: str, cooldown_seconds: Optional[int] = None):
        """Mark a key as cooling."""
        if key_name in self.keys:
            cooldown = cooldown_seconds or self.DEFAULT_COOLDOWN
            self.keys[key_name].cooldown_until = time.time() + cooldown
            log_key(f"{key_name} → cooling {cooldown}s")

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

    def get_earliest_cooldown(self) -> float:
        """Get seconds until the earliest key is available."""
        now = time.time()
        earliest = float('inf')
        for key in self.keys.values():
            if key.cooldown_until > now:
                earliest = min(earliest, key.cooldown_until - now)
        return earliest if earliest != float('inf') else 0

    def reset_all_keys(self):
        """Reset all cooldowns (emergency use)."""
        for key in self.keys.values():
            key.cooldown_until = 0
        log_key("All keys reset")

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
