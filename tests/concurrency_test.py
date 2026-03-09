#!/usr/bin/env python3
"""
Concurrency Test for Keymaster Proxy

Tests concurrent request handling to ensure:
1. Keys are properly acquired and released
2. No empty responses occur
3. Request isolation works correctly
4. Recovery under load functions properly

Usage:
    python3 concurrency_test.py --quick      # Quick test (5 requests)
    python3 concurrency_test.py --full       # Full test (20 requests)
    python3 concurrency_test.py --stress     # Stress test (50 requests)
"""

import asyncio
import argparse
import json
import sys
import time
from datetime import datetime
from typing import List, Dict, Any
import aiohttp


PROXY_URL = "http://127.0.0.1:8787/v1/chat/completions"
HEALTH_URL = "http://127.0.0.1:8787/health"


def log(msg: str, level: str = "INFO"):
    """Print timestamped log message."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] [{level}] {msg}")


async def check_proxy_health() -> bool:
    """Check if proxy is running and healthy."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(HEALTH_URL, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    log(f"Proxy healthy: {data.get('available_keys', 0)} keys available")
                    return True
                return False
    except Exception as e:
        log(f"Proxy health check failed: {e}", "ERROR")
        return False


async def make_request(
    session: aiohttp.ClientSession,
    request_id: int,
    prompt: str,
    model: str = "moonshotai/kimi-k2.5"
) -> Dict[str, Any]:
    """
    Make a single streaming request and capture all tokens.

    Returns:
        Dict with request results including:
        - request_id
        - success: bool
        - tokens: list of token contents
        - token_count: number of tokens received
        - error: error message if failed
        - duration_ms: request duration
    """
    result = {
        "request_id": request_id,
        "success": False,
        "tokens": [],
        "token_count": 0,
        "error": None,
        "duration_ms": 0,
        "key_used": None
    }

    headers = {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "stream": True,
        "max_tokens": 50,
        "messages": [{"role": "user", "content": prompt}]
    }

    start_time = time.time()

    try:
        async with session.post(
            PROXY_URL,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                result["error"] = f"HTTP {resp.status}: {error_text[:100]}"
                return result

            # Read SSE stream
            buffer = ""
            async for chunk in resp.content:
                try:
                    chunk = chunk.decode('utf-8')
                    buffer += chunk

                    # Process complete SSE lines
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()

                        if not line or line.startswith(":"):
                            continue

                        if line.startswith("data: "):
                            data = line[6:]

                            if data.strip() == "[DONE]":
                                break

                            try:
                                parsed = json.loads(data)
                                if "choices" in parsed and parsed["choices"]:
                                    choice = parsed["choices"][0]
                                    if "delta" in choice and "content" in choice["delta"]:
                                        content = choice["delta"].get("content", "")
                                        if content:
                                            result["tokens"].append(content)
                                            result["token_count"] += 1
                            except json.JSONDecodeError:
                                continue
                except Exception as e:
                    log(f"Request {request_id}: Error processing chunk: {e}", "ERROR")
                    continue

        result["duration_ms"] = int((time.time() - start_time) * 1000)

        # Check if we got tokens
        if result["token_count"] == 0:
            result["error"] = "No tokens received (empty response)"
        else:
            result["success"] = True

    except asyncio.TimeoutError:
        result["error"] = "Request timeout"
        result["duration_ms"] = int((time.time() - start_time) * 1000)
    except Exception as e:
        result["error"] = f"Exception: {str(e)[:100]}"
        result["duration_ms"] = int((time.time() - start_time) * 1000)

    return result


async def run_concurrent_requests(
    num_requests: int,
    prompt_template: str = "Test {id}: What is {id} + {id}?"
) -> List[Dict[str, Any]]:
    """Run multiple concurrent requests and collect results."""

    log(f"Starting {num_requests} concurrent requests...")

    async with aiohttp.ClientSession() as session:
        # Create all request tasks
        tasks = []
        for i in range(num_requests):
            prompt = prompt_template.format(id=i+1)
            task = make_request(session, i+1, prompt)
            tasks.append(task)

        # Run all requests concurrently
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_duration = time.time() - start_time

    # Process results
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append({
                "request_id": i+1,
                "success": False,
                "tokens": [],
                "token_count": 0,
                "error": f"Exception: {str(result)[:100]}"
            })
        else:
            processed_results.append(result)

    log(f"All {num_requests} requests completed in {total_duration:.2f}s")
    return processed_results


def analyze_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze test results and return summary."""

    total = len(results)
    successful = sum(1 for r in results if r["success"])
    failed = total - successful
    empty_responses = sum(1 for r in results if "No tokens" in (r.get("error") or ""))

    token_counts = [r["token_count"] for r in results if r["success"]]
    avg_tokens = sum(token_counts) / len(token_counts) if token_counts else 0

    durations = [r["duration_ms"] for r in results]
    avg_duration = sum(durations) / len(durations) if durations else 0

    return {
        "total_requests": total,
        "successful": successful,
        "failed": failed,
        "empty_responses": empty_responses,
        "success_rate": successful / total * 100 if total > 0 else 0,
        "avg_tokens": avg_tokens,
        "min_tokens": min(token_counts) if token_counts else 0,
        "max_tokens": max(token_counts) if token_counts else 0,
        "avg_duration_ms": avg_duration,
        "errors": [r["error"] for r in results if r["error"]]
    }


def print_summary(results: List[Dict[str, Any]], analysis: Dict[str, Any]):
    """Print detailed test summary."""

    print("\n" + "="*70)
    print("CONCURRENCY TEST RESULTS")
    print("="*70)

    print(f"\nTotal Requests: {analysis['total_requests']}")
    print(f"Successful: {analysis['successful']}")
    print(f"Failed: {analysis['failed']}")
    print(f"Empty Responses: {analysis['empty_responses']}")
    print(f"Success Rate: {analysis['success_rate']:.1f}%")

    print(f"\nToken Statistics:")
    print(f"  Average: {analysis['avg_tokens']:.1f}")
    print(f"  Min: {analysis['min_tokens']}")
    print(f"  Max: {analysis['max_tokens']}")

    print(f"\nTiming:")
    print(f"  Average Duration: {analysis['avg_duration_ms']:.0f}ms")

    if analysis['errors']:
        print(f"\nErrors ({len(analysis['errors'])}):")
        for i, error in enumerate(analysis['errors'][:10], 1):
            print(f"  {i}. {error}")
        if len(analysis['errors']) > 10:
            print(f"  ... and {len(analysis['errors']) - 10} more")

    # Print per-request details
    print("\n" + "-"*70)
    print("PER-REQUEST DETAILS")
    print("-"*70)

    for r in results:
        status = "✓" if r["success"] else "✗"
        tokens = r.get("token_count", 0)
        duration = r.get("duration_ms", 0)
        preview = "".join(r["tokens"][:3])[:50] if r["tokens"] else "(no tokens)"
        print(f"  {status} Request {r['request_id']:2d}: {tokens:3d} tokens, {duration:4d}ms | {preview}...")

    print("\n" + "="*70)


def print_recommendations(analysis: Dict[str, Any]):
    """Print recommendations based on test results."""

    print("\nRECOMMENDATIONS:")
    print("-"*70)

    if analysis['success_rate'] == 100:
        print("✓ All requests succeeded - concurrency handling is working correctly!")
    elif analysis['success_rate'] >= 90:
        print("⚠ Most requests succeeded, but some failures detected.")
        print("  - Check if keys are properly configured")
        print("  - Verify NVIDIA API is accessible")
    elif analysis['success_rate'] >= 50:
        print("✗ Significant failure rate detected!")
        print("  - Check proxy logs for errors")
        print("  - Verify all API keys are valid")
        print("  - Consider increasing key cooldown periods")
    else:
        print("✗ Critical failure rate - proxy may not be functioning!")
        print("  - Check if proxy is running: python3 start_proxy.py --status")
        print("  - Verify auth-profiles.json has valid keys")
        print("  - Check proxy logs for configuration errors")

    if analysis['empty_responses'] > 0:
        print(f"\n✗ Empty responses detected: {analysis['empty_responses']}")
        print("  This indicates the concurrency bug is NOT fixed!")
        print("  - Verify key_manager.py has atomic acquire/release")
        print("  - Check that server.py releases keys after use")

    print()


async def main():
    parser = argparse.ArgumentParser(description="Test Keymaster Proxy Concurrency")
    parser.add_argument("--quick", action="store_true", help="Quick test (5 requests)")
    parser.add_argument("--full", action="store_true", help="Full test (20 requests)")
    parser.add_argument("--stress", action="store_true", help="Stress test (50 requests)")
    parser.add_argument("--count", type=int, default=5, help="Custom request count")
    args = parser.parse_args()

    # Determine test size
    if args.stress:
        num_requests = 50
    elif args.full:
        num_requests = 20
    elif args.count:
        num_requests = args.count
    else:
        num_requests = 5

    print("\n" + "="*70)
    print(f"KEYMASTER PROXY CONCURRENCY TEST ({num_requests} requests)")
    print("="*70)

    # Check proxy health
    if not await check_proxy_health():
        log("Proxy is not healthy. Please start it first:", "ERROR")
        log("  python3 start_proxy.py", "ERROR")
        sys.exit(1)

    # Run test
    results = await run_concurrent_requests(num_requests)

    # Analyze and print results
    analysis = analyze_results(results)
    print_summary(results, analysis)
    print_recommendations(analysis)

    # Exit with appropriate code
    if analysis['success_rate'] == 100:
        sys.exit(0)
    elif analysis['success_rate'] >= 80:
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
