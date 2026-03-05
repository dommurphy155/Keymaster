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
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from .key_manager import KeyManager, KeyState

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


async def get_available_key_with_retry() -> KeyState:
    """
    Get an available key, waiting if all are on cooldown.
    Waits for the earliest cooldown to expire - never resets keys.
    """
    global key_manager

    for attempt in range(MAX_RETRIES):
        # Try to get an available key
        key = key_manager.get_key_for_request()

        if key:
            return key

        # All keys cooling - find the one with shortest cooldown
        min_cooldown = float('inf')
        for k in key_manager.keys.values():
            remaining = key_manager.get_cooldown_remaining(k.name)
            if remaining < min_cooldown:
                min_cooldown = remaining

        if min_cooldown < float('inf'):
            # Wait until the earliest key is available
            wait_time = min_cooldown
            print(f"[Proxy] All keys cooling, waiting {wait_time:.1f}s for next key...")
            await asyncio.sleep(wait_time)
        else:
            # Shouldn't happen, but just in case
            await asyncio.sleep(1)

    # All retries exhausted and all keys still cooling
    raise HTTPException(status_code=503, detail="All API keys cooling. Retry shortly.")


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

    chunks_sent = 0
    try:
        async with client.stream(
            "POST",
            url,
            headers=headers,
            json=body,
            timeout=120.0
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


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_request(request: Request, path: str):
    """
    Main proxy endpoint - forwards all requests to NVIDIA API
    with automatic key rotation on rate limits.
    """
    global key_manager, http_client, metrics

    if not key_manager or not http_client:
        raise HTTPException(status_code=503, detail="Proxy not initialized")

    # Increment total request counter (async-safe)
    await metrics.inc("total_requests")

    # Build target URL
    # Remove leading /v1/ since base URL already has /v1
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

    # Try with retries and key rotation
    last_error = None
    keys_to_try = key_manager.get_all_available_keys()

    # If all keys cooling, wait for earliest to become available
    if not keys_to_try:
        print("[Proxy] All keys cooling, waiting for earliest availability...")
        await get_available_key_with_retry()  # This waits properly
        keys_to_try = key_manager.get_all_available_keys()

    # Shuffle available keys to distribute load evenly
    random.shuffle(keys_to_try)

    for attempt in range(min(MAX_RETRIES, len(keys_to_try) if keys_to_try else MAX_RETRIES)):
        key = None
        try:
            # Get available key (waits if all cooling, never resets)
            key = await get_available_key_with_retry()
            print(f"[Proxy] Attempt {attempt+1}/{MAX_RETRIES} using {key.name}")

            # Acquire per-key semaphore to limit concurrent requests
            # Use non-blocking acquisition to avoid race conditions
            # If key busy, immediately try next key instead of queuing
            acquired = False
            try:
                # Try to acquire with zero timeout (non-blocking)
                # In Python 3.8, we use wait_for with tiny timeout
                await asyncio.wait_for(key.semaphore.acquire(), timeout=0.001)
                acquired = True
                print(f"[Proxy] Acquired semaphore for {key.name}")
                result = await _make_request_with_key(
                    http_client, request, target_url, headers, body, key
                )
                if result is not None:
                    return result
                # If result is None, it was rate limited - try next key
                continue
            except asyncio.TimeoutError:
                # Key is busy with another request, try next available key
                print(f"[Proxy] Key {key.name} busy, trying next...")
                continue
            finally:
                if acquired:
                    key.semaphore.release()

        except RateLimitError:
            # Key was marked as cooling, try again
            continue

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                if key:
                    key_manager.mark_cooldown(key.name, 60)
                continue
            raise HTTPException(status_code=e.response.status_code, detail=str(e))

        except Exception as e:
            error_msg = str(e)
            print(f"[Proxy] Error: {error_msg}")
            # Try to get more details about httpx errors
            if hasattr(e, 'response'):
                try:
                    print(f"[Proxy] Response status: {e.response.status_code}")
                    print(f"[Proxy] Response headers: {dict(e.response.headers)}")
                except:
                    pass
            last_error = error_msg
            delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS)-1)]
            await asyncio.sleep(delay)

    # All retries exhausted
    raise HTTPException(
        status_code=503,
        detail=f"All retries exhausted. Last error: {last_error}"
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

        response = await http_client.request(
            method=request.method,
            url=target_url,
            headers=request_headers,
            json=body if body else None
        )

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
        content = await response.aread()

        # Pass through headers except hop-by-hop headers
        excluded = {
            "content-encoding", "transfer-encoding",
            "connection", "keep-alive", "upgrade",
            "proxy-authenticate", "proxy-authorization",
            "te", "trailers"
        }
        response_headers = {
            k: v for k, v in response.headers.items()
            if k.lower() not in excluded
        }

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
