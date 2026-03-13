"""
Stream Relay for OpenClaw Proxy

Maintains SSE connection to OpenClaw while switching keys upstream.
Handles token buffering, keepalives, and graceful completion.
"""

import asyncio
import json
import uuid
from collections import deque
from typing import Optional, List


class TokenBuffer:
    """
    Rolling buffer of content tokens (not raw SSE frames).
    Stores last ~800 characters for deduplication.
    """

    def __init__(self, max_chars: int = 800):
        self.max_chars = max_chars
        self.content = ""  # Accumulated content text only

    def append(self, text: str):
        """Add content text (not raw frames)."""
        self.content += text
        # Trim to max size from end
        if len(self.content) > self.max_chars:
            self.content = self.content[-self.max_chars:]

    def get_content(self) -> str:
        """Get accumulated content for recovery prompt."""
        return self.content

    def get_suffix(self, length: int) -> str:
        """Get last N characters for overlap detection."""
        if length > len(self.content):
            return self.content
        return self.content[-length:]


class StreamRelay:
    """
    Relay that maintains SSE connection to OpenClaw
    while upstream keys may fail and be replaced.
    """

    def __init__(self, max_buffer_chars: int = 800):
        self.request_id = str(uuid.uuid4())
        self.output_queue = asyncio.Queue()
        self.token_buffer = TokenBuffer(max_chars=max_buffer_chars)
        self.is_transitioning = False
        self.is_complete = False
        self.conversation_history = []
        self.original_model = ""
        self.original_body = {}

        # Metrics
        self.tokens_sent = 0
        self.chunks_received = 0
        self.keys_used = []

    async def get_output_generator(self):
        """
        Generator for StreamingResponse.
        Yields SSE frames to OpenClaw.
        """
        while True:
            try:
                # Wait for chunk with timeout to send keepalives
                chunk = await asyncio.wait_for(
                    self.output_queue.get(),
                    timeout=0.5
                )

                if chunk is None:
                    # Sentinel for end of stream
                    break

                if chunk == "KEEPALIVE":
                    # Send SSE comment to keep connection alive
                    yield b":ping\n\n"
                    continue

                # Regular SSE frame
                yield chunk

            except asyncio.TimeoutError:
                # Send keepalive during idle periods
                if self.is_transitioning:
                    yield b":ping\n\n"
                continue

            except Exception as e:
                # Log error but don't crash
                print(f"[RELAY] Generator error: {e}")
                break

    async def send_frame(self, content: str = None, tool_calls: list = None, finish_reason: str = None, full_delta: dict = None):
        """
        Send a properly formatted SSE data frame.
        Supports content text, tool_calls, or a full delta dict.
        """
        if full_delta:
            # Send the complete delta as provided by upstream
            frame_data = {"choices": [{"delta": full_delta}]}
            if finish_reason:
                frame_data["choices"][0]["finish_reason"] = finish_reason
            frame = f'data: {json.dumps(frame_data)}\n\n'
            await self.output_queue.put(frame.encode())
            self.tokens_sent += 1
            return

        # Build delta from components
        delta = {}
        if content:
            delta["content"] = content
        if tool_calls:
            delta["tool_calls"] = tool_calls

        if not delta:
            return

        frame_data = {"choices": [{"delta": delta}]}
        if finish_reason:
            frame_data["choices"][0]["finish_reason"] = finish_reason

        frame = f'data: {json.dumps(frame_data)}\n\n'
        await self.output_queue.put(frame.encode())
        self.tokens_sent += 1

    async def send_done(self):
        """Send completion marker."""
        await self.output_queue.put(b'data: [DONE]\n\n')
        self.is_complete = True

    async def send_keepalive(self):
        """Queue a keepalive ping."""
        await self.output_queue.put("KEEPALIVE")

    def append_content(self, text: str):
        """Track content for recovery (raw text, not frames)."""
        self.token_buffer.append(text)

    def get_partial_content(self) -> str:
        """Get accumulated content for recovery prompt."""
        return self.token_buffer.get_content()

    def mark_transitioning(self, transitioning: bool):
        """Mark if we're in key-switch transition."""
        self.is_transitioning = transitioning

    def mark_complete(self):
        """Mark stream as complete."""
        self.is_complete = True

    def add_key_used(self, key_name: str):
        """Track which keys were used."""
        self.keys_used.append(key_name)

    async def close(self):
        """Signal end of stream."""
        # Send SSE completion marker before sentinel so client knows stream is done
        if not self.is_complete:
            await self.send_done()
        await self.output_queue.put(None)
