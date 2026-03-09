"""
Context Rebuilder for Stream Recovery

Rebuilds conversation with continuation instruction when switching keys.
"""

import json
from typing import List, Dict, Any, Tuple


class ContextRebuilder:
    """
    Rebuilds conversation context for seamless key switching.
    """

    @staticmethod
    def build_recovery_prompt(
        original_messages: List[Dict[str, Any]],
        partial_assistant_response: str,
        max_chars: int = 4000
    ) -> List[Dict[str, Any]]:
        """
        Build message array that tells the next key to continue.

        Args:
            original_messages: Original conversation history
            partial_assistant_response: Content already generated
            max_chars: Max characters to include in prompt

        Returns:
            New message array with continuation instruction
        """
        # Truncate partial response if too long
        partial = partial_assistant_response
        if len(partial) > max_chars:
            # Keep end of response (most relevant for continuation)
            partial = partial[-max_chars:]

        # Copy original messages
        messages = original_messages.copy()

        # Add the partial assistant response
        # This makes the model think it already said this
        messages.append({
            "role": "assistant",
            "content": partial
        })

        # Add explicit continuation instruction
        # This is critical - without it, the model might restart
        messages.append({
            "role": "user",
            "content": "Continue the previous response exactly where it stopped. Do not repeat any text already written."
        })

        return messages

    @staticmethod
    def is_done_frame(data: str) -> bool:
        """
        Check if SSE data is the completion marker.

        Args:
            data: Raw SSE data content (after 'data: ')

        Returns:
            True if this is the [DONE] marker
        """
        return data.strip() == "[DONE]"

    @staticmethod
    def parse_sse_data(line: str) -> Tuple[bool, str]:
        """
        Parse an SSE line.

        Args:
            line: Raw SSE line from stream

        Returns:
            (is_data, content)
            is_data: True if this is a data line
            content: The content (or empty string for comments)
        """
        line = line.strip()

        if not line:
            return False, ""

        if line.startswith("data: "):
            return True, line[6:]

        if line.startswith(":"):
            # SSE comment (like :ping)
            return False, ""

        return False, ""

    @staticmethod
    def extract_content(data: str) -> Tuple[bool, str]:
        """
        Extract content from SSE data frame.

        Args:
            data: SSE data content (after 'data: ')

        Returns:
            (has_content, content_text)
            has_content: True if valid content found
            content_text: The content string
        """
        # Check for done marker
        if data.strip() == "[DONE]":
            return False, "[DONE]"

        try:
            parsed = json.loads(data)

            # Handle OpenAI format
            if "choices" in parsed and len(parsed["choices"]) > 0:
                choice = parsed["choices"][0]

                if "delta" in choice and "content" in choice["delta"]:
                    content = choice["delta"]["content"]
                    if content:  # May be null or empty
                        return True, content

                if "text" in choice:  # Non-chat format
                    return True, choice["text"]

            return False, ""

        except json.JSONDecodeError:
            # Not JSON, treat as plain text
            return bool(data.strip()), data

    @staticmethod
    def build_sse_frame(content: str) -> str:
        """
        Build a properly formatted SSE data frame.

        Args:
            content: Content text to wrap

        Returns:
            Formatted SSE frame with newline
        """
        frame = {
            "choices": [{
                "delta": {"content": content},
                "index": 0,
                "finish_reason": None
            }]
        }
        return f'data: {json.dumps(frame)}\n\n'
