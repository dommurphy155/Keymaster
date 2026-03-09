# OpenClaw Keymaster Systemd Service

This service automatically manages the Keymaster proxy and OpenClaw configuration.

## What It Does

When you start the service, it automatically:

1. **Configures OpenClaw** - Routes all API calls through the proxy (localhost:8787)
2. **Starts the proxy** - Runs the key rotation proxy server
3. **Manages logs** - All output goes to `~/.openclaw/keymaster_service.log`
4. **Auto-restarts** - If the proxy crashes, systemd restarts it automatically
5. **Auto-starts on boot** - Service runs automatically when you log in

## Quick Start

### Install the Service (One-time setup)

```bash
cd ~/.openclaw/skills/keymaster
sudo ./install-service.sh
```

This will:
- Create the systemd service file
- Ask if you want to enable and start the service now
- Configure OpenClaw to use the proxy

### Manage the Service

```bash
# Start/stop/restart
cd ~/.openclaw/skills/keymaster
./scripts/service.sh start      # Start the service
./scripts/service.sh stop       # Stop the service
./scripts/service.sh restart    # Restart the service

# Check status
./scripts/service.sh status     # See if it's running
./scripts/service.sh health     # Test proxy connectivity

# View logs
./scripts/service.sh logs       # Follow the log file

# Enable/disable auto-start
./scripts/service.sh enable     # Start on boot
./scripts/service.sh disable    # Don't start on boot
```

Or use systemctl directly:

```bash
# Start
sudo systemctl start openclaw-proxy@$USER

# Stop
sudo systemctl stop openclaw-proxy@$USER

# Check status
sudo systemctl status openclaw-proxy@$USER

# View logs
sudo journalctl -u openclaw-proxy@$USER -f
```

## How It Works

### Normal Operation

1. OpenClaw makes API request to `http://127.0.0.1:8787`
2. Proxy receives request and picks an available NVIDIA key
3. Proxy forwards request to NVIDIA API with the selected key
4. If key gets rate limited (429), proxy marks it cooling and tries another key
5. Response returned to OpenClaw transparently

### Key Rotation

- **Only rotates on rate limits** - Not just because a key is busy
- **2 concurrent requests per key** - Allows some parallelism
- **60 second cooldown** - After rate limit, key rests before reuse
- **Key affinity** - Parallel tool calls prefer the same key
- **Queuing** - If key busy, requests wait (up to 60s) instead of switching

### Logs

The service logs to: `~/.openclaw/keymaster_service.log`

Example log output:
```
[2024-01-15 09:30:45] Keymaster: Configuring OpenClaw...
[Proxy] Ready with 6 keys
[Proxy] Attempt 1/5 using nvidia:primary
[Proxy] Waiting for semaphore on nvidia:primary
[Proxy] Acquired semaphore for nvidia:primary
[KeyManager] Key nvidia:primary on cooldown for 60s
[Proxy] Attempt 2/5 using nvidia:secondary
...
```

## Troubleshooting

### Service won't start

```bash
# Check for errors
sudo systemctl status openclaw-proxy@$USER

# Check logs
tail -n 50 ~/.openclaw/keymaster_service.log

# Test proxy manually
python3 ~/.openclaw/skills/keymaster/scripts/start_proxy.py --status
```

### OpenClaw not using proxy

```bash
# Verify OpenClaw config
python3 ~/.openclaw/skills/keymaster/scripts/configure_openclaw.py --status

# Re-enable if needed
python3 ~/.openclaw/skills/keymaster/scripts/configure_openclaw.py --enable
```

### All keys cooling

If you see "All keys cooling" in logs:
- Normal after ~60 mins of continuous use
- Service waits for first key to become available (60s cooldown)
- If OpenClaw times out, just retry your request - keys will be ready

### Reset everything

```bash
# Stop service
sudo systemctl stop openclaw-proxy@$USER

# Revert OpenClaw to direct NVIDIA
python3 ~/.openclaw/skills/keymaster/scripts/configure_openclaw.py --disable

# Reset all key cooldowns
curl http://127.0.0.1:8787/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Keys available: {d[\"available_keys\"]}/{d[\"total_keys\"]}')"

# Start service again
sudo systemctl start openclaw-proxy@$USER
```

## Service Configuration

The service file is at: `/etc/systemd/system/openclaw-proxy@.service`

Key settings:
- **Restart=always** - Automatically restarts on crash
- **RestartSec=5** - Wait 5 seconds before restarting
- **TimeoutStopSec=30** - 30 seconds to shut down gracefully

## Uninstall

```bash
# Stop and disable service
sudo systemctl stop openclaw-proxy@$USER
sudo systemctl disable openclaw-proxy@$USER

# Remove service file
sudo rm /etc/systemd/system/openclaw-proxy@.service
sudo systemctl daemon-reload

# Revert OpenClaw
python3 ~/.openclaw/skills/keymaster/scripts/configure_openclaw.py --disable
```

## Advanced: Custom Cooldown

To change the cooldown time, edit your auth-profiles.json:

```bash
# Edit config
nano ~/.openclaw/agents/main/agent/auth-profiles.json
```

Change the `keymaster` section:
```json
{
  "keymaster": {
    "enabled": true,
    "cooldown_seconds": 60,
    "max_retries_per_key": 3
  }
}
```

Then restart the service:
```bash
./scripts/service.sh restart
```
