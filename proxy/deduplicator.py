"""
Deduplicator for Token Overlap Detection

Simple suffix matching to skip repeated content when switching keys.
Operates on content text only, not raw SSE frames.
"""

from typing import Tuple


class Deduplicator:
    """
    Detects overlapping content between original stream and retry.
    Uses simple suffix matching - no embeddings or complex algorithms.
    """

    # Suffix sizes to check, from largest to smallest
    SUFFIX_SIZES = [800, 600, 400, 200, 100, 50, 30, 15, 5]

    @classmethod
    def find_overlap(cls, already_sent: str, new_content: str) -> int:
        """
        Find how many leading characters of new_content overlap with
        the end of already_sent.

        Returns: number of characters to skip (0 if no overlap)

        Example:
            already_sent = "return revenue - cost"
            new_content = "return revenue - cost - tax"
            returns: 21 (length of overlap)

            already_sent = "return revenue - cost"
            new_content = " - tax"
            returns: 0 (no overlap)
        """
        if not already_sent or not new_content:
            return 0

        # Try largest suffixes first
        for size in cls.SUFFIX_SIZES:
            if size > len(already_sent):
                continue
            if size > len(new_content):
                continue

            # Get suffix of already_sent
            suffix = already_sent[-size:]

            # Check if new_content starts with this suffix
            if new_content.startswith(suffix):
                return size

        # No overlap found
        return 0

    @classmethod
    def dedup_token(cls, already_sent: str, token: str) -> Tuple[str, int]:
        """
        Deduplicate a single token against already-sent content.

        Returns:
            (new_text, overlap_size)
            new_text: text to send (may be empty)
            overlap_size: how much was skipped

        Example:
            already_sent = "return revenue"
            token = "revenue - cost"
            returns: (" - cost", 7)  # 'revenue' was skipped
        """
        overlap = cls.find_overlap(already_sent, token)

        if overlap > 0:
            new_text = token[overlap:]
            return new_text, overlap
        else:
            return token, 0


class TokenBuffer:
    """
    Per-token buffer for streaming deduplication.
    Accumulates content and deduplicates token-by-token.
    """

    def __init__(self, max_chars: int = 800):
        self.sent_content = ""  # Everything already sent downstream
        self.max_chars = max_chars

    def add_sent(self, text: str):
        """Mark text as sent downstream."""
        self.sent_content += text
        # Trim to prevent unbounded growth
        if len(self.sent_content) > self.max_chars:
            self.sent_content = self.sent_content[-self.max_chars:]

    def dedup(self, new_text: str) -> str:
        """
        Deduplicate new text against sent content.
        Returns only the non-overlapping portion.
        """
        deduped, overlap = Deduplicator.dedup_token(self.sent_content, new_text)

        if overlap > 0:
            # Track what we're about to send
            self.add_sent(deduped)
            return deduped
        else:
            # No overlap, send everything
            self.add_sent(new_text)
            return new_text

    def get_sent_content(self) -> str:
        """Get all content sent so far (for recovery prompt)."""
        return self.sent_content
