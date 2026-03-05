# Context Compaction Strategies

Methods for reducing context window size when approaching limits.

## Strategy 1: Summarize Older Turns

**Use when:** Context >80% full, many conversation turns

**Method:**
1. Keep system messages (unchanged)
2. Keep last 10 conversation turns (unchanged)
3. Summarize all older turns into a single system message

**Summary format:**
```
[Context Compaction]
Summary of 45 earlier messages across 23 turns
Topics discussed: Python recursion, error handling, file I/O
Files referenced: /home/user/script.py, /home/user/utils.py

[Recent conversation continues below...]
```

**Implementation:**
```python
system_msgs, recent_msgs, older_msgs = split_messages(messages)
summary = generate_summary(older_msgs)
compacted = system_msgs + [summary_msg] + recent_msgs
```

## Strategy 2: Remove System Messages

**Use when:** Multiple redundant system messages

**Method:**
1. Keep only the most recent system message
2. Remove older system prompts

**Caution:** Only if system messages are redundant

## Strategy 3: Truncate Tool Output

**Use when:** Large tool outputs in history

**Method:**
1. Identify tool result messages
2. Truncate large outputs to first/last N lines
3. Keep only essential information

**Example:**
```python
if msg.get('role') == 'tool':
    content = msg.get('content', '')
    if len(content) > 5000:
        lines = content.split('\n')
        truncated = '\n'.join(lines[:20] + ['... truncated ...'] + lines[-10:])
        msg['content'] = truncated
```

## Strategy 4: Remove Empty/Minimal Messages

**Use when:** Many short acknowledgments

**Method:**
1. Remove messages with <10 characters
2. Remove "ok", "thanks", "got it" type responses
3. Remove duplicate user confirmations

## Strategy 5: Compress Code Blocks

**Use when:** Large code blocks in conversation

**Method:**
1. Detect code blocks (```language...```)
2. Keep only first 50 and last 20 lines of large blocks
3. Add "... (truncated N lines) ..." marker

**Implementation:**
```python
def compress_code(content: str) -> str:
    lines = content.split('\n')
    if len(lines) > 100:
        return '\n'.join(
            lines[:50] +
            [f'... ({len(lines) - 70} lines truncated) ...'] +
            lines[-20:]
        )
    return content
```

## Token Estimation

### Simple Method
```python
def estimate_tokens(text: str) -> int:
    # Rough approximation: 4 characters per token
    return len(text) // 4
```

### More Accurate
```python
def estimate_tokens(text: str) -> int:
    # Count words (approx 1.3 tokens per word for English)
    words = len(text.split())
    # Add overhead for special characters, formatting
    special = len([c for c in text if c in '{}[]"\'\\'])
    return int(words * 1.3 + special * 0.5)
```

## Compaction Thresholds

| Context Window | Warning At | Compact At | Critical At |
|----------------|------------|------------|-------------|
| 128k tokens | 90k | 100k | 120k |
| 256k tokens | 180k | 200k | 240k |

## Best Practices

1. **Always preserve system prompts** - Never remove initial instructions
2. **Keep recent context** - Last 5-10 turns are most relevant
3. **Summarize, don't delete** - Provide context that conversation happened
4. **Track compaction** - Log when and why compaction occurred
5. **Avoid over-compacting** - Only compact when necessary

## Implementation Priority

1. Summarize older turns (most effective)
2. Truncate large tool outputs
3. Remove minimal messages
4. Compress code blocks
5. Remove redundant system messages (last resort)
