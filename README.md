# OpenClaw Multi-Agent Toolkit

A powerful duo of OpenClaw skills for building resilient, long-running AI workflows:

- **Keymaster** - Intelligent API key rotation with automatic fallback
- **Agent-Orchestrator** - Multi-agent task decomposition and coordination

## What This Solves

Running long AI tasks? Hit rate limits after 10 minutes? Want to spawn sub-agents? This toolkit handles:

- **Rate limits** - Auto-rotate through multiple API keys
- **Timeouts** - Automatic retry with key switching
- **Context loss** - Preserves conversation across key rotations
- **Complex tasks** - Break down work into coordinated sub-agents
- **Multi-agent workflows** - Each agent gets its own key

## Repository Structure

```
.
├── README.md                 # This file
├── SETUP.md                  # LLM setup instructions (give this to Claude!)
├── keymaster/               # API key rotation skill
│   ├── SKILL.md
│   ├── SETUP.md
│   ├── README.md
│   └── scripts/
│       ├── __init__.py
│       ├── key_pool_manager.py
│       ├── request_wrapper.py
│       ├── context_compactor.py
│       ├── state_manager.py
│       ├── orchestrator_bridge.py
│       ├── agent_bridge.py
│       └── activate.py
└── agent-orchestrator/      # Multi-agent coordination skill
    ├── SKILL.md
    └── references/
```

## Quick Start

### Step 1: Place Skills in OpenClaw

```bash
# Clone or copy to OpenClaw skills directory
git clone https://github.com/YOUR_USERNAME/openclaw-multi-agent-toolkit.git
cp -r openclaw-multi-agent-toolkit/keymaster ~/.openclaw/skills/
cp -r openclaw-multi-agent-toolkit/agent-orchestrator ~/.openclaw/skills/
```

### Step 2: Let Claude Set It Up

**Copy the contents of `SETUP.md` and paste it to Claude with your API keys:**

```
"Here are my NVIDIA API keys: nvapi-XXX, nvapi-YYY, nvapi-ZZZ.
Please set up keymaster using the instructions in SETUP.md"
```

Claude will:
1. Read the SETUP.md instructions
2. Create/update your OpenClaw config files
3. Activate keymaster
4. Verify everything works

### Step 3: Use It

```python
# Instead of direct API calls that fail on rate limits:
# response = openai.ChatCompletion.create(...)

# Use keymaster for automatic fallback:
from keymaster.scripts import keymaster_request

response = keymaster_request(
    messages=[{"role": "user", "content": "Hello"}],
    model="moonshotai/kimi-k2.5"
)

print(response['content'])
```

## Features

### Keymaster

- **6 Key Rotation** - Seamlessly rotates through up to 6 NVIDIA API keys
- **Auto Recovery** - Detects rate limits (429), timeouts (408/504), switches keys
- **Context Preservation** - Keeps conversation state across key switches
- **Context Compaction** - Summarizes older messages when context >80% full
- **Role-Based Assignment** - Different keys for different agent roles
- **Cooldown Tracking** - 60-second cooldown for rate-limited keys

### Agent-Orchestrator

- **Task Decomposition** - Break complex tasks into parallel subtasks
- **Agent Spawning** - Spawn specialized sub-agents with custom skills
- **File-Based Communication** - Inbox/outbox protocol between agents
- **Key Coordination** - Each sub-agent gets optimal key assignment
- **Checkpoint Recovery** - Resume from failures

## Configuration Requirements

You'll need:

- **OpenClaw** installed at `~/.openclaw/`
- **NVIDIA API keys** (1-6 keys supported, more with customization)
- **Python 3.8+**

## How Keymaster Works

```
User Request
    ↓
Keymaster Wrapper
    ↓
Try Key 1 (nvidia:primary)
    ↓ (if 429/timeout)
Mark Key 1 cooldown
    ↓
Compact context if needed
    ↓
Try Key 2 (nvidia:secondary)
    ↓
Success! Continue with Key 2
```

## Key Roles

| Key | Role | Best For |
|-----|------|----------|
| `nvidia:primary` | coordinator | Main agent, task coordination |
| `nvidia:secondary` | strategist | Analysis, planning |
| `nvidia:tertiary` | heavy_lifter | Data processing |
| `nvidia:quaternary` | worker | General purpose |
| `nvidia:quinary` | fixer | Error recovery |
| `nvidia:senary` | backup | Overflow tasks |

## Agent-Orchestrator + Keymaster Integration

When using both together:

```python
from keymaster.scripts.orchestrator_bridge import OrchestratorKeymaster

# Create bridge for a sub-agent
bridge = OrchestratorKeymaster(
    agent_path="/path/to/agent/workspace",
    agent_name="data-collector"
)

# Request with automatic key rotation
response = bridge.request(
    messages=messages,
    task_id="collect-data"
)
# Status automatically written to outbox/keymaster_status.json
```

## Configuration Files

The setup modifies these files:

| File | Purpose |
|------|---------|
| `~/.openclaw/openclaw.json` | API key providers and model settings |
| `~/.openclaw/agents/main/agent/auth-profiles.json` | Key roles, fallback chains, keymaster config |
| `~/.openclaw/keymaster_state.json` | Auto-generated runtime state |

**Important:** Only `auth`, `models.providers`, and `agents.defaults` sections are modified. Your gateway, channels, and other settings are preserved.

## Usage Examples

### Basic Request with Fallback

```python
from keymaster.scripts import keymaster_request

response = keymaster_request(
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Explain quantum computing"}
    ],
    model="moonshotai/kimi-k2.5",
    temperature=0.7,
    max_tokens=4096
)

print(response['content'])
```

### Long-Running Task with Recovery

```python
from keymaster.scripts import keymaster_request_with_recovery

for i, chunk in enumerate(large_dataset):
    response = keymaster_request_with_recovery(
        messages=[
            {"role": "user", "content": f"Analyze: {chunk}"}
        ],
        conversation_id="analysis-task-123",  # Enables checkpoints
        model="moonshotai/kimi-k2.5"
    )
    # If key rotation happens, continues seamlessly
```

### Multi-Agent with Key Coordination

```python
from keymaster.scripts.orchestrator_bridge import MultiAgentCoordinator

coordinator = MultiAgentCoordinator()

# Assign keys based on agent roles
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

## CLI Commands

```bash
# Check key status
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py stats

# Manual key rotation
python3 ~/.openclaw/skills/keymaster/scripts/key_pool_manager.py rotate

# Test request
python3 ~/.openclaw/skills/keymaster/scripts/request_wrapper.py --test --prompt "Hello"

# Verify setup
python3 ~/.openclaw/skills/keymaster/scripts/activate.py
```

## Troubleshooting

**"All keys exhausted"**
```python
from keymaster.scripts import reset_all_keys
reset_all_keys()
```

**Check health**
```python
from keymaster.scripts import is_keymaster_healthy
print(is_keymaster_healthy())
```

**Clear checkpoints**
```python
from keymaster.scripts.state_manager import StateManager
StateManager().clear_all_checkpoints()
```

## How to Give This to Claude

Want Claude to set this up for you? Here's the exact prompt:

---

**"I want to set up the keymaster skill. Here are my details:**

- **API Keys:**
  - Key 1: `nvapi-XXXX`
  - Key 2: `nvapi-YYYY`
  - Key 3: `nvapi-ZZZZ`
  - (etc.)

**Please read the `SETUP.md` file and set up keymaster for me. Follow the instructions exactly.**"

---

## License

MIT - See LICENSE file

## Contributing

Contributions welcome! Both skills use portable paths (`Path.home()`) so they work on any machine regardless of username.

## Credits

- Keymaster: Intelligent API key rotation for OpenClaw
- Agent-Orchestrator: Multi-agent task coordination
- Built for the OpenClaw ecosystem
