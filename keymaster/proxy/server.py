#!/usr/bin/env python3
"""
OpenClaw Proxy Server

Transparent proxy that:
- Receives OpenAI-compatible requests from OpenClaw
- Rotates through NVIDIA API keys on rate limits
- Supports streaming responses
- Never resets cooldown state (waits for earliest expiry)
"""

import asyncio
import json
import random
import time
from typing import AsyncGenerator, Optional, Dict
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

import httpx
import requests
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from .key_manager import KeyManager, KeyState

# Thread pool for running sync requests library
thread_pool = ThreadPoolExecutor(max_workers=20)

# Global key manager
key_manager: Optional[KeyManager] = None
http_client: Optional[httpx.AsyncClient] = None

# Thread-safe metrics class
class Metrics:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.total_requests = 0
        self.total_rate_limits = 0
        self.total_streaming_requests = 0
        self.total_streaming_errors = 0

    async def inc(self, field: str):
        """Increment a metric field atomically."""
        async with self._lock:
            current = getattr(self, field, 0)
            setattr(self, field, current + 1)

# Global metrics instance
metrics = Metrics()

# NVIDIA API base URL
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Retry configuration
MAX_RETRIES = 5
BACKOFF_DELAYS = [0.5, 1, 2, 4, 8]  # Exponential backoff


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    global key_manager, http_client

    print("[Proxy] Starting up...")
    key_manager = KeyManager()
    # Use a more robust timeout configuration
    timeout = httpx.Timeout(120.0, connect=30.0, read=120.0, write=30.0)
    # Increased connection pool for parallel tool calls (200 max, 50 keepalive)
    http_client = httpx.AsyncClient(
        timeout=timeout,
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        follow_redirects=True,
        http2=False  # Disable HTTP/2 to avoid content-length issues
    )
    print(f"[Proxy] Ready with {len(key_manager.keys)} keys")

    yield

    print("[Proxy] Shutting down...")
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="OpenClaw Keymaster Proxy",
    description="Transparent API key rotation for OpenClaw",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware (OpenClaw runs locally)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)




async def stream_response(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    body: dict,
    key: KeyState
) -> AsyncGenerator[bytes, None]:
    """
    Stream response from NVIDIA API.
    Transparent passthrough - no buffering.
    Logs errors but cannot recover mid-stream.
    """
    # Increment streaming request counter
    await metrics.inc("total_streaming_requests")

    # Replace auth header with the selected key (remove any existing auth first)
    headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
    headers["Authorization"] = f"Bearer {key.key}"

    # Remove host header (will be set by httpx)
    headers.pop("host", None)

    # Remove content-length and transfer-encoding for streaming
    # These cause "Too much data for declared Content-Length" errors
    headers.pop("content-length", None)
    headers.pop("transfer-encoding", None)
    headers.pop("Content-Length", None)
    headers.pop("Transfer-Encoding", None)

    chunks_sent = 0
    try:
        # Use unlimited read timeout for streaming - LLM can take very long between chunks
        # Only apply timeout to connection establishment, not to waiting for chunks
        stream_timeout = httpx.Timeout(None, connect=60.0, read=None, write=30.0)
        async with client.stream(
            "POST",
            url,
            headers=headers,
            json=body,
            timeout=stream_timeout
        ) as response:
            # Check for rate limit (before streaming starts - can still retry)
            if response.status_code == 429:
                cooldown = 60
                retry_after = response.headers.get("retry-after")
                if retry_after:
                    try:
                        cooldown = int(retry_after)
                    except ValueError:
                        pass
                elif response.headers.get("x-ratelimit-reset"):
                    try:
                        reset_time = int(response.headers.get("x-ratelimit-reset"))
                        cooldown = max(0, reset_time - int(time.time()))
                    except ValueError:
                        pass

                key_manager.mark_cooldown(key.name, cooldown)
                raise RateLimitError(f"Rate limited on {key.name}")

            # Forward status and headers (except auth-related)
            response.raise_for_status()

            # Stream chunks directly without modification
            async for chunk in response.aiter_raw():
                yield chunk
                chunks_sent += 1

    except RateLimitError:
        raise  # Let caller retry with new key
    except httpx.ReadTimeout as e:
        # Read timeout during streaming - treat like a rate limit and retry
        await metrics.inc("total_streaming_errors")
        print(f"[Proxy] Read timeout after {chunks_sent} chunks on {key.name}: {e}")
        # Mark key as cooling briefly (30s) - might be temporary network issue
        key_manager.mark_cooldown(key.name, 30)
        raise RateLimitError(f"Read timeout on {key.name}")
    except Exception as e:
        # Log streaming error but cannot recover
        await metrics.inc("total_streaming_errors")
        print(f"[Proxy] Stream error after {chunks_sent} chunks: {e}")
        raise  # Re-raise to terminate stream


class RateLimitError(Exception):
    pass


@app.get("/health")
async def health_check():
    """Health check endpoint with metrics."""
    global key_manager, metrics
    if not key_manager:
        raise HTTPException(status_code=503, detail="Proxy not ready")

    status = key_manager.get_status()
    return {
        "status": "ok",
        "timestamp": time.time(),
        "total_requests": metrics.total_requests,
        "total_rate_limits": metrics.total_rate_limits,
        "total_streaming_requests": metrics.total_streaming_requests,
        "total_streaming_errors": metrics.total_streaming_errors,
        **status
    }


# Simple in-memory key affinity - tracks which key was last used
# This helps parallel tool calls from the same batch use the same key
_key_usage_history: Dict[str, str] = {}
_last_key_used: Optional[str] = None


async def try_acquire_key(key: KeyState, timeout: float = 0.1) -> bool:
    """
    Try to acquire a key's semaphore without blocking.
    Returns True if acquired, False if key is busy.
    """
    try:
        await asyncio.wait_for(key.semaphore.acquire(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_request(request: Request, path: str):
    """
    Main proxy endpoint - forwards all requests to NVIDIA API
    with automatic key rotation on rate limits.

    Strategy:
    1. Try keys in round-robin fashion (with affinity for last used)
    2. If key busy (semaphore full), immediately try next key
    3. Only rotate on rate limit (429) - not on "busy"
    4. If all keys cooling, return 503 immediately so OpenClaw retries
    """
    global key_manager, http_client, metrics, _last_key_used

    if not key_manager or not http_client:
        raise HTTPException(status_code=503, detail="Proxy not initialized")

    # Increment total request counter (async-safe)
    await metrics.inc("total_requests")

    # Build target URL
    clean_path = path
    if clean_path.startswith("v1/"):
        clean_path = clean_path[3:]
    target_url = f"{NVIDIA_BASE_URL}/{clean_path}"

    # Get headers
    headers = dict(request.headers)

    # Get body for POST requests
    body = None
    if request.method in ["POST", "PUT"]:
        try:
            body = await request.json()
        except:
            body = await request.body()

    # Get all available keys (not on cooldown)
    available_keys = key_manager.get_all_available_keys()

    # If all keys cooling, return 503 immediately
    # OpenClaw will retry with backoff - better than timing out
    if not available_keys:
        earliest = key_manager.get_earliest_cooldown()
        print(f"[Proxy] All keys cooling, earliest available in {earliest:.1f}s")
        raise HTTPException(
            status_code=503,
            detail=f"All API keys cooling. Retry in {int(earliest)}s."
        )

    # Sort keys: prefer last used, then random shuffle of remaining
    key_order = []
    if _last_key_used and _last_key_used in available_keys:
        key_order.append(_last_key_used)
    # Shuffle remaining keys
    other_keys = [k for k in available_keys if k != _last_key_used]
    random.shuffle(other_keys)
    key_order.extend(other_keys)

    # Try each key
    keys_attempted = set()
    last_error = None

    for key_name in key_order:
        if len(keys_attempted) >= MAX_RETRIES:
            break

        key = key_manager.keys[key_name]

        # Try to acquire semaphore immediately (non-blocking)
        # If key is busy, try next key right away
        acquired = await try_acquire_key(key, timeout=0.1)

        if not acquired:
            # Key is busy with 5 concurrent requests, try next key
            print(f"[Proxy] Key {key_name} busy, trying next...")
            continue

        # Got the key, mark as attempted
        keys_attempted.add(key_name)
        print(f"[Proxy] Using {key_name} (attempt {len(keys_attempted)}/{MAX_RETRIES})")

        try:
            result = await _make_request_with_key(
                http_client, request, target_url, headers, body, key
            )

            if result is not None:
                # Success! Track this key for affinity
                _last_key_used = key_name
                return result
            else:
                # Result is None means rate limited (429)
                # Key was already marked as cooling, try next key
                last_error = "Rate limited (429)"
                continue

        except RateLimitError:
            # Key hit rate limit, already marked as cooling
            last_error = "Rate limited (429)"
            continue

        except httpx.HTTPStatusError as e:
            key.semaphore.release()
            acquired = False
            if e.response.status_code == 429:
                key_manager.mark_cooldown(key.name, 60)
                last_error = "Rate limited (429)"
                continue
            raise HTTPException(status_code=e.response.status_code, detail=str(e))

        except Exception as e:
            error_msg = str(e)
            print(f"[Proxy] Error with {key_name}: {error_msg}")
            last_error = error_msg
            continue

        finally:
            if acquired:
                key.semaphore.release()

    # All retries exhausted
    raise HTTPException(
        status_code=503,
        detail=f"All keys busy or cooling. Last error: {last_error}"
    )


async def _make_request_with_key(
    http_client: httpx.AsyncClient,
    request: Request,
    target_url: str,
    headers: dict,
    body: any,
    key: KeyState
) -> Optional[Response]:
    """
    Make request with a specific key.
    Returns Response on success, None on rate limit (caller should retry).
    """
    global metrics

    # Check if streaming
    is_streaming = body and isinstance(body, dict) and body.get("stream", False)

    if is_streaming and request.method == "POST":
        # Streaming response - use generator
        return StreamingResponse(
            stream_response(http_client, target_url, headers, body, key),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    else:
        # Non-streaming - regular request
        request_headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
        request_headers["Authorization"] = f"Bearer {key.key}"
        request_headers.pop("host", None)
        request_headers["accept-encoding"] = "identity"

        # Use requests library instead of httpx for non-streaming requests
        # requests is more lenient with content-length mismatches (NVIDIA bug)
        # Run in thread pool to keep it async
        def make_sync_request():
            resp = requests.request(
                request.method,
                target_url,
                headers=request_headers,
                json=body if body else None,
                timeout=120.0
            )
            return resp.status_code, dict(resp.headers), resp.content

        try:
            status_code, resp_headers, content_bytes = await asyncio.get_event_loop().run_in_executor(
                thread_pool, make_sync_request
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Request failed: {str(e)}")

        # Reconstruct a fake response object for the code below
        class FakeResponse:
            def __init__(self, status, headers, content):
                self.status_code = status
                self.headers = headers
                self._content = content
            def raise_for_status(self):
                if self.status_code >= 400:
                    raise httpx.HTTPStatusError(str(self.status_code), request=None, response=self)
        response = FakeResponse(status_code, resp_headers, content_bytes)

        # Handle rate limit
        if response.status_code == 429:
            cooldown = 60
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    cooldown = int(retry_after)
                except:
                    pass
            key_manager.mark_cooldown(key.name, cooldown)
            await metrics.inc("total_rate_limits")
            return None  # Signal to retry with different key

        # Handle server errors
        if response.status_code in [500, 502, 503, 504]:
            response.raise_for_status()  # Will trigger retry via exception

        response.raise_for_status()

        # Success - return response
        content = response._content

        # Pass through headers except hop-by-hop headers and content-length
        # We exclude content-length because NVIDIA's endpoint has a bug where
        # it sends more bytes than declared, and we need to set our own
        # content-length based on the actual bytes received
        excluded = {
            "content-encoding", "transfer-encoding",
            "content-length",
            "connection", "keep-alive", "upgrade",
            "proxy-authenticate", "proxy-authorization",
            "te", "trailers"
        }
        response_headers = {
            k: v for k, v in response.headers.items()
            if k.lower() not in excluded
        }
        # Set correct content-length based on actual bytes received
        response_headers["content-length"] = str(len(content))

        return Response(
            content=content,
            status_code=response.status_code,
            headers=response_headers
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
