#!/usr/bin/env python3
"""
OpenClaw Proxy Server

Transparent proxy that:
- Receives OpenAI-compatible requests from OpenClaw
- Rotates through NVIDIA API keys on rate limits
- Supports streaming responses
- Cycles back to key 1 when all keys exhausted
"""

import asyncio
import json
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
    http_client = httpx.AsyncClient(
        timeout=120.0,
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20)
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
    When all keys exhausted, cycles back and waits for key 1.
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
            wait_time = min(5, min_cooldown)  # Wait max 5s at a time
            print(f"[Proxy] All keys cooling, waiting {wait_time:.1f}s...")
            await asyncio.sleep(wait_time)
        else:
            # Shouldn't happen, but just in case
            await asyncio.sleep(1)

    # If we get here, we've been waiting a while
    # Force reset and try again (nuclear option for long tasks)
    print("[Proxy] Max retries reached, cycling keys...")
    key_manager.reset_all_keys()
    await asyncio.sleep(1)

    key = key_manager.get_key_for_request()
    if key:
        return key

    raise HTTPException(status_code=503, detail="All API keys unavailable")


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
    """
    # Replace auth header with the selected key
    headers = {**headers, "Authorization": f"Bearer {key.key}"}

    # Remove host header (will be set by httpx)
    headers.pop("host", None)

    async with client.stream(
        "POST",
        url,
        headers=headers,
        json=body,
        timeout=120.0
    ) as response:
        # Check for rate limit
        if response.status_code == 429:
            # Get cooldown from header or default
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


class RateLimitError(Exception):
    pass


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    if not key_manager:
        raise HTTPException(status_code=503, detail="Proxy not ready")

    status = key_manager.get_status()
    return {
        "status": "ok",
        "timestamp": time.time(),
        **status
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_request(request: Request, path: str):
    """
    Main proxy endpoint - forwards all requests to NVIDIA API
    with automatic key rotation on rate limits.
    """
    global key_manager, http_client

    if not key_manager or not http_client:
        raise HTTPException(status_code=503, detail="Proxy not initialized")

    # Build target URL
    target_url = f"{NVIDIA_BASE_URL}/{path}"

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

    for attempt in range(MAX_RETRIES):
        key = None
        try:
            # Get available key (waits if all cooling)
            key = await get_available_key_with_retry()
            print(f"[Proxy] Attempt {attempt+1}/{MAX_RETRIES} using {key.name}")

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
                request_headers = {**headers, "Authorization": f"Bearer {key.key}"}
                request_headers.pop("host", None)

                response = await http_client.request(
                    method=request.method,
                    url=target_url,
                    headers=request_headers,
                    json=body if body else None,
                    timeout=120.0
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
                    print(f"[Proxy] Rate limited on {key.name}, retrying...")
                    last_error = f"Rate limited on {key.name}"
                    continue  # Try next key

                # Handle server errors - retry with backoff
                if response.status_code in [500, 502, 503, 504]:
                    delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS)-1)]
                    print(f"[Proxy] Server error {response.status_code}, retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    last_error = f"Server error {response.status_code}"
                    continue  # Retry with same or new key

                response.raise_for_status()

                # Success - return response
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )

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
            print(f"[Proxy] Error: {e}")
            last_error = str(e)
            delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS)-1)]
            await asyncio.sleep(delay)

    # All retries exhausted
    raise HTTPException(
        status_code=503,
        detail=f"All retries exhausted. Last error: {last_error}"
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
