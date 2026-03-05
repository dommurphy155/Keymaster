#!/usr/bin/env python3
"""
Request Wrapper - Wraps LLM API calls with automatic key fallback.

Integrates with OpenClaw's configuration and Agent Orchestrator.

This is the main entry point for Keymaster. Use make_request() instead of
direct API calls to get automatic key rotation on rate limits/timeouts.
"""

import json
import os
import time
import sys
from typing import Dict, List, Optional, Any, Iterator
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from key_pool_manager import KeyPoolManager
from context_compactor import ContextCompactor, compact_context
from state_manager import StateManager


class KeymasterError(Exception):
    """Base exception for Keymaster errors."""
    pass


class AllKeysExhaustedError(KeymasterError):
    """Raised when all API keys have been tried and failed."""
    pass


class RequestWrapper:
    """Wraps LLM API requests with key rotation and context preservation."""

    # Error patterns that trigger rotation
    RETRYABLE_ERRORS = [
        'rate_limit',
        'rate limit',
        '429',
        'timeout',
        '408',
        '504',
        'connection',
        'context_length_exceeded',
        'tokens per minute',
        'tpm',
        'rpm',
        'too many requests',
        'insufficient_quota',
        'nvcf-req-002',
        'inference_timeout'
    ]

    # Non-retryable errors
    FATAL_ERRORS = [
        'invalid_api_key',
        'authentication',
        '401',
        '403',
        'not_found',
        'model_not_found',
        'invalid_request',
        '400',
        'nvcf-auth-001'
    ]

    DEFAULT_TIMEOUT = 120
    MAX_RETRIES_PER_KEY = 3

    def __init__(self):
        self.key_manager = KeyPoolManager()
        self.compactor = ContextCompactor()
        self.state_manager = StateManager()

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error should trigger key rotation."""
        error_str = str(error).lower()

        # Check for retryable patterns
        for pattern in self.RETRYABLE_ERRORS:
            if pattern in error_str:
                return True

        # Check HTTP status codes in error message
        if '429' in error_str or '408' in error_str or '504' in error_str:
            return True

        return False

    def _is_fatal_error(self, error: Exception) -> bool:
        """Check if an error is non-recoverable."""
        error_str = str(error).lower()

        for pattern in self.FATAL_ERRORS:
            if pattern in error_str:
                return True

        return False

    def _make_nvidia_request(self,
                            api_key: str,
                            base_url: str,
                            messages: List[Dict[str, Any]],
                            model: str = "moonshotai/kimi-k2.5",
                            temperature: float = 0.7,
                            max_tokens: int = 4096,
                            timeout: int = 120,
                            stream: bool = False,
                            **kwargs) -> Dict[str, Any]:
        """
        Make a request to NVIDIA API using OpenClaw provider config.

        Returns:
            Response dict with 'content', 'usage', etc.
        """
        try:
            import requests
        except ImportError:
            raise ImportError("requests library required. Install with: pip install requests")

        url = f"{base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Clean up messages for API
        clean_messages = []
        for msg in messages:
            clean_msg = {
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            }
            # Only include name if present (for tool messages)
            if "name" in msg and msg["name"]:
                clean_msg["name"] = msg["name"]
            clean_messages.append(clean_msg)

        payload = {
            "model": model,
            "messages": clean_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }

        # Add any additional parameters
        for key in ["top_p", "frequency_penalty", "presence_penalty", "stop"]:
            if key in kwargs:
                payload[key] = kwargs[key]

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout
            )

            # Handle HTTP errors
            if response.status_code == 429:
                raise Exception(f"Rate limit exceeded (429): {response.text}")
            elif response.status_code == 408:
                raise Exception(f"Request timeout (408): {response.text}")
            elif response.status_code == 504:
                raise Exception(f"Gateway timeout (504): {response.text}")
            elif response.status_code == 401:
                raise Exception(f"Invalid API key (401): {response.text}")
            elif response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")

            result = response.json()

            # Extract content
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                content = choice.get("message", {}).get("content", "")

                return {
                    "content": content,
                    "finish_reason": choice.get("finish_reason"),
                    "usage": result.get("usage", {}),
                    "model": result.get("model", model),
                    "raw_response": result
                }
            else:
                raise Exception(f"Unexpected response format: {result}")

        except requests.exceptions.Timeout:
            raise Exception(f"Request timeout after {timeout}s")
        except requests.exceptions.ConnectionError as e:
            raise Exception(f"Connection error: {e}")
        except Exception as e:
            raise Exception(f"Request failed: {e}")

    def _compact_if_needed(self,
                          messages: List[Dict[str, Any]],
                          threshold: Optional[float] = None) -> List[Dict[str, Any]]:
        """Compact context if it exceeds threshold."""
        if threshold is None:
            threshold = 0.8

        if self.compactor.should_compact(messages, threshold):
            print(f"[Keymaster] Context compaction triggered before rotation")
            result = self.compactor.compact(messages, threshold=threshold)
            print(f"[Keymaster] Compacted from {result.original_tokens:,} to {result.compacted_tokens:,} tokens")
            return result.messages

        return messages

    def make_request(self,
                    messages: List[Dict[str, Any]],
                    model: str = "moonshotai/kimi-k2.5",
                    temperature: float = 0.7,
                    max_tokens: int = 4096,
                    timeout: int = 120,
                    stream: bool = False,
                    compact_threshold: Optional[float] = None,
                    conversation_id: Optional[str] = None,
                    **kwargs) -> Dict[str, Any]:
        """
        Make an LLM request with automatic key fallback.

        This is the main method - use this instead of direct API calls.

        Args:
            messages: List of conversation messages
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            stream: Whether to stream response
            compact_threshold: Context compaction threshold (0.0-1.0)
            conversation_id: Optional conversation ID for checkpointing
            **kwargs: Additional API parameters

        Returns:
            Response dict with 'content', 'usage', etc.

        Raises:
            AllKeysExhaustedError: If all keys fail
            KeymasterError: For other errors
        """
        # Track attempted keys
        attempted_keys = set()
        last_error = None

        # Compact context before starting if needed
        messages = self._compact_if_needed(messages, compact_threshold)

        # Create checkpoint if conversation_id provided
        if conversation_id:
            self.state_manager.create_checkpoint(
                conversation_id=conversation_id,
                messages=messages,
                current_key=self.key_manager.get_current_key()
            )

        while len(attempted_keys) < len(self.key_manager.KEY_NAME_MAP):
            # Get current key
            current_key_name = self.key_manager.get_current_key()

            if current_key_name in attempted_keys:
                # We've already tried this key, try to rotate
                new_key = self.key_manager.rotate_to_next_key("exhausted_attempts")
                if new_key is None or new_key in attempted_keys:
                    break
                current_key_name = new_key

            attempted_keys.add(current_key_name)

            # Get API key and base URL from OpenClaw config
            api_key = self.key_manager.get_key_api_key(current_key_name)
            base_url = self.key_manager.get_key_base_url(current_key_name)

            if not api_key:
                print(f"[Keymaster] Warning: No API key found for {current_key_name}")
                continue

            if not base_url:
                base_url = "https://integrate.api.nvidia.com/v1"

            # Try request with retries
            for attempt in range(self.MAX_RETRIES_PER_KEY):
                try:
                    print(f"[Keymaster] Using {current_key_name} (attempt {attempt + 1})")

                    response = self._make_nvidia_request(
                        api_key=api_key,
                        base_url=base_url,
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout,
                        stream=stream,
                        **kwargs
                    )

                    # Success!
                    print(f"[Keymaster] Request successful with {current_key_name}")

                    # Save conversation state if ID provided
                    if conversation_id:
                        self.state_manager.save_conversation_state(
                            conversation_id=conversation_id,
                            messages=messages,
                            current_key=current_key_name
                        )

                    return response

                except Exception as e:
                    last_error = e
                    error_msg = str(e).lower()

                    print(f"[Keymaster] Error with {current_key_name}: {e}")

                    # Check if fatal error
                    if self._is_fatal_error(e):
                        raise KeymasterError(f"Fatal error with {current_key_name}: {e}")

                    # Check if retryable
                    if self._is_retryable_error(e):
                        if attempt < self.MAX_RETRIES_PER_KEY - 1:
                            # Wait briefly before retry
                            wait_time = (attempt + 1) * 2
                            print(f"[Keymaster] Retrying in {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                        else:
                            # Exhausted retries, mark cooldown and rotate
                            print(f"[Keymaster] Marking {current_key_name} for cooldown")
                            self.key_manager.mark_key_cooldown(current_key_name)
                            break
                    else:
                        # Unknown error, try next key immediately
                        break

        # All keys exhausted
        raise AllKeysExhaustedError(
            f"All API keys exhausted. Last error: {last_error}"
        )

    def make_request_with_recovery(self,
                                  messages: List[Dict[str, Any]],
                                  conversation_id: str,
                                  **kwargs) -> Dict[str, Any]:
        """
        Make a request with full checkpoint-based recovery.

        For use with agent-orchestrator - if a request fails, the conversation
        state is saved and can be resumed with a new key.

        Args:
            messages: Conversation messages
            conversation_id: Unique conversation ID for checkpointing
            **kwargs: Additional args passed to make_request

        Returns:
            Response dict
        """
        try:
            return self.make_request(
                messages=messages,
                conversation_id=conversation_id,
                **kwargs
            )
        except AllKeysExhaustedError:
            # Save final state before failing
            self.state_manager.save_conversation_state(
                conversation_id=conversation_id,
                messages=messages,
                current_key=self.key_manager.get_current_key(),
                compacted=True
            )
            raise

    def make_request_stream(self,
                           messages: List[Dict[str, Any]],
                           model: str = "moonshotai/kimi-k2.5",
                           **kwargs) -> Iterator[str]:
        """
        Make a streaming request with fallback support.

        Yields chunks of content as they're received.
        """
        # For now, non-streaming fallback
        # Full streaming with rotation is more complex
        response = self.make_request(messages, model=model, stream=False, **kwargs)
        yield response.get("content", "")


def make_request(messages: List[Dict[str, Any]],
                model: str = "moonshotai/kimi-k2.5",
                temperature: float = 0.7,
                max_tokens: int = 4096,
                timeout: int = 120,
                stream: bool = False,
                conversation_id: Optional[str] = None,
                **kwargs) -> Dict[str, Any]:
    """
    Convenience function for making requests with Keymaster.

    Use this instead of direct API calls.

    Example:
        response = make_request(
            messages=[{"role": "user", "content": "Hello"}],
            model="moonshotai/kimi-k2.5",
            conversation_id="task-123"
        )
        print(response["content"])
    """
    wrapper = RequestWrapper()
    return wrapper.make_request(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        stream=stream,
        conversation_id=conversation_id,
        **kwargs
    )


def make_request_with_recovery(messages: List[Dict[str, Any]],
                               conversation_id: str,
                               **kwargs) -> Dict[str, Any]:
    """
    Make request with checkpoint-based recovery for agent-orchestrator.

    Args:
        messages: Conversation messages
        conversation_id: Unique ID for this conversation/task
        **kwargs: Additional API arguments

    Returns:
        Response dict with 'content', 'usage', etc.

    Raises:
        AllKeysExhaustedError: If all keys fail
    """
    wrapper = RequestWrapper()
    return wrapper.make_request_with_recovery(
        messages=messages,
        conversation_id=conversation_id,
        **kwargs
    )


def get_available_key_info() -> Dict[str, Any]:
    """Get information about available keys for agent-orchestrator."""
    manager = KeyPoolManager()
    return {
        'current_key': manager.get_current_key(),
        'current_provider': manager.get_current_provider_id(),
        'available_keys': manager.get_all_available_keys(),
        'key_roles': {
            k: manager.get_key_role(k)
            for k in manager.KEY_NAME_MAP.keys()
        }
    }


def main():
    """CLI for testing the wrapper."""
    import argparse

    parser = argparse.ArgumentParser(description="Keymaster Request Wrapper")
    parser.add_argument("--test", action="store_true", help="Run a test request")
    parser.add_argument("--prompt", type=str, default="Hello, what is 2+2?", help="Test prompt")
    parser.add_argument("--model", type=str, default="moonshotai/kimi-k2.5", help="Model to use")
    parser.add_argument("--compact", action="store_true", help="Test context compaction")
    parser.add_argument("--conversation-id", type=str, help="Conversation ID for checkpointing")

    args = parser.parse_args()

    if args.test:
        print(f"[Keymaster] Testing with prompt: {args.prompt}")
        print(f"[Keymaster] Model: {args.model}")
        print("-" * 50)

        try:
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": args.prompt}
            ]

            response = make_request(
                messages=messages,
                model=args.model,
                temperature=0.7,
                max_tokens=1024,
                conversation_id=args.conversation_id
            )

            print(f"Response:\n{response['content']}")
            print("-" * 50)
            print(f"Usage: {response.get('usage', {})}")
            print(f"Finish reason: {response.get('finish_reason')}")

        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.compact:
        # Test compaction
        print("[Keymaster] Testing context compaction")

        # Create large test conversation
        messages = [
            {"role": "system", "content": "You are Claude, an AI assistant."},
        ]

        for i in range(30):
            messages.append({
                "role": "user",
                "content": f"Question {i}: Explain the concept of recursion in programming and provide examples."
            })
            messages.append({
                "role": "assistant",
                "content": f"Answer {i}: Recursion is a programming concept where a function calls itself. "
                          f"Here's an example in Python:\n\n"
                          f"def factorial(n):\n"
                          f"    if n <= 1:\n"
                          f"        return 1\n"
                          f"    return n * factorial(n-1)\n\n"
                          f"This is a simple example but recursion can be used for many things like "
                          f"tree traversal, dynamic programming, and divide-and-conquer algorithms. "
                          + "x" * 500  # Add padding to simulate large response
            })

        compactor = ContextCompactor()
        result = compactor.compact(messages, threshold=0.5)  # Lower threshold for testing

        print(compactor.get_compaction_report(result))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
