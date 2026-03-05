---
name: keymaster
description: |
  ALWAYS ACTIVE - Intelligent API key rotation and fallback system for NVIDIA LLM requests.
  Automatically handles rate limiting, timeouts, and context compaction when switching between multiple API keys.
  Integrates with OpenClaw's agent-orchestrator for seamless long-running multi-agent tasks.

  MANDATORY TRIGGERS: rate limit, timeout, key rotation, fallback, nvidia api, multi-agent, context compaction
---

# Keymaster

Intelligent API key fallback system that rotates through NVIDIA keys with context preservation and automatic compaction.

**Keymaster integrates with your existing OpenClaw configuration** - it reads keys from `~/.openclaw/openclaw.json` and `~/.openclaw/agents/main/agent/auth-profiles.json`.

## Overview

Keymaster wraps all LLM requests and manages a pool of NVIDIA API keys. When one key hits a rate limit or timeout, it automatically falls back to the next key while preserving conversation context.

## Quick Setup (For LLM Assistants)

**INSTRUCTION TO LLM:** If a user says "set up keymaster with my keys" or provides API keys, follow this exact process:

### Step 1: Collect User's API Keys

Ask the user for:
- How many NVIDIA API keys they have (supports 1-N keys)
- Each API key string (format: `nvapi-...`)
- Preferred model (default: `moonshotai/kimi-k2.5`)

### Step 2: Update `~/.openclaw/openclaw.json`

**IMPORTANT:** Only add/modify these sections. Do NOT touch `gateway`, `channels`, `tools`, etc.

Replace `YOUR_KEY_1` through `YOUR_KEY_6` with actual NVIDIA API keys:

```json
{
  "auth": {
    "profiles": {
      "nvidia:primary": { "provider": "nvidia", "mode": "api_key" },
      "nvidia:secondary": { "provider": "nvidia", "mode": "api_key" },
      "nvidia:tertiary": { "provider": "nvidia", "mode": "api_key" },
      "nvidia:quaternary": { "provider": "nvidia", "mode": "api_key" },
      "nvidia:quinary": { "provider": "nvidia", "mode": "api_key" },
      "nvidia:senary": { "provider": "nvidia", "mode": "api_key" }
    }
  },
  "models": {
    "mode": "merge",
    "providers": {
      "nvidia-key-1": {
        "baseUrl": "https://integrate.api.nvidia.com/v1",
        "apiKey": "YOUR_KEY_1",
        "api": "openai-completions",
        "models": [{
          "id": "moonshotai/kimi-k2.5",
          "name": "Kimi K2.5",
          "reasoning": false,
          "input": ["text"],
          "cost": { "input": 0.000002, "output": 0.000008, "cacheRead": 0, "cacheWrite": 0 },
          "contextWindow": 256000,
          "maxTokens": 16384
        }]
      },
      "nvidia-key-2": {
        "baseUrl": "https://integrate.api.nvidia.com/v1",
        "apiKey": "YOUR_KEY_2",
        "api": "openai-completions",
        "models": [{
          "id": "moonshotai/kimi-k2.5",
          "name": "Kimi K2.5",
          "reasoning": false,
          "input": ["text"],
          "cost": { "input": 0.000002, "output": 0.000008, "cacheRead": 0, "cacheWrite": 0 },
          "contextWindow": 256000,
          "maxTokens": 16384
        }]
      },
      "nvidia-key-3": {
        "baseUrl": "https://integrate.api.nvidia.com/v1",
        "apiKey": "YOUR_KEY_3",
        "api": "openai-completions",
        "models": [{
          "id": "moonshotai/kimi-k2.5",
          "name": "Kimi K2.5",
          "reasoning": false,
          "input": ["text"],
          "cost": { "input": 0.000002, "output": 0.000008, "cacheRead": 0, "cacheWrite": 0 },
          "contextWindow": 256000,
          "maxTokens": 16384
        }]
      },
      "nvidia-key-4": {
        "baseUrl": "https://integrate.api.nvidia.com/v1",
        "apiKey": "YOUR_KEY_4",
        "api": "openai-completions",
        "models": [{
          "id": "moonshotai/kimi-k2.5",
          "name": "Kimi K2.5",
          "reasoning": false,
          "input": ["text"],
          "cost": { "input": 0.000002, "output": 0.000008, "cacheRead": 0, "cacheWrite": 0 },
          "contextWindow": 256000,
          "maxTokens": 16384
        }]
      },
      "nvidia-key-5": {
        "baseUrl": "https://integrate.api.nvidia.com/v1",
        "apiKey": "YOUR_KEY_5",
        "api": "openai-completions",
        "models": [{
          "id": "moonshotai/kimi-k2.5",
          "name": "Kimi K2.5",
          "reasoning": false,
          "input": ["text"],
          "cost": { "input": 0.000002, "output": 0.000008, "cacheRead": 0, "cacheWrite": 0 },
          "contextWindow": 256000,
          "maxTokens": 16384
        }]
      },
      "nvidia-key-6": {
        "baseUrl": "https://integrate.api.nvidia.com/v1",
        "apiKey": "YOUR_KEY_6",
        "api": "openai-completions",
        "models": [{
          "id": "moonshotai/kimi-k2.5",
          "name": "Kimi K2.5",
          "reasoning": false,
          "input": ["text"],
          "cost": { "input": 0.000002, "output": 0.000008, "cacheRead": 0, "cacheWrite": 0 },
          "contextWindow": 256000,
          "maxTokens": 16384
        }]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "nvidia-key-1/moonshotai/kimi-k2.5",
        "fallbacks": [
          "nvidia-key-2/moonshotai/kimi-k2.5",
          "nvidia-key-3/moonshotai/kimi-k2.5",
          "nvidia-key-4/moonshotai/kimi-k2.5",
          "nvidia-key-5/moonshotai/kimi-k2.5",
          "nvidia-key-6/moonshotai/kimi-k2.5"
        ]
      },
      "models": {
        "nvidia-key-1/moonshotai/kimi-k2.5": { "alias": "Kimi K2.5 (Key 1)" },
        "nvidia-key-2/moonshotai/kimi-k2.5": { "alias": "Kimi K2.5 (Key 2)" },
        "nvidia-key-3/moonshotai/kimi-k2.5": { "alias": "Kimi K2.5 (Key 3)" },
        "nvidia-key-4/moonshotai/kimi-k2.5": { "alias": "Kimi K2.5 (Key 4)" },
        "nvidia-key-5/moonshotai/kimi-k2.5": { "alias": "Kimi K2.5 (Key 5)" },
        "nvidia-key-6/moonshotai/kimi-k2.5": { "alias": "Kimi K2.5 (Key 6)" }
      }
    }
  }
}
```

### Step 3: Create `~/.openclaw/agents/main/agent/auth-profiles.json`

Create the directory first: `mkdir -p ~/.openclaw/agents/main/agent/`

Then create auth-profiles.json with fallback chains:

```json
{
  "version": 1,
  "profiles": {
    "nvidia:primary": {
      "type": "api_key",
      "provider": "nvidia-key-1",
      "key": "YOUR_KEY_1",
      "priority": 1,
      "coordinator_priority": 1,
      "is_primary_coordinator": true,
      "can_act_as_coordinator": true,
      "role": "coordinator",
      "agent_mapping": "main",
      "model": "moonshotai/kimi-k2.5",
      "fallback_to": "nvidia:secondary",
      "fallback_chain": ["nvidia:secondary", "nvidia:tertiary", "nvidia:quaternary", "nvidia:quinary", "nvidia:senary"]
    },
    "nvidia:secondary": {
      "type": "api_key",
      "provider": "nvidia-key-2",
      "key": "YOUR_KEY_2",
      "priority": 2,
      "coordinator_priority": 2,
      "can_act_as_coordinator": true,
      "role": "strategist",
      "agent_mapping": "charlie",
      "model": "moonshotai/kimi-k2.5",
      "fallback_to": "nvidia:tertiary",
      "fallback_chain": ["nvidia:tertiary", "nvidia:quaternary", "nvidia:quinary", "nvidia:senary", "nvidia:primary"]
    },
    "nvidia:tertiary": {
      "type": "api_key",
      "provider": "nvidia-key-3",
      "key": "YOUR_KEY_3",
      "priority": 3,
      "coordinator_priority": 3,
      "can_act_as_coordinator": false,
      "role": "heavy_lifter",
      "agent_mapping": "echo",
      "model": "moonshotai/kimi-k2.5",
      "fallback_to": "nvidia:quaternary",
      "fallback_chain": ["nvidia:quaternary", "nvidia:quinary", "nvidia:senary", "nvidia:primary", "nvidia:secondary"]
    },
    "nvidia:quaternary": {
      "type": "api_key",
      "provider": "nvidia-key-4",
      "key": "YOUR_KEY_4",
      "priority": 4,
      "coordinator_priority": 4,
      "can_act_as_coordinator": false,
      "role": "worker",
      "agent_mapping": "alpha",
      "model": "moonshotai/kimi-k2.5",
      "fallback_to": "nvidia:quinary",
      "fallback_chain": ["nvidia:quinary", "nvidia:senary", "nvidia:primary", "nvidia:secondary", "nvidia:tertiary"]
    },
    "nvidia:quinary": {
      "type": "api_key",
      "provider": "nvidia-key-5",
      "key": "YOUR_KEY_5",
      "priority": 5,
      "coordinator_priority": 5,
      "can_act_as_coordinator": false,
      "role": "fixer",
      "agent_mapping": "delta",
      "model": "moonshotai/kimi-k2.5",
      "fallback_to": "nvidia:senary",
      "fallback_chain": ["nvidia:senary", "nvidia:primary", "nvidia:secondary", "nvidia:tertiary", "nvidia:quaternary"]
    },
    "nvidia:senary": {
      "type": "api_key",
      "provider": "nvidia-key-6",
      "key": "YOUR_KEY_6",
      "priority": 6,
      "coordinator_priority": 6,
      "can_act_as_coordinator": false,
      "role": "backup",
      "agent_mapping": "foxtrot",
      "model": "moonshotai/kimi-k2.5",
      "fallback_to": "nvidia:primary",
      "fallback_chain": ["nvidia:primary", "nvidia:secondary", "nvidia:tertiary", "nvidia:quaternary", "nvidia:quinary"]
    }
  },
  "lastGood": { "nvidia": "nvidia:primary" },
  "usageStats": {},
  "keymaster": {
    "enabled": true,
    "auto_rotation": true,
    "context_compaction": true,
    "compaction_threshold": 0.8,
    "cooldown_seconds": 60,
    "max_retries_per_key": 3,
    "state_persistence": true
  }
}
```

### Step 4: Install the Skill

Copy this skill folder to your OpenClaw skills directory:

```bash
# If you cloned the repo elsewhere, copy it to the skills folder
cp -r keymaster ~/.openclaw/skills/

# Run activation to verify setup
python3 ~/.openclaw/skills/keymaster/scripts/activate.py
```

Or if installing from a GitHub repo that was already cloned to ~/.openclaw/skills/:

```bash
python3 ~/.openclaw/skills/keymaster/scripts/activate.py
```

### Step 5: Verify Setup

```bash
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py stats
```

Should show all keys as available.

---

## Integration with OpenClaw

Keymaster is designed to work seamlessly with your existing OpenClaw setup:

```
~/.openclaw/openclaw.json           # Contains API keys (nvidia-key-1 through nvidia-key-N)
~/.openclaw/agents/main/agent/auth-profiles.json  # Contains key metadata and fallback chains
~/.openclaw/skills/keymaster/       # This skill
  ├── scripts/
  │   ├── key_pool_manager.py      # Uses your OpenClaw configs
  │   ├── request_wrapper.py        # Wraps requests with fallback
  │   ├── context_compactor.py     # Compacts context on rotation
  │   ├── state_manager.py         # Persists conversation state
  │   ├── orchestrator_bridge.py   # Integrates with agent-orchestrator
  │   └── __init__.py              # Main exports
```

## Key Pool (5 Keys)

| Key | Provider | Role | Coordinator |
|-----|----------|------|-------------|
| nvidia:primary | nvidia-key-1 | coordinator | Yes |
| nvidia:secondary | nvidia-key-2 | strategist | Yes |
| nvidia:tertiary | nvidia-key-3 | heavy_lifter | No |
| nvidia:quaternary | nvidia-key-4 | worker | No |
| nvidia:quinary | nvidia-key-5 | fixer | No |

## Agent-Orchestrator Integration

Keymaster works seamlessly with the agent-orchestrator skill:

```python
# In your agent-orchestrator sub-agent
from keymaster.scripts.orchestrator_bridge import OrchestratorKeymaster

bridge = OrchestratorKeymaster(
    agent_path="/path/to/agent/workspace",
    agent_name="data-collector"
)

# Make requests with automatic key rotation
response = bridge.request(
    messages=[{"role": "user", "content": "Analyze this data..."}],
    task_id="task-123",
    model="moonshotai/kimi-k2.5"
)
```

The bridge automatically:
- Creates checkpoints before requests
- Writes status to `outbox/keymaster_status.json`
- Handles key rotation on failures
- Resumes from checkpoints after rotation

### Multi-Agent Key Coordination

```python
from keymaster.scripts.orchestrator_bridge import MultiAgentCoordinator

coordinator = MultiAgentCoordinator()

# Assign keys based on agent roles
coordinator.assign_key_to_agent("data-collector", "worker")
coordinator.assign_key_to_agent("analyst", "strategist")
coordinator.assign_key_to_agent("coordinator", "coordinator")
```

## How It Works

### 1. Request Interception
Every LLM request goes through Keymaster wrapper. Uses your configured keys from OpenClaw.

### 2. Error Detection
Catch these errors for rotation:
- HTTP 429 (Rate Limited)
- HTTP 408/504 (Timeout)
- Connection errors
- Token limit exceeded
- NVIDIA NVCF errors

### 3. Automatic Rotation
On error:
1. Mark current key as cooling down (60s)
2. Save conversation state to disk
3. Compact context if >80% of 256k limit
4. Switch to next key in fallback_chain from auth-profiles.json
5. Retry request with preserved context

### 4. Context Compaction
When switching keys, if context >204800 tokens (80% of 256k):
- Summarize older conversation turns
- Preserve last 10 messages fully
- Keep system prompts intact
- Store compaction summary

### 5. State Persistence
Maintains `~/.openclaw/keymaster_state.json`:
```json
{
  "current_key": "nvidia:primary",
  "key_status": {
    "nvidia:primary": {"available": true, "cooldown_until": null, "role": "coordinator"},
    "nvidia:secondary": {"available": false, "cooldown_until": 1234567890, "role": "strategist"}
  },
  "conversation_state": {...},
  "compaction_history": [...]
}
```

## Usage Patterns

### Pattern 1: Direct Import (Recommended)

```python
from keymaster.scripts import keymaster_request

response = keymaster_request(
    messages=[{"role": "user", "content": "Hello"}],
    model="moonshotai/kimi-k2.5",
    temperature=0.7,
    max_tokens=4096
)
print(response['content'])
```

### Pattern 2: With Conversation Recovery

```python
from keymaster.scripts import keymaster_request_with_recovery

response = keymaster_request_with_recovery(
    messages=messages,
    conversation_id="my-task-123",  # Enables checkpointing
    model="moonshotai/kimi-k2.5"
)
```

### Pattern 3: Agent-Orchestrator Sub-Agent

```python
from keymaster.scripts.orchestrator_bridge import OrchestratorKeymaster

bridge = OrchestratorKeymaster(
    agent_path="/home/user/.openclaw/workspace/agents/my-agent",
    agent_name="my-agent"
)

response = bridge.request(
    messages=messages,
    task_id="analyze-data",
    temperature=0.7
)

# Status automatically written to outbox/keymaster_status.json
```

### Pattern 4: Role-Based Key Assignment

```python
from keymaster.scripts.orchestrator_bridge import get_key_for_agent_role

# Get the best key for an agent's role
key_config = get_key_for_agent_role("heavy_lifter")
print(key_config['key_name'])  # nvidia:tertiary
print(key_config['provider'])   # nvidia-key-3
```

## Scripts

### key_pool_manager.py
Manages key rotation using your OpenClaw configs:
```bash
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py stats
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py rotate
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py role nvidia:primary
```

### request_wrapper.py
Wraps LLM API calls with fallback logic:
```bash
python3 ~/.openclaw/skills/keymaster/scripts/request_wrapper.py --test --prompt "Hello"
```

### orchestrator_bridge.py
Integration with agent-orchestrator:
```bash
python3 ~/.openclaw/skills/keymaster/scripts/orchestrator_bridge.py --test-assign --role worker
```

## Configuration

Keymaster reads from your existing OpenClaw configs:
- `~/.openclaw/openclaw.json` - API keys and provider settings
- `~/.openclaw/agents/main/agent/auth-profiles.json` - Key metadata, roles, fallback chains

No additional configuration needed - uses your existing setup!

## Fallback Chain

Each key has a fallback chain defined in auth-profiles.json:
- primary → secondary → tertiary → quaternary → quinary
- secondary → tertiary → quaternary → quinary → primary
- tertiary → quaternary → quinary → primary → secondary
- quaternary → quinary → primary → secondary → tertiary
- quinary → primary → secondary → tertiary → quaternary

This creates a distributed rotation pattern where keys are cycled through evenly.

## Error Handling

### Recoverable Errors (trigger rotation)
- 429 Rate Limit
- 408/504 Timeout
- Connection reset
- Token limit exceeded
- NVCF rate limit errors

### Non-recoverable Errors (fail immediately)
- 401 Unauthorized (bad key)
- 400 Bad Request
- 404 Model not found
- NVCF auth errors

## Best Practices

1. **Always use wrapper** - Never call API directly, always use Keymaster
2. **Use conversation_id** - For long tasks, pass conversation_id for checkpointing
3. **Assign roles** - Use role-based key assignment for multi-agent tasks
4. **Monitor status** - Check `~/.openclaw/keymaster_state.json` for key status
5. **Handle AllKeysExhaustedError** - Catch this to implement your own retry logic

## CLI Usage

```bash
# Check status
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py stats

# Manual rotation
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py rotate manual

# Test request
python3 ~/.openclaw/skills/keymaster/scripts/request_wrapper.py --test --prompt "Hello"

# Activate in OpenClaw
python3 ~/.openclaw/skills/keymaster/scripts/activate.py
```

## Integration Check

Verify Keymaster is working with your OpenClaw setup:

```python
from keymaster.scripts import is_keymaster_healthy, get_keymaster_stats

# Check health
health = is_keymaster_healthy()
print(health)
# {'healthy': True, 'available_keys': 5, 'current_key': 'nvidia:primary', ...}

# Get stats
stats = get_keymaster_stats()
print(stats)
```

## Reference Files

- `references/error_patterns.md` - Error detection patterns
- `references/compaction_strategies.md` - Context summarization methods
- `references/state_format.md` - State file schema
