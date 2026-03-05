# Keymaster - API Key Fallback System

**Intelligent API key rotation and fallback for OpenClaw with NVIDIA keys.**

Keymaster integrates with your existing OpenClaw configuration to automatically rotate through 5 NVIDIA API keys when rate limits or timeouts occur. Perfect for long-running tasks and multi-agent orchestration.

## Features

- **Auto Rotation**: On rate limit (429) or timeout (408/504)
- **Context Preservation**: Carries conversation state to next key
- **Context Compaction**: Summarizes older messages when >80% context window
- **Cooldown Tracking**: 60-second cooldown for rate-limited keys
- **Agent-Orchestrator Integration**: Seamless multi-agent key coordination
- **Uses Your Configs**: Reads from your existing `openclaw.json` and `auth-profiles.json`

## Quick Start

```python
from keymaster.scripts import keymaster_request

# Use instead of direct API calls
response = keymaster_request(
    messages=[{"role": "user", "content": "Hello"}],
    model="moonshotai/kimi-k2.5",
    temperature=0.7
)

print(response['content'])
```

## Agent-Orchestrator Integration

```python
from keymaster.scripts.orchestrator_bridge import OrchestratorKeymaster

# Create bridge for your sub-agent
bridge = OrchestratorKeymaster(
    agent_path="/path/to/agent",
    agent_name="data-collector"
)

# Request with automatic checkpointing
response = bridge.request(
    messages=messages,
    task_id="task-123"
)
```

## Key Pool (5 Keys)

| Key | Provider | Role |
|-----|----------|------|
| nvidia:primary | nvidia-key-1 | coordinator |
| nvidia:secondary | nvidia-key-2 | strategist |
| nvidia:tertiary | nvidia-key-3 | heavy_lifter |
| nvidia:quaternary | nvidia-key-4 | worker |
| nvidia:quinary | nvidia-key-5 | fixer |

## CLI Usage

```bash
# Check key status
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py stats

# Manual rotation
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py rotate

# Test request
python3 ~/.openclaw/skills/keymaster/scripts/request_wrapper.py --test

# Activate
python3 ~/.openclaw/skills/keymaster/scripts/activate.py
```

## Configuration

Keymaster automatically reads from your OpenClaw configs:

- `~/.openclaw/openclaw.json` - API keys (nvidia-key-1 through nvidia-key-5)
- `~/.openclaw/agents/main/agent/auth-profiles.json` - Key roles and fallback chains

No additional setup needed!

## Files

```
~/.openclaw/skills/keymaster/
├── SKILL.md                      # Main documentation
├── README.md                     # This file
├── QUICKSTART.md                 # Quick start guide
├── scripts/
│   ├── key_pool_manager.py      # Key rotation (uses your configs)
│   ├── request_wrapper.py        # API request wrapper
│   ├── context_compactor.py     # Context compaction
│   ├── state_manager.py         # State persistence
│   ├── orchestrator_bridge.py   # Agent-orchestrator integration
│   └── __init__.py              # Module interface
└── references/
    ├── error_patterns.md        # Error detection
    └── compaction_strategies.md # Compaction methods
```

## Health Check

```python
from keymaster.scripts import is_keymaster_healthy

health = is_keymaster_healthy()
print(health)
# {'healthy': True, 'available_keys': 5, 'current_key': 'nvidia:primary'}
```

## State Files

- `~/.openclaw/keymaster_state.json` - Key status and stats
- `~/.openclaw/keymaster_checkpoints/` - Conversation checkpoints

## Integration

To use Keymaster in your OpenClaw agents:

```python
# Instead of direct API calls:
import openai
response = openai.ChatCompletion.create(...)

# Use Keymaster:
from keymaster.scripts import keymaster_request
response = keymaster_request(messages, model="...")

# Or with agent-orchestrator:
from keymaster.scripts.orchestrator_bridge import OrchestratorKeymaster
bridge = OrchestratorKeymaster(agent_path=..., agent_name=...)
response = bridge.request(messages, task_id="...")
```

Keymaster is always active and intercepts all LLM requests for automatic fallback.
