#!/usr/bin/env python3
"""
Context Compactor - Compacts conversation context before key rotation.

When switching API keys, if the context window is large, this module:
1. Summarizes older conversation turns
2. Preserves recent messages fully
3. Keeps system prompts intact
4. Creates a compaction summary
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class CompactionResult:
    """Result of context compaction."""
    original_tokens: int
    compacted_tokens: int
    messages: List[Dict[str, Any]]
    summary: str
    preserved_count: int
    summarized_count: int


class ContextCompactor:
    """Compacts conversation context by summarizing older messages."""

    # Rough token estimation (approximate)
    TOKENS_PER_CHAR = 0.25  # ~4 chars per token

    # Default thresholds
    DEFAULT_CONTEXT_WINDOW = 256000  # Kimi K2.5 context window
    DEFAULT_COMPACTION_THRESHOLD = 0.8  # Compact at 80% capacity
    DEFAULT_PRESERVE_RECENT = 10  # Keep last 10 messages intact

    def __init__(self, context_window: Optional[int] = None):
        self.context_window = context_window or self.DEFAULT_CONTEXT_WINDOW
        self.threshold = self.DEFAULT_COMPACTION_THRESHOLD
        self.preserve_recent = self.DEFAULT_PRESERVE_RECENT

    def estimate_tokens(self, text: str) -> int:
        """Rough estimation of token count from text."""
        return int(len(text) * self.TOKENS_PER_CHAR)

    def estimate_message_tokens(self, message: Dict[str, Any]) -> int:
        """Estimate tokens for a single message."""
        content = message.get('content', '')
        # Add overhead for message structure
        return self.estimate_tokens(content) + 4  # 4 tokens overhead per message

    def estimate_total_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Estimate total tokens for message list."""
        return sum(self.estimate_message_tokens(m) for m in messages)

    def should_compact(self, messages: List[Dict[str, Any]], threshold: Optional[float] = None) -> bool:
        """Check if context should be compacted."""
        if threshold is None:
            threshold = self.threshold

        total_tokens = self.estimate_total_tokens(messages)
        return total_tokens > (self.context_window * threshold)

    def _identify_sections(self, messages: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        Split messages into sections:
        1. System messages (always preserved)
        2. Recent messages (to preserve)
        3. Older messages (to summarize)
        """
        # Separate system messages
        system_messages = [m for m in messages if m.get('role') == 'system']
        non_system = [m for m in messages if m.get('role') != 'system']

        # Split into recent (preserve) and older (summarize)
        if len(non_system) <= self.preserve_recent:
            return system_messages, non_system, []

        recent = non_system[-self.preserve_recent:]
        older = non_system[:-self.preserve_recent]

        return system_messages, recent, older

    def _summarize_messages(self, messages: List[Dict[str, Any]]) -> str:
        """
        Create a summary of older messages.

        This is a simple summarization strategy:
        - Extract key topics from user messages
        - Extract key actions from assistant messages
        - Create a condensed narrative
        """
        if not messages:
            return ""

        # Group by conversation turns
        turns = []
        current_turn = {'user': None, 'assistant': None}

        for msg in messages:
            role = msg.get('role')
            content = msg.get('content', '')

            if role == 'user':
                if current_turn['user'] is not None:
                    turns.append(current_turn)
                    current_turn = {'user': None, 'assistant': None}
                current_turn['user'] = content
            elif role == 'assistant':
                current_turn['assistant'] = content
            elif role == 'tool':
                # Tool results - keep brief mention
                if 'tool_calls' in msg:
                    current_turn['tools'] = True

        if current_turn['user'] is not None or current_turn['assistant'] is not None:
            turns.append(current_turn)

        # Generate summary
        summary_parts = []
        summary_parts.append(f"[Summary of {len(messages)} earlier messages across {len(turns)} turns]")

        # Extract key topics (from first few user messages)
        user_messages = [t['user'] for t in turns if t['user']][:3]
        if user_messages:
            topics = self._extract_topics(user_messages)
            if topics:
                summary_parts.append(f"Topics discussed: {', '.join(topics)}")

        # Note any tools used
        tools_used = any('tools' in t for t in turns)
        if tools_used:
            summary_parts.append("Tools were used during this conversation.")

        # Note any files/code mentioned
        code_files = self._extract_file_references(messages)
        if code_files:
            summary_parts.append(f"Files referenced: {', '.join(code_files[:5])}")

        return "\n".join(summary_parts)

    def _extract_topics(self, messages: List[str]) -> List[str]:
        """Extract key topics from user messages."""
        topics = []

        # Common keywords that indicate topics
        topic_indicators = [
            r'create|build|make|implement',
            r'fix|debug|solve|error|bug',
            r'add|update|modify|change|edit',
            r'deploy|install|configure|setup',
            r'analyze|review|check|test',
            r'database|api|server|client|frontend|backend',
            r'python|javascript|typescript|react|node',
        ]

        for msg in messages[:2]:  # Check first 2 messages
            msg_lower = msg.lower()
            for pattern in topic_indicators:
                if re.search(pattern, msg_lower):
                    # Extract surrounding words
                    match = re.search(r'\b\w+(?:\s+\w+){0,3}\s+' + pattern + r'(?:\s+\w+){0,3}\b', msg_lower)
                    if match:
                        topic = match.group(0).strip()
                        if topic and topic not in topics:
                            topics.append(topic)

        return topics[:5]  # Limit topics

    def _extract_file_references(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extract file paths mentioned in messages."""
        files = []
        file_pattern = r'(?:/|\w+\/)[\w\-\/]+\.(?:py|js|ts|tsx|jsx|json|md|yaml|yml|txt)'

        for msg in messages:
            content = msg.get('content', '')
            matches = re.findall(file_pattern, content)
            for match in matches:
                if match not in files:
                    files.append(match)

        return files

    def compact(self, messages: List[Dict[str, Any]],
                threshold: Optional[float] = None,
                preserve_recent: Optional[int] = None) -> CompactionResult:
        """
        Compact the conversation context.

        Args:
            messages: List of conversation messages
            threshold: Compaction threshold (default 0.8)
            preserve_recent: Number of recent messages to preserve (default 10)

        Returns:
            CompactionResult with compacted messages and metadata
        """
        if preserve_recent is None:
            preserve_recent = self.preserve_recent
        if threshold is None:
            threshold = self.threshold

        original_tokens = self.estimate_total_tokens(messages)

        # Check if compaction needed
        if not self.should_compact(messages, threshold):
            return CompactionResult(
                original_tokens=original_tokens,
                compacted_tokens=original_tokens,
                messages=messages,
                summary="No compaction needed",
                preserved_count=len(messages),
                summarized_count=0
            )

        # Split into sections
        system_msgs, recent_msgs, older_msgs = self._identify_sections(messages)

        if not older_msgs:
            return CompactionResult(
                original_tokens=original_tokens,
                compacted_tokens=original_tokens,
                messages=messages,
                summary="No older messages to summarize",
                preserved_count=len(messages),
                summarized_count=0
            )

        # Create summary of older messages
        summary = self._summarize_messages(older_msgs)

        # Build compacted message list
        compacted = []

        # 1. System messages (unchanged)
        compacted.extend(system_msgs)

        # 2. Summary message (if we have older messages)
        if summary:
            summary_msg = {
                'role': 'system',
                'content': f'[Context Compaction]\n{summary}\n\n[Recent conversation continues below...]',
                'name': 'keymaster_compactor'
            }
            compacted.append(summary_msg)

        # 3. Recent messages (preserved)
        compacted.extend(recent_msgs)

        compacted_tokens = self.estimate_total_tokens(compacted)

        return CompactionResult(
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            messages=compacted,
            summary=summary,
            preserved_count=len(system_msgs) + len(recent_msgs),
            summarized_count=len(older_msgs)
        )

    def get_compaction_report(self, result: CompactionResult) -> str:
        """Generate a human-readable compaction report."""
        savings = result.original_tokens - result.compacted_tokens
        savings_pct = (savings / result.original_tokens * 100) if result.original_tokens > 0 else 0

        report = f"""
Context Compaction Report
=========================
Original tokens: {result.original_tokens:,}
Compacted tokens: {result.compacted_tokens:,}
Savings: {savings:,} ({savings_pct:.1f}%)
Messages preserved: {result.preserved_count}
Messages summarized: {result.summarized_count}

Summary:
{result.summary}
"""
        return report.strip()


def compact_context(messages: List[Dict[str, Any]],
                   threshold: float = 0.8,
                   context_window: Optional[int] = None) -> CompactionResult:
    """
    Convenience function to compact context.

    Args:
        messages: Conversation messages
        threshold: Threshold for compaction (0.0-1.0)
        context_window: Maximum context window size

    Returns:
        CompactionResult
    """
    compactor = ContextCompactor(context_window=context_window)
    return compactor.compact(messages, threshold=threshold)


def main():
    """CLI for testing compaction."""
    import sys

    # Example usage
    example_messages = [
        {'role': 'system', 'content': 'You are Claude, an AI assistant.'},
        {'role': 'user', 'content': 'Hello, can you help me with Python?'},
        {'role': 'assistant', 'content': 'Yes, I can help with Python programming.'},
        # ... (imagine many more messages)
    ]

    compactor = ContextCompactor()

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        # Create a large test message set
        test_messages = [
            {'role': 'system', 'content': 'You are Claude, an AI assistant.'},
        ]

        # Add 50 simulated conversation turns
        for i in range(50):
            test_messages.append({'role': 'user', 'content': f'Question {i}: How do I do task {i} in Python?'})
            test_messages.append({'role': 'assistant', 'content': f'Answer {i}: To do task {i}, you can use the following approach... ' + 'x' * 500})

        result = compactor.compact(test_messages)
        print(compactor.get_compaction_report(result))
    else:
        print("Usage: context_compactor.py test")


if __name__ == "__main__":
    main()
