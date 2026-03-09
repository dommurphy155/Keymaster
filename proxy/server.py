#!/usr/bin/env python3
"""
OpenClaw Proxy Server with Stream Relay Recovery

Transparent proxy that:
- Receives OpenAI-compatible requests from OpenClaw
- Rotates through NVIDIA API keys on rate limits
- Supports streaming responses with mid-stream recovery
- Uses round-robin key selection
- Per-token deduplication on content (not raw frames)
"""

import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional, Dict, List, Any
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from .key_manager import KeyManager, KeyState
from .stream_relay import StreamRelay
from .context_rebuilder import ContextRebuilder
from .deduplicator import TokenBuffer
from .config import CONFIG

# Logging helpers
def log_msg(level: str, msg: str):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] [{level}] {msg}")

def log_proxy(msg: str): log_msg("PROXY", msg)
def log_key(msg: str): log_msg("KEY", msg)
def log_req(msg: str): log_msg("REQ", msg)
def log_res(msg: str): log_msg("RES", msg)
def log_err(msg: str): log_msg("ERR", msg)
def log_stream(msg: str): log_msg("STREAM", msg)
def log_dedup(msg: str): log_msg("DEDUP", msg)

# Global state
key_manager: Optional[KeyManager] = None
http_client: Optional[httpx.AsyncClient] = None

# Metrics
class Metrics:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.total_requests = 0
        self.total_rate_limits = 0
        self.total_recoveries = 0
        self.total_tokens_streamed = 0

    async def inc(self, field: str):
        async with self._lock:
            current = getattr(self, field, 0)
            setattr(self, field, current + 1)

metrics = Metrics()

# Constants
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global key_manager, http_client
    log_proxy("Starting up...")

    key_manager = KeyManager()
    timeout = httpx.Timeout(120.0, connect=30.0, read=120.0, write=30.0)
    http_client = httpx.AsyncClient(
        timeout=timeout,
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        follow_redirects=True,
        http2=False
    )
    log_proxy(f"Ready with {len(key_manager.keys)} keys")

    yield

    log_proxy("Shutting down...")
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="OpenClaw Keymaster Proxy",
    description="Transparent API key rotation with stream relay recovery",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RateLimitError(Exception):
    pass


class StreamComplete(Exception):
    """Raised when stream reaches [DONE]"""
    pass


@app.get("/health")
async def health_check():
    global key_manager, metrics
    if not key_manager:
        raise HTTPException(status_code=503, detail="Proxy not ready")

    status = key_manager.get_status()
    return {
        "status": "ok",
        "timestamp": time.time(),
        "total_requests": metrics.total_requests,
        "total_rate_limits": metrics.total_rate_limits,
        "total_recoveries": metrics.total_recoveries,
        "total_tokens_streamed": metrics.total_tokens_streamed,
        **status
    }


async def stream_from_key(
    relay: StreamRelay,
    key: KeyState,
    http_client: httpx.AsyncClient,
    target_url: str,
    headers: dict,
    body: dict,
    dedup_buffer: TokenBuffer,
    is_recovery: bool = False,
    request_id: str = "unknown"
) -> None:
    """
    Stream from a single key to the relay.

    Parses SSE frames, extracts content, applies dedup if recovery.
    Raises RateLimitError on 429, StreamComplete on [DONE].
    """
    # Prepare headers
    request_headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
    request_headers["Authorization"] = f"Bearer {key.key}"
    request_headers.pop("host", None)
    request_headers.pop("content-length", None)
    request_headers.pop("transfer-encoding", None)

    log_stream(f"[{request_id}] → {key.name} ({'recovery' if is_recovery else 'initial'})")

    buffer = ""  # Buffer for incomplete SSE lines

    try:
        async with http_client.stream(
            "POST", target_url, headers=request_headers, json=body
        ) as response:
            # Check for pre-stream errors
            if response.status_code == 429:
                cooldown = 60
                retry_after = response.headers.get("retry-after")
                if retry_after:
                    try:
                        cooldown = int(retry_after)
                    except ValueError:
                        pass
                key_manager.mark_cooldown(key.name, cooldown)
                log_key(f"{key.name} → cooling {cooldown}s (429)")
                raise RateLimitError(f"Rate limited on {key.name}")

            if response.status_code in [502, 503, 504]:
                log_err(f"Gateway {response.status_code} on {key.name}")
                raise RateLimitError(f"Gateway error {response.status_code}")

            response.raise_for_status()

            # Stream content
            log_stream(f"[{request_id}] upstream_stream_started")
            chunk_count = 0
            token_count = 0

            async for chunk in response.aiter_text():
                chunk_count += 1
                if chunk_count == 1:
                    log_stream(f"[{request_id}] first_chunk_received: {len(chunk)} bytes")
                buffer += chunk

                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if not line:
                        # Empty line - end of SSE frame
                        continue

                    if line.startswith(":"):
                        # SSE comment, ignore
                        continue

                    if line.startswith("data: "):
                        data = line[6:]

                        # Check for done marker
                        if data.strip() == "[DONE]":
                            await relay.send_done()
                            raise StreamComplete()

                        # Parse JSON and extract content
                        try:
                            parsed = json.loads(data)
                            if "choices" in parsed and len(parsed["choices"]) > 0:
                                choice = parsed["choices"][0]

                                if "delta" in choice and "content" in choice["delta"]:
                                    content = choice["delta"]["content"]
                                    if content:
                                        # Deduplicate if this is a recovery stream
                                        if is_recovery:
                                            deduped = dedup_buffer.dedup(content)
                                            if deduped:
                                                await relay.send_frame(deduped)
                                                await metrics.inc("total_tokens_streamed")
                                            else:
                                                log_dedup(f"Skipped duplicate: '{content[:30]}...'")
                                        else:
                                            # Normal stream - send immediately
                                            await relay.send_frame(content)
                                            dedup_buffer.add_sent(content)
                                            await metrics.inc("total_tokens_streamed")

                                        # Track in relay for recovery
                                        relay.append_content(content)
                                        token_count += 1
                                        if token_count <= 3:
                                            log_stream(f"[{request_id}] token_{token_count}: '{content[:30]}...'")
                        except json.JSONDecodeError:
                            log_err(f"[{request_id}] Invalid JSON in SSE: {data[:100]}")
                            continue

            # After stream ends, check if we have remaining buffer
            log_stream(f"[{request_id}] stream_ended: chunks={chunk_count}, tokens={token_count}")
            if buffer.strip():
                log_stream(f"[{request_id}] unprocessed_buffer: {len(buffer)} chars")

    except httpx.ReadTimeout:
        log_err(f"Read timeout on {key.name}")
        key_manager.mark_cooldown(key.name, 30)
        raise RateLimitError(f"Read timeout on {key.name}")

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            key_manager.mark_cooldown(key.name, 60)
            raise RateLimitError(f"Rate limited on {key.name}")
        raise


async def send_keepalives(relay: StreamRelay, interval: float = 0.5):
    """Send keepalive pings during key transitions."""
    try:
        while True:
            await asyncio.sleep(interval)
            await relay.send_keepalive()
    except asyncio.CancelledError:
        pass


async def stream_with_recovery(
    relay: StreamRelay,
    http_client: httpx.AsyncClient,
    target_url: str,
    headers: dict,
    original_body: dict,
    request_id: str
) -> None:
    """
    Main streaming logic with recovery.

    Handles:
    - Round-robin key selection with atomic acquisition
    - Mid-stream failover
    - Per-token deduplication
    - Keepalives during transitions
    - Proper key release on completion/failure
    """
    global key_manager

    log_req(f"[{request_id}] stream_with_recovery started")

    dedup_buffer = TokenBuffer(max_chars=CONFIG.buffer_max_chars)
    keys_used = set()
    keys_acquired = []  # Track acquired keys for proper release
    tokens_forwarded = 0

    # Get initial key
    key = await key_manager.get_key_for_request()
    log_req(f"[{request_id}] initial_key={key.name if key else 'None'}")

    if not key:
        # All keys cooling, wait briefly
        log_req(f"[{request_id}] all_keys_cooling, waiting...")
        await asyncio.sleep(2)
        key = await key_manager.get_key_for_request()
        if not key:
            log_err(f"[{request_id}] no_keys_available_after_wait")
            await relay.send_frame("Error: All API keys are rate limited. Please try again in a minute.")
            await relay.close()
            return

    while True:
        if key.name in keys_used:
            # We've cycled through keys
            log_err(f"[{request_id}] all_keys_exhausted")
            await relay.send_frame("Error: All keys exhausted for this request.")
            await relay.close()
            # Release all acquired keys
            for k in keys_acquired:
                await k.release()
                log_key(f"{k.name} released (exhausted)")
            return

        keys_used.add(key.name)
        keys_acquired.append(key)
        relay.add_key_used(key.name)

        try:
            # Build request body
            if len(keys_used) == 1:
                # First attempt - use original body
                body = original_body
            else:
                # Recovery attempt - rebuild with continuation
                partial = relay.get_partial_content()
                messages = ContextRebuilder.build_recovery_prompt(
                    original_body.get("messages", []),
                    partial,
                    max_chars=CONFIG.max_recovery_context
                )
                body = original_body.copy()
                body["messages"] = messages
                log_stream(f"Recovery: using {len(partial)} chars context")

            # Stream from this key
            await stream_from_key(
                relay, key, http_client, target_url, headers, body,
                dedup_buffer, is_recovery=(len(keys_used) > 1), request_id=request_id
            )

            # Stream completed successfully - release all keys
            log_stream(f"✓ Completed using {key.name}")
            await relay.close()
            for k in keys_acquired:
                await k.release()
                log_key(f"{k.name} released (success)")
            return

        except StreamComplete:
            # Normal completion - release all keys
            log_stream(f"✓ Stream complete via {key.name}")
            await relay.close()
            for k in keys_acquired:
                await k.release()
                log_key(f"{k.name} released (complete)")
            return

        except RateLimitError as e:
            log_key(f"Rate limit on {key.name}: {e}")
            await metrics.inc("total_rate_limits")

            # Get next key for retry
            key = await key_manager.get_next_available_key(exclude_keys=keys_used)

            if not key:
                # No more keys available - release all acquired keys
                log_err(f"[{request_id}] no_more_keys_available")
                await relay.send_frame("Error: All keys rate limited. Request cannot complete.")
                await relay.close()
                for k in keys_acquired:
                    await k.release()
                    log_key(f"{k.name} released (no more keys)")
                return

            # Enter transition mode
            relay.mark_transitioning(True)
            keepalive_task = asyncio.create_task(
                send_keepalives(relay, interval=CONFIG.keepalive_interval)
            )

            log_stream(f"→ Switching to {key.name}")
            await metrics.inc("total_recoveries")

            # Brief delay for key to stabilize
            await asyncio.sleep(0.5)

            keepalive_task.cancel()
            relay.mark_transitioning(False)

            # Continue loop with new key
            continue

        except Exception as e:
            log_err(f"Unexpected error with {key.name}: {e}")
            await metrics.inc("total_rate_limits")

            # Try next key
            key = await key_manager.get_next_available_key(exclude_keys=keys_used)
            if not key:
                # No more keys available - release all acquired keys
                log_err(f"[{request_id}] request_failed_final")
                await relay.send_frame(f"Error: Request failed after {len(keys_used)} attempts.")
                await relay.close()
                for k in keys_acquired:
                    await k.release()
                    log_key(f"{k.name} released (failed)")
                return
            continue


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_request(request: Request, path: str):
    """
    Main proxy endpoint with stream relay recovery.
    """
    global key_manager, http_client, metrics

    if not key_manager or not http_client:
        raise HTTPException(status_code=503, detail="Proxy not initialized")

    await metrics.inc("total_requests")

    # Build target URL
    clean_path = path
    if clean_path.startswith("v1/"):
        clean_path = clean_path[3:]
    target_url = f"{NVIDIA_BASE_URL}/{clean_path}"

    # Get headers
    headers = dict(request.headers)

    # Get body
    body = None
    if request.method in ["POST", "PUT"]:
        try:
            body = await request.json()
        except:
            body = await request.body()

    is_streaming = body and isinstance(body, dict) and body.get("stream", False)
    model = body.get("model", "unknown") if body else "unknown"

    # Generate request ID for tracking
    request_id = str(uuid.uuid4())[:8]
    log_req(f"[{request_id}] → {model} (stream={is_streaming})")

    if is_streaming and request.method == "POST":
        # Create relay for this request
        relay = StreamRelay(max_buffer_chars=CONFIG.buffer_max_chars)
        relay.request_id = request_id
        relay.conversation_history = body.get("messages", [])
        relay.original_model = model
        relay.original_body = body

        log_req(f"[{request_id}] starting background stream task")

        # Start streaming in background with error handling
        async def run_stream():
            try:
                await stream_with_recovery(
                    relay, http_client, target_url, headers, body, request_id
                )
            except Exception as e:
                log_err(f"[{request_id}] Background task failed: {e}")
                await relay.send_frame(f"Error: Stream processing failed: {str(e)[:100]}")
                await relay.close()

        asyncio.create_task(run_stream())

        # Return streaming response
        return StreamingResponse(
            relay.get_output_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

    else:
        # Non-streaming - use simple key rotation
        return await handle_non_streaming(request, target_url, headers, body)


async def handle_non_streaming(
    request: Request,
    target_url: str,
    headers: dict,
    body: Any
) -> Response:
    """Handle non-streaming requests with key rotation and proper release."""
    global key_manager, http_client

    max_attempts = CONFIG.max_key_switches
    attempted = 0
    last_error = None
    keys_acquired = []  # Track acquired keys for proper release

    while attempted < max_attempts:
        key = await key_manager.get_key_for_request()
        if not key:
            # Release any acquired keys before failing
            for k in keys_acquired:
                await k.release()
            raise HTTPException(
                status_code=503,
                detail="All keys cooling",
                headers={"Retry-After": str(key_manager.get_earliest_cooldown() + 1)}
            )

        attempted += 1
        keys_acquired.append(key)

        # Prepare request
        request_headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
        request_headers["Authorization"] = f"Bearer {key.key}"
        request_headers.pop("host", None)

        try:
            response = await http_client.request(
                request.method,
                target_url,
                headers=request_headers,
                json=body if body else None
            )

            if response.status_code == 429:
                key_manager.mark_cooldown(key.name, 60)
                await key.release()
                last_error = "Rate limited"
                continue

            response.raise_for_status()

            # Success - release the key before returning
            await key.release()

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers={
                    k: v for k, v in response.headers.items()
                    if k.lower() not in ["content-encoding", "transfer-encoding", "connection"]
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                key_manager.mark_cooldown(key.name, 60)
                await key.release()
                last_error = "Rate limited"
                continue
            # Release key before raising
            await key.release()
            raise HTTPException(status_code=e.response.status_code, detail=str(e))

        except Exception as e:
            last_error = str(e)
            await key.release()
            continue

    # All attempts failed - release all acquired keys
    for k in keys_acquired:
        await k.release()

    raise HTTPException(
        status_code=503,
        detail=f"All keys exhausted. Last error: {last_error}"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8787,
        log_level="info",
        loop="uvloop"
    )
