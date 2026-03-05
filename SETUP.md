# OpenClaw Skills Setup Guide

**For LLM Assistants:** This guide helps you set up both `keymaster` and `agent-orchestrator` skills for a user who has just pulled this repository.

## Repository Structure

This repo contains two OpenClaw skills:

```
~/.openclaw/skills/
├── keymaster/           # API key rotation with fallback
│   ├── SKILL.md
│   ├── scripts/
│   └── references/
└── agent-orchestrator/  # Multi-agent task orchestration
    ├── SKILL.md
    └── references/
```

## Quick Setup Command

When a user says:
> "Set up these skills" or "I have X API keys, configure keymaster"

**YOU (the LLM) should:**

### Step 1: Verify Location

Confirm skills are at `~/.openclaw/skills/keymaster/` and `~/.openclaw/skills/agent-orchestrator/`. If the user cloned elsewhere, copy them there.

### Step 2: Collect Information

Ask the user:
1. **How many NVIDIA API keys do you have?** (supports 1-10+)
2. **Provide each key** (format: `nvapi-...`)
3. **What model?** (default: `moonshotai/kimi-k2.5`)

### Step 3: Create Config Files

Create these two files with the user's keys:

#### File 1: `~/.openclaw/openclaw.json` (merge into existing)

Add/update ONLY these sections (preserve their existing gateway, channels, etc):

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
        "apiKey": "USER_KEY_1",
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
        "apiKey": "USER_KEY_2",
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
        "apiKey": "USER_KEY_3",
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
        "apiKey": "USER_KEY_4",
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
        "apiKey": "USER_KEY_5",
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
        "apiKey": "USER_KEY_6",
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

**IMPORTANT:** Only modify `auth`, `models.providers`, and `agents.defaults` sections. Preserve their existing `gateway`, `channels`, `tools`, etc.

#### File 2: `~/.openclaw/agents/main/agent/auth-profiles.json`

Create this file (and parent directories):

```bash
mkdir -p ~/.openclaw/agents/main/agent/
```

Then create `auth-profiles.json`:

```json
{
  "version": 1,
  "profiles": {
    "nvidia:primary": {
      "type": "api_key",
      "provider": "nvidia-key-1",
      "key": "USER_KEY_1",
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
      "key": "USER_KEY_2",
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
      "key": "USER_KEY_3",
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
      "key": "USER_KEY_4",
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
      "key": "USER_KEY_5",
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
      "key": "USER_KEY_6",
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

### Step 4: Activate Keymaster

```bash
python3 ~/.openclaw/skills/keymaster/scripts/activate.py
```

### Step 5: Verify Setup

```bash
# Check keymaster status
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py stats

# Test a request
python3 ~/.openclaw/skills/keymaster/scripts/request_wrapper.py --test --prompt "Hello"
```

Expected output: All keys should show as available.

### Step 6: Test Agent-Orchestrator Integration

```python
# Quick test
from keymaster.scripts.orchestrator_bridge import OrchestratorKeymaster

bridge = OrchestratorKeymaster(
    agent_path="/tmp/test-agent",
    agent_name="test-agent"
)

print("Agent-orchestrator bridge ready!")
```

## Role-Based Key Assignment

The keys have specific roles:

| Key | Role | Best For |
|-----|------|----------|
| `nvidia:primary` | coordinator | Main agent, task coordination |
| `nvidia:secondary` | strategist | Analysis, planning |
| `nvidia:tertiary` | heavy_lifter | Data processing |
| `nvidia:quaternary` | worker | General purpose |
| `nvidia:quinary` | fixer | Error recovery |
| `nvidia:senary` | backup | Overflow/backup |

## Configuration for Different Key Counts

If user has fewer/more keys, adjust the templates:

### 3 Keys Setup
- Keep: primary, secondary, tertiary
- Remove: quaternary, quinary, senary references
- Update fallback chains to only include existing keys

### 10 Keys Setup
- Add: `nvidia:septenary` (7), `nvidia:octonary` (8), `nvidia:nonary` (9), `nvidia:denary` (10)
- Follow the same pattern for providers and fallback chains

## Troubleshooting

**"No API key found for nvidia:primary"**
- Check that `openclaw.json` has the providers section
- Run `python3 ~/.openclaw/skills/keymaster/scripts/activate.py`

**"All API keys exhausted"**
- All keys are on cooldown (rate limited)
- Wait 60 seconds or run: `python3 -c "from keymaster.scripts import reset_all_keys; reset_all_keys()"`

**"auth-profiles.json not found"**
- Create the directory: `mkdir -p ~/.openclaw/agents/main/agent/`
- Create the file with the template above

## Files Modified

| File | Purpose |
|------|---------|
| `~/.openclaw/openclaw.json` | API keys and model providers |
| `~/.openclaw/agents/main/agent/auth-profiles.json` | Key roles, fallback chains, keymaster settings |
| `~/.openclaw/keymaster_state.json` | Auto-generated, stores key status |

## Next Steps

Once configured:

1. **Keymaster** automatically rotates keys on rate limits
2. **Agent-Orchestrator** can spawn sub-agents with key coordination
3. Use `from keymaster.scripts import keymaster_request` instead of direct API calls
4. Use `from keymaster.scripts.orchestrator_bridge import OrchestratorKeymaster` for multi-agent tasks
