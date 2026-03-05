# Keymaster Quickstart

**Intelligent API key rotation for OpenClaw with Agent-Orchestrator support.**

## What It Does

Your OpenClaw runs for ~10 minutes, then hits rate limits/timeouts. Keymaster automatically:
1. Detects rate limits (429) and timeouts (408/504)
2. Switches to the next NVIDIA API key
3. Preserves your conversation context
4. Compacts context if it gets too large
5. Retries the request

**All without you having to do anything!**

## Installation

Already installed at `~/.openclaw/skills/keymaster/`

It reads keys from your existing:
- `~/.openclaw/openclaw.json`
- `~/.openclaw/agents/main/agent/auth-profiles.json`

## Usage

### Method 1: Direct Import (Recommended)

```python
from keymaster.scripts import keymaster_request

response = keymaster_request(
    messages=[
        {"role": "system", "content": "You are Claude."},
        {"role": "user", "content": "Hello!"}
    ],
    model="moonshotai/kimi-k2.5",
    temperature=0.7,
    max_tokens=4096
)

print(response['content'])
```

### Method 2: With Conversation Recovery

For long-running tasks, pass a `conversation_id`:

```python
from keymaster.scripts import keymaster_request_with_recovery

response = keymaster_request_with_recovery(
    messages=messages,
    conversation_id="my-long-task-123",  # Enables checkpointing
    model="moonshotai/kimi-k2.5"
)
```

### Method 3: Agent-Orchestrator Sub-Agent

When building agents that work with agent-orchestrator:

```python
from keymaster.scripts.orchestrator_bridge import OrchestratorKeymaster

bridge = OrchestratorKeymaster(
    agent_path="/home/user/.openclaw/workspace/agents/data-collector",
    agent_name="data-collector"
)

# This writes status to outbox/keymaster_status.json
response = bridge.request(
    messages=messages,
    task_id="collect-market-data"
)
```

### Method 4: Multi-Agent Key Coordination

When spawning multiple agents:

```python
from keymaster.scripts.orchestrator_bridge import MultiAgentCoordinator

coordinator = MultiAgentCoordinator()

# Each agent gets a different key based on role
agents = [
    {"name": "coordinator", "role": "coordinator"},
    {"name": "researcher", "role": "strategist"},
    {"name": "worker1", "role": "worker"},
    {"name": "worker2", "role": "heavy_lifter"}
]

for agent in agents:
    key = coordinator.assign_key_to_agent(agent['name'], agent['role'])
    print(f"{agent['name']}: {key}")
```

## Key Pool

| Key | Provider | Role | When to Use |
|-----|----------|------|-------------|
| nvidia:primary | nvidia-key-1 | coordinator | Main coordinator agents |
| nvidia:secondary | nvidia-key-2 | strategist | Analysis/planning agents |
| nvidia:tertiary | nvidia-key-3 | heavy_lifter | Data processing agents |
| nvidia:quaternary | nvidia-key-4 | worker | General purpose agents |
| nvidia:quinary | nvidia-key-5 | fixer | Error recovery agents |

## How It Works

1. **Request made** → Uses current key (default: primary)
2. **Rate limit hit** → Marks key cooldown, rotates to next
3. **Context large?** → Compacts before rotation
4. **Retry** → Uses new key with preserved context
5. **Success!** → Continues with new key

## CLI Testing

```bash
# Test the wrapper
python3 ~/.openclaw/skills/keymaster/scripts/request_wrapper.py --test --prompt "Hello"

# Test with conversation ID
python3 ~/.openclaw/skills/keymaster/scripts/request_wrapper.py --test --prompt "Hello" --conversation-id test-123

# Check key status
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py stats

# View available keys
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py available

# Manually rotate keys
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py rotate manual

# Check role of a key
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py role nvidia:primary

# Activate (verify setup)
python3 ~/.openclaw/skills/keymaster/scripts/activate.py
```

## State Files

- `~/.openclaw/keymaster_state.json` - Current key, cooldowns, stats
- `~/.openclaw/keymaster_checkpoints/` - Conversation checkpoints

## Health Check

```python
from keymaster.scripts import is_keymaster_healthy

health = is_keymaster_healthy()
print(health)
```

Output:
```python
{
    'healthy': True,
    'available_keys': 5,
    'total_keys': 5,
    'current_key': 'nvidia:primary',
    'missing_keys': []
}
```

## Configuration

Keymaster uses your existing OpenClaw config. No changes needed!

Your `~/.openclaw/openclaw.json` already has:
- 5 NVIDIA keys configured (nvidia-key-1 through nvidia-key-5)
- Fallback chain

Your `~/.openclaw/agents/main/agent/auth-profiles.json` already has:
- Key roles and priorities
- Fallback chains

## Common Issues

### "No API key found for nvidia:primary"

Check that your `~/.openclaw/openclaw.json` has the keys:
```bash
python3 ~/.openclaw/skills/keymaster/scripts/activate.py
```

### "All API keys exhausted"

All 5 keys are on cooldown. Wait 60 seconds and try again:
```python
from keymaster.scripts import reset_all_keys
reset_all_keys()
```

### Checkpoint not found

Checkpoints are saved by conversation_id. Make sure you're using the same ID:
```python
from keymaster.scripts.state_manager import StateManager
sm = StateManager()
checkpoints = sm.list_checkpoints("my-conversation-id")
print(checkpoints)
```

## Integration with Agent-Orchestrator

When using with agent-orchestrator, Keymaster:

1. **Creates checkpoints** before each request
2. **Writes status** to `outbox/keymaster_status.json`
3. **Handles rotation** automatically
4. **Resumes** from checkpoints on failure

Example status file written to outbox:
```json
{
  "status": "success",
  "current_key": "nvidia:secondary",
  "keys_used": ["nvidia:primary", "nvidia:secondary"],
  "rotations": 1,
  "checkpoint": "data-collector-task-123_1234567890"
}
```

## Troubleshooting

```bash
# Reset all keys
python3 -c "from keymaster.scripts import reset_all_keys; reset_all_keys()"

# Clear checkpoints
python3 -c "from keymaster.scripts.state_manager import StateManager; StateManager().clear_all_checkpoints()"

# Test with specific key
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py rotate
python3 ~/.openclaw/skills/keymaster/scripts/request_wrapper.py --test
```

## Support

For issues:
1. Run `activate.py` to verify setup
2. Check `~/.openclaw/keymaster_state.json`
3. Ensure keys are in `~/.openclaw/openclaw.json`
