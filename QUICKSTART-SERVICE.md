# Keymaster Unified Service - Quick Start

This is the **unified systemd service** that runs everything together with a single log stream.

## What This Does

The unified service:
- Creates an isolated Python virtual environment
- Installs all dependencies automatically
- Configures OpenClaw to use the proxy
- Runs the proxy with unified logging
- Handles all logs in one place: `~/.openclaw/keymaster.log`

## Quick Install (Any Machine)

### Option 1: One-Line Install

```bash
curl -fsSL https://raw.githubusercontent.com/dommurphy155/Keymaster/main/install.sh | bash
```

### Option 2: Manual Install

```bash
cd ~/.openclaw/skills/keymaster
bash install.sh
```

### Option 3: Development/Local Install

```bash
cd ~/.openclaw/skills/keymaster
# Make sure scripts are executable
chmod +x keymaster scripts/*.sh
# Install the service
sudo ./install.sh
```

## Requirements

Before installing, ensure you have:

1. **Python 3.8+**
2. **systemd** (for service mode)
3. **NVIDIA API keys** in `~/.openclaw/agents/main/agent/auth-profiles.json`
4. **OpenClaw** installed (optional but recommended)

## Commands

After installation, use the `keymaster` command:

```bash
# Service Control
keymaster start        # Start the unified service
keymaster stop         # Stop the service
keymaster restart      # Restart the service
keymaster status       # Show detailed status

# Monitoring
keymaster logs         # Follow unified logs (Ctrl+C to exit)
keymaster logcat       # Show recent colorized logs
keymaster health       # Run health check

# Key Management
keymaster keys         # List all API keys
keymaster cooldowns    # Show current cooldowns
keymaster reset        # Reset all key cooldowns

# Configuration
keymaster direct       # Configure OpenClaw for direct NVIDIA
keymaster proxy        # Configure OpenClaw to use proxy
keymaster enable       # Enable auto-start on boot
keymaster disable      # Disable auto-start on boot
```

## Unified Logs

All logs go to one file:

```bash
# View all logs
tail -f ~/.openclaw/keymaster.log

# View last 100 lines with colors
keymaster logcat

# View with filtering
grep "PROXY" ~/.openclaw/keymaster.log
grep "ERROR" ~/.openclaw/keymaster.log
grep "acquired" ~/.openclaw/keymaster.log
```

## Log Format

```
[2025-03-08 23:45:12.123] [INIT] Keymaster Service Setup
[2025-03-08 23:45:12.234] [INIT] Found 6 NVIDIA API keys
[2025-03-08 23:45:12.345] [INIT] Starting Proxy Server on port 8787
[2025-03-08 23:45:15.456] [PROXY] Ready with 6 keys
[2025-03-08 23:45:20.567] [KEY] nvidia:primary acquired (active: 1)
[2025-03-08 23:45:20.678] [PROXY] REQ_abc123 → moonshotai/kimi-k2.5 (stream=True)
```

## File Structure

```
~/.openclaw/
├── keymaster.log              # Unified logs
├── keymaster_venv/            # Isolated Python environment
└── skills/keymaster/
    ├── keymaster              # Management command
    ├── install.sh             # Installer script
    ├── proxy/                 # Proxy code
    │   ├── server.py
    │   ├── key_manager.py
    │   └── ...
    ├── scripts/               # Helper scripts
    │   ├── run_unified.sh     # Main service runner
    │   ├── service-setup.sh   # Pre-start setup
    │   └── ...
    └── systemd/
        └── openclaw-keymaster@.service
```

## Troubleshooting

### Service Won't Start

```bash
# Check systemd status
sudo systemctl status openclaw-keymaster@$USER

# Check logs
sudo journalctl -u openclaw-keymaster@$USER -f

# Check unified log
tail -n 50 ~/.openclaw/keymaster.log
```

### No NVIDIA Keys Found

```bash
# Check auth-profiles.json exists
cat ~/.openclaw/agents/main/agent/auth-profiles.json

# Count keys
jq '.profiles | keys | map(select(startswith("nvidia:"))) | length' \
  ~/.openclaw/agents/main/agent/auth-profiles.json
```

### Port Already in Use

```bash
# Check what's using port 8787
sudo lsof -i :8787

# Kill existing processes
keymaster stop
# or manually:
pkill -f "uvicorn.*8787"
```

### Virtual Environment Issues

```bash
# Recreate venv
rm -rf ~/.openclaw/keymaster_venv
keymaster restart
```

## Manual Operation (No systemd)

If systemd is not available:

```bash
# Run directly
~/.openclaw/skills/keymaster/scripts/run_unified.sh

# Or using the keymaster command
keymaster start  # Will fall back to manual mode
```

## Uninstall

```bash
# Stop and disable service
keymaster stop
keymaster disable

# Remove service file
sudo rm /etc/systemd/system/openclaw-keymaster@.service
sudo systemctl daemon-reload

# Optional: Remove virtual environment
rm -rf ~/.openclaw/keymaster_venv

# Optional: Remove logs
rm ~/.openclaw/keymaster.log
```

## How It Works

1. **Install** (`install.sh`):
   - Creates isolated Python virtual environment
   - Installs dependencies
   - Configures systemd service
   - Installs `keymaster` command

2. **Service Setup** (`service-setup.sh`):
   - Runs before the main service
   - Ensures venv has all dependencies
   - Configures OpenClaw to use proxy
   - Cleans up stale state

3. **Unified Runner** (`run_unified.sh`):
   - Sets up environment
   - Verifies configuration
   - Starts the proxy with unbuffered output
   - All logs go to stdout → systemd captures → unified log file

4. **Management** (`keymaster`):
   - Simple interface to control everything
   - View status, logs, key status
   - Reset cooldowns, configure OpenClaw

## Architecture

```
┌─────────────────────────────────────────┐
│           systemd                       │
│  ┌─────────────────────────────────┐    │
│  │  openclaw-keymaster@user.service │    │
│  │                                 │    │
│  │  ExecStartPre: setup_venv.sh    │    │
│  │  ExecStart: run_unified.sh      │    │
│  │                                 │    │
│  │  Logs → ~/.openclaw/keymaster.log│   │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│     OpenClaw → localhost:8787           │
│         │                               │
│         ▼                               │
│  ┌─────────────┐   ┌─────────────┐      │
│  │  Key 1      │   │  Key 2      │      │
│  │ (active: 1) │   │ (active: 1) │      │
│  └─────────────┘   └─────────────┘      │
│         │               │               │
│         ▼               ▼               │
│     ┌───────────────────────┐           │
│     │   NVIDIA API          │           │
│     └───────────────────────┘           │
└─────────────────────────────────────────┘
```

All logs from all components go to **one unified log file** for easy debugging!
