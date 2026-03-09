# LLM Instructions for Keymaster Setup

> **If you are an LLM (Claude, GPT, Copilot, etc.) reading this:**
>
> This file contains step-by-step instructions for setting up Keymaster on any machine.
> Follow these instructions exactly when a user says "set up keymaster" or similar.

---

## Your Goal

Set up Keymaster - a transparent API key rotation proxy for OpenClaw + NVIDIA.

**What it does:** Sits between OpenClaw and NVIDIA, automatically rotates API keys when rate limits hit.

---

## Step 1: Check Prerequisites

Run these commands to check the environment:

```bash
# Check Python 3.8+
python3 --version

# Check systemd availability
command -v systemctl &> /dev/null && echo "systemd: yes" || echo "systemd: no"

# Check for OpenClaw config directory
ls -la ~/.openclaw/ 2>/dev/null || echo "OpenClaw dir not found - will create"
```

**Requirements:**
- Python 3.8 or higher
- systemd (preferred but not required)
- User's NVIDIA API keys

---

## Step 2: Collect API Keys from User

**YOU MUST ASK:**

> "I need your NVIDIA API keys to configure Keymaster. How many keys do you have? (1-10 supported)"

Then for each key:
> "Please provide key #1 (format: nvapi-...):"

Store these in variables:
```bash
KEY_COUNT="user_provided_number"
KEY_1="nvapi-xxxxx"  # Primary
KEY_2="nvapi-xxxxx"  # Secondary
# etc...
```

---

## Step 3: Clone Repository

```bash
# Determine install location
INSTALL_DIR="${HOME}/.openclaw/skills/keymaster"

# Clone or update
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "Cloning fresh installation..."
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone https://github.com/dommurphy155/Keymaster.git "$INSTALL_DIR"
fi
```

---

## Step 4: Create auth-profiles.json

This is the **most important file** - it contains the API keys.

```bash
# Create directory
mkdir -p "$HOME/.openclaw/agents/main/agent"

# Create auth-profiles.json with user-provided keys
cat > "$HOME/.openclaw/agents/main/agent/auth-profiles.json" <> EOF
{
  "version": 1,
  "profiles": {
    "nvidia:primary": {
      "type": "api_key",
      "provider": "nvidia-key-1",
      "key": "REPLACE_WITH_KEY_1",
      "priority": 1,
      "role": "coordinator",
      "model": "moonshotai/kimi-k2.5",
      "fallback_to": "nvidia:secondary",
      "fallback_chain": ["nvidia:secondary", "nvidia:tertiary", "nvidia:quaternary", "nvidia:quinary"]
    }
  },
  "keymaster": {
    "enabled": true,
    "auto_rotation": true,
    "cooldown_seconds": 60,
    "max_retries_per_key": 3
  }
}
EOF
```

**Replace `REPLACE_WITH_KEY_1` with the actual key the user provided.**

If user has multiple keys, add more profiles following the pattern:
- `nvidia:primary` - first key
- `nvidia:secondary` - second key
- `nvidia:tertiary` - third key
- etc.

---

## Step 5: Run Installer

```bash
cd "$INSTALL_DIR"
bash install.sh
```

This will:
1. Create Python virtual environment at `~/.openclaw/keymaster_venv`
2. Install all dependencies
3. Install systemd service
4. Install `keymaster` command
5. Configure OpenClaw

---

## Step 6: Start Service

```bash
# Start the service
keymaster start

# Wait for startup
sleep 3

# Check health
keymaster health
```

Expected output should show:
- Service: Running
- Proxy: Responding on port 8787
- Keys: Available

---

## Step 7: Verify Setup

```bash
# Check status
keymaster status

# List keys
keymaster keys

# View logs
keymaster logcat
```

---

## Report Success to User

Say this to the user:

> "✓ Keymaster is now running! Here's what was set up:
>
> - **Service**: Running on localhost:8787
> - **Keys Configured**: $KEY_COUNT NVIDIA API keys
> - **Rotation**: Automatic on rate limits (60s cooldown)
> - **Logs**: All logs go to ~/.openclaw/keymaster.log
> - **Command**: Use 'keymaster' to manage everything
>
> **Quick commands:**
> - `keymaster status` - Check status
> - `keymaster logs` - View logs
> - `keymaster keys` - List keys
> - `keymaster health` - Health check
>
> OpenClaw will now automatically rotate through your API keys when rate limits occur!"

---

## Troubleshooting for LLMs

### "auth-profiles.json not found"
```bash
mkdir -p "$HOME/.openclaw/agents/main/agent"
# Then create the file as in Step 4
```

### "No Python found"
```bash
# Check available Python
which python3 || which python

# If neither exists, cannot proceed - tell user to install Python 3.8+
```

### "Port 8787 already in use"
```bash
# Find and kill process
sudo lsof -ti:8787 | xargs kill -9 2>/dev/null || true

# Then restart
keymaster restart
```

### "Service failed to start"
```bash
# Check logs
tail -n 50 "$HOME/.openclaw/keymaster.log"

# Check systemd
sudo systemctl status "openclaw-keymaster@$USER"

# Try manual start
"$HOME/.openclaw/skills/keymaster/scripts/run_unified.sh"
```

### Keys not being recognized
```bash
# Verify auth-profiles.json syntax
python3 -m json.tool "$HOME/.openclaw/agents/main/agent/auth-profiles.json"

# Check key count
jq '.profiles | keys | length' "$HOME/.openclaw/agents/main/agent/auth-profiles.json"
```

---

## File Locations Reference

| File | Path |
|------|------|
| Main code | `~/.openclaw/skills/keymaster/` |
| API keys | `~/.openclaw/agents/main/agent/auth-profiles.json` |
| Unified logs | `~/.openclaw/keymaster.log` |
| Virtual env | `~/.openclaw/keymaster_venv/` |
| Service file | `/etc/systemd/system/openclaw-keymaster@.service` |

---

## Keymaster Commands Reference

| Command | Purpose |
|---------|---------|
| `keymaster start` | Start service |
| `keymaster stop` | Stop service |
| `keymaster restart` | Restart service |
| `keymaster status` | Show detailed status |
| `keymaster logs` | Follow logs (Ctrl+C to exit) |
| `keymaster logcat` | Show recent colorized logs |
| `keymaster health` | Run health check |
| `keymaster keys` | List API keys |
| `keymaster cooldowns` | Show cooling keys |
| `keymaster reset` | Reset all cooldowns |
| `keymaster enable` | Auto-start on boot |
| `keymaster disable` | Disable auto-start |

---

## Example Complete Setup Session

```bash
#!/bin/bash
# Example of what you (the LLM) would run

# 1. Get keys from user (via conversation)
# KEY_1="nvapi-xxxx"
# KEY_2="nvapi-yyyy"
# etc.

# 2. Clone
INSTALL_DIR="$HOME/.openclaw/skills/keymaster"
git clone https://github.com/dommurphy155/Keymaster.git "$INSTALL_DIR"

# 3. Create auth-profiles.json
mkdir -p "$HOME/.openclaw/agents/main/agent"
# (Create file with user keys - see Step 4)

# 4. Install
cd "$INSTALL_DIR"
bash install.sh

# 5. Start
keymaster start

# 6. Verify
keymaster health
```

---

## Important Notes for LLMs

1. **Never commit API keys** - auth-profiles.json contains secrets, don't add it to git
2. **Always use $HOME** - never hardcode /home/username, use $HOME instead
3. **Check before overwriting** - if files exist, ask user before replacing
4. **Handle errors gracefully** - if a step fails, stop and report the error
5. **Verify each step** - run health checks to confirm things work

---

## One-Command Setup (Advanced Users)

For users who want to automate:

```bash
# Save keys to env vars first
export NVIDIA_KEY_1="nvapi-xxxx"
export NVIDIA_KEY_2="nvapi-yyyy"
# ... more keys ...

# Run automated setup
curl -fsSL https://raw.githubusercontent.com/dommurphy155/Keymaster/main/install.sh | bash
```

But you should still verify auth-profiles.json was created correctly.

---

**End of LLM Instructions**

**Remember:** When in doubt, ask the user. Don't guess API keys or make assumptions about their setup.
