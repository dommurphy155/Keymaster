# OpenClaw Keymaster - Complete Setup Guide

**For LLM Assistants:** This guide helps you set up Keymaster on any machine with any username.

---

## Quick Setup Command

When a user says:
> "Set up keymaster" or "I have X API keys, configure keymaster"

**YOU (the LLM) should:**

### Step 1: Verify Location

Check if keymaster is already installed:
```bash
if [ -d "$HOME/.openclaw/skills/keymaster/.git" ]; then
    echo "Keymaster already installed"
    cd "$HOME/.openclaw/skills/keymaster"
    git pull origin main
else
    echo "Installing fresh..."
    git clone https://github.com/dommurphy155/Keymaster.git "$HOME/.openclaw/skills/keymaster"
fi
```

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
      "nvidia:tertiary": { "provider": "nvidia", "mode": "api_key" }
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
      }
    }
  }
}
```

**IMPORTANT:** Only modify `auth`, `models.providers`, and `agents.defaults` sections. Preserve their existing `gateway`, `channels`, `tools`, etc.

#### File 2: `~/.openclaw/agents/main/agent/auth-profiles.json`

Create this file (and parent directories):
```bash
mkdir -p "$HOME/.openclaw/agents/main/agent/"
```

Then create auth-profiles.json:

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
      "fallback_chain": ["nvidia:secondary", "nvidia:tertiary"]
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
      "fallback_chain": ["nvidia:tertiary", "nvidia:primary"]
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
      "fallback_to": "nvidia:primary",
      "fallback_chain": ["nvidia:primary", "nvidia:secondary"]
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
cd "$HOME/.openclaw/skills/keymaster"
bash install.sh
```

### Step 5: Verify Setup
```bash
# Check keymaster status
keymaster status

# Test a request
keymaster health
```

Expected output: All keys should show as available.

---

## Role-Based Key Assignment

The keys have specific roles:

| Key | Role | Best For |
|-----|------|----------|
| `nvidia:primary` | coordinator | Main agent, task coordination |
| `nvidia:secondary` | strategist | Analysis/planning agents |
| `nvidia:tertiary` | heavy_lifter | Data processing agents |
| `nvidia:quaternary` | worker | General purpose agents |
| `nvidia:quinary` | fixer | Error recovery agents |

---

## Configuration for Different Key Counts

### 3 Keys Setup
- Keep: primary, secondary, tertiary
- Remove: quaternary, quinary, senary references
- Update fallback chains to only include existing keys

### 10 Keys Setup
- Add: `nvidia:septenary` (7), `nvidia:octonary` (8), `nvidia:nonary` (9), `nvidia:denary` (10)
- Follow the same pattern for providers and fallback chains

---

## Troubleshooting

**"No API key found for nvidia:primary"**
- Check that `openclaw.json` has the providers section
- Run `keymaster status`

**"All API keys exhausted"**
- All keys are on cooldown (rate limited)
- Wait 60 seconds or run: `keymaster reset`

**"auth-profiles.json not found"**
- Create the directory: `mkdir -p ~/.openclaw/agents/main/agent/`
- Create the file with the template above

---

## Files Modified

| File | Purpose |
|------|---------|
| `~/.openclaw/openclaw.json` | API keys and model providers |
| `~/.openclaw/agents/main/agent/auth-profiles.json` | Key roles, fallback chains, keymaster settings |
| `~/.openclaw/keymaster.log` | Unified logs |

---

## Next Steps

Once configured:

1. **Keymaster** automatically rotates keys on rate limits
2. **All logs** go to `~/.openclaw/keymaster.log`
3. Use `keymaster` command for all management
4. OpenClaw works normally - rotation is transparent
