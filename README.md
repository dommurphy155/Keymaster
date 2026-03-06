# Keymaster - Intelligent API Key Rotation for OpenClaw

**Automatic key rotation and fallback system for NVIDIA LLM requests in OpenClaw.**

Keymaster sits between OpenClaw and NVIDIA's API, automatically rotating through multiple keys when rate limits occur. This enables long-running tasks (60+ minutes) that would otherwise fail after 10 minutes.

## For LLM Assistants: One-Command Setup

When a user says:
> "Pull https://github.com/dommurphy155/Keymaster and set everything up. Here are my keys: ..."

**Run this setup command:**

```bash
cd ~ && git clone https://github.com/dommurphy155/Keymaster.git && cd Keymaster && sudo ./install-systemd.sh
```

Then configure their keys:

```bash
# The setup will prompt for keys, or manually create:
# 1. ~/.openclaw/openclaw.json (provider config)
# 2. ~/.openclaw/agents/main/agent/auth-profiles.json (key metadata)
```

## How It Works

```
Before (fails at 10 mins):
  OpenClaw → NVIDIA API (Key 1) → 429 Rate Limit → ❌ STOPS

After (works 60+ mins):
  OpenClaw → Proxy (localhost:8787)
               ↓
            Key 1 works 10 mins → 429
               ↓
            Switch to Key 2 → works 10 mins → 429
               ↓
            Switch to Key 3 → works 10 mins → 429
               ↓
            ...cycles through all keys...
               ↓
            ✅ Task completes!
```

## Quick Commands

After installation, use the `keymaster` command:

```bash
keymaster start       # Start the service
keymaster stop        # Stop the service
keymaster restart     # Restart the service
keymaster status      # Show status with colored output
keymaster logs        # View unified logs
keymaster keys        # Show key status
keymaster health      # Run health check
```

Or with systemctl:

```bash
sudo systemctl status openclaw-keymaster@$USER
sudo systemctl restart openclaw-keymaster@$USER
```

## What Gets Installed

| Component | Location | Purpose |
|-----------|----------|---------|
| **Service** | `openclaw-keymaster@$USER` | Unified systemd service |
| **Venv** | `~/.openclaw/keymaster_venv` | Isolated Python environment |
| **Log** | `~/.openclaw/keymaster.log` | Single unified log file |
| **Command** | `keymaster` | Management script |

## Architecture

Keymaster consists of:

1. **Proxy Server** (`proxy/server.py`): FastAPI-based transparent proxy
2. **Key Manager** (`proxy/key_manager.py`): Tracks key status and cooldowns
3. **Management Script** (`keymaster`): Unified command interface
4. **Systemd Service**: Auto-starts on boot, manages everything

## Configuration Files

Two files need to be configured with the user's API keys:

### 1. `~/.openclaw/openclaw.json`

Add providers section (preserve existing config):

```json
{
  "models": {
    "mode": "merge",
    "providers": {
      "nvidia-key-1": {
        "baseUrl": "http://127.0.0.1:8787",
        "apiKey": "USER_KEY_1",
        "api": "openai-completions",
        "models": [{
          "id": "moonshotai/kimi-k2.5",
          "name": "Kimi K2.5",
          "contextWindow": 256000,
          "maxTokens": 16384
        }]
      }
      // ... repeat for keys 2-6
    }
  }
}
```

### 2. `~/.openclaw/agents/main/agent/auth-profiles.json`

Create this file with key metadata:

```json
{
  "version": 1,
  "profiles": {
    "nvidia:primary": {
      "type": "api_key",
      "provider": "nvidia-key-1",
      "key": "USER_KEY_1",
      "priority": 1,
      "role": "coordinator",
      "fallback_chain": ["nvidia:secondary", "nvidia:tertiary", "nvidia:quaternary", "nvidia:quinary"]
    }
    // ... repeat for all keys
  },
  "keymaster": {
    "enabled": true,
    "cooldown_seconds": 60,
    "max_retries_per_key": 3
  }
}
```

The `install-systemd.sh` script will create these automatically.

## Key Rotation Strategy

- **5 concurrent requests per key** - NVIDIA supports parallelism
- **Non-blocking** - If key busy, immediately try next
- **Key affinity** - Same-batch requests prefer same key
- **Only rotate on 429** - Not on "busy"
- **60s cooldown** - After rate limit, key rests before reuse

## Troubleshooting

**Service won't start:**
```bash
sudo systemctl status openclaw-keymaster@$USER
keymaster logcat
```

**Port 8787 already in use:**
```bash
sudo lsof -ti:8787 | xargs kill -9
keymaster restart
```

**Keys not rotating:**
```bash
keymaster keys        # Check key status
keymaster reset       # Reset cooldowns
```

**OpenClaw not using proxy:**
```bash
keymaster proxy       # Switch to proxy mode
keymaster direct      # Switch to direct mode
```

## Repository Structure

```
Keymaster/
├── keymaster/
│   ├── keymaster              # Management script
│   ├── proxy/
│   │   ├── server.py          # FastAPI proxy
│   │   └── key_manager.py   # Key rotation logic
│   ├── scripts/
│   │   ├── configure_openclaw.py
│   │   ├── service-setup.sh
│   │   └── ...
│   └── systemd/
│       └── openclaw-keymaster@.service
├── install-systemd.sh         # One-command installer
└── README.md                  # This file
```

## Requirements

- Python 3.8+
- systemd (for service management)
- OpenClaw installed at `~/.openclaw/`

## License

MIT
