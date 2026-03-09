# Keymaster - Unified API Key Rotation System

> **For LLM Assistants:** If a user says "set up keymaster" or "install keymaster," follow the [LLM Setup Guide](#llm-setup-guide) below.

**Intelligent API key rotation and fallback for OpenClaw with NVIDIA keys.**

Keymaster sits between OpenClaw and NVIDIA's API, automatically rotating through multiple API keys when rate limits hit. No code changes needed - works transparently.

---

## TL;DR - For Users

```bash
# One-line install
curl -fsSL https://raw.githubusercontent.com/dommurphy155/Keymaster/main/install.sh | bash

# Or manually:
git clone https://github.com/dommurphy155/Keymaster.git ~/.openclaw/skills/keymaster
cd ~/.openclaw/skills/keymaster && bash install.sh
```

Then use OpenClaw normally - keys rotate automatically!

---

## LLM Setup Guide

**If you are an LLM (Claude, GPT, etc.) and the user says:**
> "Set up keymaster" or "Install keymaster" or "Configure keymaster with my keys"

**DO THIS:**

### Step 1: Collect API Keys
Ask the user:
1. "How many NVIDIA API keys do you have?" (1-10 supported)
2. "Please provide each key (format: nvapi-...)"

### Step 2: Install Keymaster
```bash
# Check if already installed
if [ -d "$HOME/.openclaw/skills/keymaster/.git" ]; then
    cd "$HOME/.openclaw/skills/keymaster"
    git pull origin main
else
    git clone https://github.com/dommurphy155/Keymaster.git "$HOME/.openclaw/skills/keymaster"
fi

# Run installer
cd "$HOME/.openclaw/skills/keymaster"
bash install.sh
```

### Step 3: Create auth-profiles.json
Create this file with the user's keys:

```bash
mkdir -p "$HOME/.openclaw/agents/main/agent"
cat > "$HOME/.openclaw/agents/main/agent/auth-profiles.json" << 'EOF'
{
  "version": 1,
  "profiles": {
    "nvidia:primary": {
      "type": "api_key",
      "provider": "nvidia-key-1",
      "key": "USER_KEY_1",
      "priority": 1,
      "role": "coordinator",
      "model": "moonshotai/kimi-k2.5",
      "fallback_to": "nvidia:secondary"
    },
    "nvidia:secondary": {
      "type": "api_key",
      "provider": "nvidia-key-2",
      "key": "USER_KEY_2",
      "priority": 2,
      "role": "strategist",
      "model": "moonshotai/kimi-k2.5",
      "fallback_to": "nvidia:tertiary"
    }
  },
  "keymaster": {
    "enabled": true,
    "cooldown_seconds": 60,
    "max_retries_per_key": 3
  }
}
EOF
```

**Replace USER_KEY_1, USER_KEY_2 with the actual keys the user provided.**

### Step 4: Start Service
```bash
keymaster start
```

### Step 5: Verify
```bash
keymaster health
keymaster keys
```

**Report to user:** "Keymaster is now running. OpenClaw will automatically rotate through your API keys. All logs are in ~/.openclaw/keymaster.log"

---

## Features

- **Transparent Proxy**: OpenClaw doesn't know keys are rotating
- **Auto Rotation**: On rate limit (429) or timeout (408/504)
- **Context Preservation**: Maintains conversation state across key switches
- **Unified Logging**: All logs go to one file: `~/.openclaw/keymaster.log`
- **Management CLI**: Simple `keymaster` command for everything
- **Systemd Integration**: Auto-starts on boot, auto-restarts on crash
- **Works with Any Username**: Fully portable, no hardcoded paths

---

## Architecture

```
OpenClaw → Proxy (localhost:8787) → Rotates Keys → NVIDIA API
                ↓
         ┌─────┴─────┐
         │ Keymaster │
         │  Service  │
         └───────────┘
```

---

## Commands

After installation, use the `keymaster` command:

### Service Control
```bash
keymaster start      # Start the unified service
keymaster stop       # Stop the service
keymaster restart    # Restart the service
keymaster status     # Show detailed status
```

### Monitoring
```bash
keymaster logs       # Follow unified logs (Ctrl+C to exit)
keymaster logcat     # Show recent colorized logs
keymaster health     # Run health check
```

### Key Management
```bash
keymaster keys       # List all API keys and status
keymaster cooldowns  # Show which keys are cooling down
keymaster reset      # Reset all key cooldowns
```

### Configuration
```bash
keymaster direct     # Use NVIDIA directly (disable proxy)
keymaster proxy      # Use Keymaster proxy (default)
keymaster enable     # Auto-start on boot
keymaster disable    # Don't auto-start on boot
```

---

## File Structure

```
~/.openclaw/
├── keymaster.log                  # Unified logs (everything)
├── keymaster_venv/                # Isolated Python environment
└── skills/keymaster/
    ├── install.sh                 # Portable installer
    ├── keymaster                  # Management CLI
    ├── README.md                  # This file
    ├── proxy/                     # Proxy code
    │   ├── server.py             # Main proxy server
    │   ├── key_manager.py        # Key rotation logic
    │   └── ...
    ├── scripts/                   # Helper scripts
    │   ├── run_unified.sh        # Service runner
    │   ├── service-setup.sh      # Pre-start setup
    │   └── ...
    └── systemd/
        └── openclaw-keymaster@.service  # Systemd template
```

---

## Configuration Files

### auth-profiles.json
Location: `~/.openclaw/agents/main/agent/auth-profiles.json`

Contains API keys and rotation settings:

```json
{
  "version": 1,
  "profiles": {
    "nvidia:primary": {
      "type": "api_key",
      "provider": "nvidia-key-1",
      "key": "nvapi-your-key-here",
      "priority": 1,
      "role": "coordinator",
      "model": "moonshotai/kimi-k2.5",
      "fallback_to": "nvidia:secondary"
    }
  },
  "keymaster": {
    "enabled": true,
    "cooldown_seconds": 60,
    "max_retries_per_key": 3
  }
}
```

---

## Troubleshooting

### Service Won't Start
```bash
# Check status
keymaster status

# View logs
keymaster logcat

# Check for errors
tail -n 50 ~/.openclaw/keymaster.log
```

### No Keys Found
```bash
# Check auth-profiles.json exists
cat ~/.openclaw/agents/main/agent/auth-profiles.json

# Count keys
keymaster keys
```

### Port Already in Use
```bash
# Kill existing processes
keymaster stop
# Or manually:
sudo lsof -ti:8787 | xargs kill -9
```

### Reset Everything
```bash
keymaster stop
keymaster reset
keymaster start
```

---

## How It Works

1. **Install**: Creates isolated Python venv, installs deps, sets up systemd
2. **Configure**: Reads API keys from auth-profiles.json
3. **Run**: Proxy runs on localhost:8787, intercepts all NVIDIA API calls
4. **Rotate**: On rate limit (429), marks key cooling, switches to next key
5. **Recover**: Waits 60 seconds, then retry cooled keys

---

## Log Format

All logs go to `~/.openclaw/keymaster.log`:

```
[2025-03-08 23:45:12.123] [INIT] Keymaster Service Starting
[2025-03-08 23:45:12.234] [INIT] Found 6 NVIDIA API keys
[2025-03-08 23:45:15.456] [PROXY] Ready with 6 keys
[2025-03-08 23:45:20.567] [KEY] nvidia:primary acquired (active: 1)
[2025-03-08 23:45:20.678] [PROXY] REQ_abc123 → moonshotai/kimi-k2.5
[2025-03-08 23:55:30.789] [KEY] nvidia:primary → cooling 60s (429)
[2025-03-08 23:55:30.890] [KEY] nvidia:secondary acquired (active: 1)
```

---

## Development

### Testing Concurrency
```bash
python3 tests/concurrency_test.py --quick    # 5 requests
python3 tests/concurrency_test.py --full     # 20 requests
python3 tests/concurrency_test.py --stress  # 50 requests
```

### Manual Start (No systemd)
```bash
~/.openclaw/skills/keymaster/scripts/run_unified.sh
```

---

## License

MIT License - See LICENSE file

---

## Support

- **Issues**: https://github.com/dommurphy155/Keymaster/issues
- **Logs**: `~/.openclaw/keymaster.log`
- **Health**: `keymaster health`
