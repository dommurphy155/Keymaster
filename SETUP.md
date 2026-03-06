# LLM Setup Guide for Keymaster

**For AI Assistants: Complete instructions to set up Keymaster for any user.**

## When User Says

> "Pull https://github.com/dommurphy155/Keymaster and set everything up. Here are my keys: nvapi-xxx..., nvapi-yyy..., ..."

## Quick Setup (One Command)

```bash
cd ~ && git clone https://github.com/dommurphy155/Keymaster.git && cd Keymaster && sudo ./install-systemd.sh
```

This command:
1. Clones the repository
2. Creates an isolated Python virtual environment
3. Installs all dependencies (fastapi, uvicorn, httpx, requests)
4. Installs the systemd service
5. Configures OpenClaw to use the proxy
6. Starts the service

## Detailed Step-by-Step

If the user wants you to do it manually, follow these steps:

### Step 1: Clone Repository

```bash
cd ~ && git clone https://github.com/dommurphy155/Keymaster.git
```

### Step 2: Collect User's API Keys

Ask the user:
1. **How many NVIDIA API keys do you have?** (1-10 supported)
2. **Provide each key** (format: `nvapi-...`)
3. **Confirm model** (default: `moonshotai/kimi-k2.5`)

### Step 3: Install Systemd Service

```bash
cd ~/Keymaster
sudo ./install-systemd.sh
```

The installer will:
- Create `~/.openclaw/keymaster_venv/` (isolated Python environment)
- Install Python dependencies
- Install systemd service file
- Configure OpenClaw to use proxy
- Start the service

### Step 4: Configure API Keys

The installer will prompt you to enter the API keys. For each key, it will:

1. Add the key to `~/.openclaw/openclaw.json`
2. Add metadata to `~/.openclaw/agents/main/agent/auth-profiles.json`

Example configuration for 3 keys:

**~/.openclaw/openclaw.json** (merge into existing):
```json
{
  "models": {
    "mode": "merge",
    "providers": {
      "nvidia-key-1": {
        "baseUrl": "http://127.0.0.1:8787",
        "apiKey": "USER_KEY_1_HERE",
        "api": "openai-completions",
        "models": [{
          "id": "moonshotai/kimi-k2.5",
          "name": "Kimi K2.5",
          "reasoning": false,
          "input": ["text"],
          "cost": { "input": 0.000002, "output": 0.000008 },
          "contextWindow": 256000,
          "maxTokens": 16384
        }]
      },
      "nvidia-key-2": {
        "baseUrl": "http://127.0.0.1:8787",
        "apiKey": "USER_KEY_2_HERE",
        "api": "openai-completions",
        "models": [{
          "id": "moonshotai/kimi-k2.5",
          "name": "Kimi K2.5",
          "reasoning": false,
          "input": ["text"],
          "cost": { "input": 0.000002, "output": 0.000008 },
          "contextWindow": 256000,
          "maxTokens": 16384
        }]
      },
      "nvidia-key-3": {
        "baseUrl": "http://127.0.0.1:8787",
        "apiKey": "USER_KEY_3_HERE",
        "api": "openai-completions",
        "models": [{
          "id": "moonshotai/kimi-k2.5",
          "name": "Kimi K2.5",
          "reasoning": false,
          "input": ["text"],
          "cost": { "input": 0.000002, "output": 0.000008 },
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
          "nvidia-key-3/moonshotai/kimi-k2.5"
        ]
      }
    }
  }
}
```

**~/.openclaw/agents/main/agent/auth-profiles.json**:
```json
{
  "version": 1,
  "profiles": {
    "nvidia:primary": {
      "type": "api_key",
      "provider": "nvidia-key-1",
      "key": "USER_KEY_1_HERE",
      "priority": 1,
      "role": "coordinator",
      "fallback_chain": ["nvidia:secondary", "nvidia:tertiary"]
    },
    "nvidia:secondary": {
      "type": "api_key",
      "provider": "nvidia-key-2",
      "key": "USER_KEY_2_HERE",
      "priority": 2,
      "role": "strategist",
      "fallback_chain": ["nvidia:tertiary", "nvidia:primary"]
    },
    "nvidia:tertiary": {
      "type": "api_key",
      "provider": "nvidia-key-3",
      "key": "USER_KEY_3_HERE",
      "priority": 3,
      "role": "worker",
      "fallback_chain": ["nvidia:primary", "nvidia:secondary"]
    }
  },
  "keymaster": {
    "enabled": true,
    "auto_rotation": true,
    "cooldown_seconds": 60,
    "max_retries_per_key": 3
  }
}
```

### Step 5: Verify Installation

```bash
# Check service status
keymaster status

# Should show:
# ✓ Service running
# ✓ Proxy responding on port 8787
# ✓ X keys available

# View logs
keymaster logs
```

## Management Commands

After setup, the user can manage Keymaster with:

```bash
# Service control
keymaster start       # Start service
keymaster stop        # Stop service
keymaster restart     # Restart service
keymaster status      # Show detailed status

# Monitoring
keymaster logs        # Follow logs
keymaster logcat      # Show recent colored logs
keymaster health      # Run health checks
keymaster keys        # Show key status
keymaster cooldowns   # Show cooldown status

# Key management
keymaster reset       # Reset all key cooldowns

# Configuration
keymaster direct      # Switch to direct NVIDIA access
keymaster proxy       # Switch back to proxy mode
```

Or using systemctl:

```bash
sudo systemctl status openclaw-keymaster@$USER
sudo systemctl restart openclaw-keymaster@$USER
sudo systemctl stop openclaw-keymaster@$USER
```

## Troubleshooting

### Service won't start

```bash
# Check logs
keymaster logcat

# Check systemd status
sudo systemctl status openclaw-keymaster@$USER

# Check for port conflicts
sudo lsof -i:8787

# Kill any process on port 8787 and restart
sudo lsof -ti:8787 | xargs kill -9
keymaster restart
```

### Keys not rotating

```bash
# Check key status
keymaster keys

# Reset cooldowns
keymaster reset

# Check proxy health
curl http://127.0.0.1:8787/health
```

### OpenClaw not using proxy

```bash
# Switch to proxy mode
keymaster proxy

# Or manually configure
python3 ~/Keymaster/keymaster/scripts/configure_openclaw.py --enable
```

## Files Created

| File | Purpose |
|------|---------|
| `~/.openclaw/keymaster_venv/` | Isolated Python environment |
| `~/.openclaw/keymaster.log` | Unified log file |
| `/etc/systemd/system/openclaw-keymaster@.service` | Systemd service |
| `/usr/local/bin/keymaster` | Management command |
| `~/.openclaw/openclaw.json` | OpenClaw configuration |
| `~/.openclaw/agents/main/agent/auth-profiles.json` | Key metadata |

## Uninstall

```bash
# Stop and disable service
sudo systemctl stop openclaw-keymaster@$USER
sudo systemctl disable openclaw-keymaster@$USER

# Remove files
sudo rm /etc/systemd/system/openclaw-keymaster@.service
sudo rm /usr/local/bin/keymaster
rm -rf ~/.openclaw/keymaster_venv
rm -f ~/.openclaw/keymaster.log

# Revert OpenClaw to direct
keymaster direct

# Reload systemd
sudo systemctl daemon-reload
```

## Support

For issues or questions:
- Check logs: `keymaster logs`
- Health check: `keymaster health`
- Repository: https://github.com/dommurphy155/Keymaster
