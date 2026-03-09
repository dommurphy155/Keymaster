"""
Stream Relay Configuration

Central configuration for proxy behavior.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class RelayConfig:
    """Configuration for stream relay behavior."""

    # Token buffer for deduplication (characters, not tokens)
    buffer_max_chars: int = 800

    # Max key switches per request before giving up
    max_key_switches: int = 3

    # Keepalive interval during key switches (seconds)
    keepalive_interval: float = 0.5

    # Deduplication suffix sizes to check (largest first)
    dedup_suffix_sizes: List[int] = None

    # Max partial response to include in recovery prompt (characters)
    max_recovery_context: int = 4000

    # Cooldown duration after rate limit (seconds)
    cooldown_seconds: int = 60

    # Recovery transition timeout (seconds)
    recovery_timeout: float = 30.0

    # Round-robin: max concurrent requests per key
    key_concurrency_limit: int = 5

    # SSE queue size
    queue_size: int = 100

    # Timeout for SSE generator (seconds)
    generator_timeout: float = 0.5

    def __post_init__(self):
        if self.dedup_suffix_sizes is None:
            self.dedup_suffix_sizes = [800, 600, 400, 200, 100, 50, 30, 15, 5]


# Global config instance
CONFIG = RelayConfig()
