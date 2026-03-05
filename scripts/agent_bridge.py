#!/usr/bin/env python3
"""
Keymaster-Agent Orchestrator Integration Bridge

Connects Keymaster's key rotation system with agent-orchestrator's
file-based communication protocol. Allows sub-agents to automatically
use Keymaster for resilient LLM requests.
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict

# Add skill scripts to path
SKILL_DIR = Path.home() / ".openclaw" / "skills" / "keymaster" / "scripts"
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from request_wrapper import make_request, make_request_with_recovery, AllKeysExhaustedError
from key_pool_manager import KeyPoolManager
from state_manager import StateManager


@dataclass
class AgentKeymasterConfig:
    """Configuration for Keymaster in an agent context."""
    agent_name: str
    task_id: str
    preferred_key: Optional[str] = None
    auto_compact: bool = True
    compact_threshold: float = 0.8
    checkpoint_on_rotation: bool = True


class AgentKeymasterBridge:
    """
    Bridge between Keymaster and agent-orchestrator sub-agents.

    Provides:
    - Automatic key rotation on rate limits
    - Checkpoint-based recovery for long tasks
    - Status reporting via file-based protocol
    - Context compaction before key handoff
    """

    def __init__(self, agent_name: str, task_id: str,
                 workspace_path: Optional[Path] = None):
        """
        Initialize the bridge for an agent.

        Args:
            agent_name: Name of the sub-agent
            task_id: Task ID for this execution
            workspace_path: Path to agent workspace (optional)
        """
        self.agent_name = agent_name
        self.task_id = task_id
        self.conversation_id = f"{agent_name}-{task_id}"
        self.key_manager = KeyPoolManager()
        self.state_manager = StateManager()

        # Set up workspace paths for agent-orchestrator protocol
        if workspace_path:
            self.workspace = Path(workspace_path)
        else:
            self.workspace = Path.home() / ".openclaw" / "workspace" / agent_name

        self.inbox = self.workspace / "inbox"
        self.outbox = self.workspace / "outbox"
        self.status_file = self.workspace / "status.json"

        # Ensure directories exist
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.outbox.mkdir(parents=True, exist_ok=True)

        # Track key usage for this agent
        self.rotation_count = 0
        self.last_key = None

    def get_key_for_role(self, role: str = None) -> str:
        """
        Get the appropriate API key for an agent role.

        Args:
            role: Agent role (coordinator, strategist, heavy_lifter, worker, fixer)

        Returns:
            API key string
        """
        role_to_key = {
            'coordinator': 'nvidia:primary',
            'strategist': 'nvidia:secondary',
            'heavy_lifter': 'nvidia:tertiary',
            'worker': 'nvidia:quaternary',
            'fixer': 'nvidia:quinary'
        }

        if role and role in role_to_key:
            key_name = role_to_key[role]
        else:
            key_name = self.key_manager.get_current_key()

        self.last_key = key_name
        return self.key_manager.get_key_api_key(key_name)

    def update_status(self, state: str, progress: Dict = None, error: Dict = None):
        """
        Update the agent status.json for orchestrator monitoring.

        Args:
            state: pending|running|completed|failed
            progress: Optional progress dict
            error: Optional error dict
        """
        status = {
            'state': state,
            'agent_name': self.agent_name,
            'task_id': self.task_id,
            'current_key': self.key_manager.get_current_key(),
            'key_rotations': self.rotation_count,
            'timestamp': time.time()
        }

        if progress:
            status['progress'] = progress

        if error:
            status['error'] = error

        with open(self.status_file, 'w') as f:
            json.dump(status, f, indent=2)

    def log_rotation_event(self, from_key: str, to_key: str, reason: str):
        """Log a key rotation event to the outbox."""
        self.rotation_count += 1

        event = {
            'type': 'key_rotation',
            'timestamp': time.time(),
            'from_key': from_key,
            'to_key': to_key,
            'reason': reason,
            'rotation_count': self.rotation_count
        }

        # Write to keymaster log in outbox
        log_path = self.outbox / 'keymaster_log.json'

        logs = []
        if log_path.exists():
            try:
                with open(log_path, 'r') as f:
                    logs = json.load(f)
            except:
                pass

        logs.append(event)

        with open(log_path, 'w') as f:
            json.dump(logs, f, indent=2)

    def llm_request(self,
                   messages: List[Dict[str, Any]],
                   model: str = "moonshotai/kimi-k2.5",
                   temperature: float = 0.7,
                   max_tokens: int = 4096,
                   **kwargs) -> Dict[str, Any]:
        """
        Make an LLM request with automatic key rotation and checkpointing.

        This is the main method for agents to use instead of direct API calls.

        Args:
            messages: Conversation messages
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            **kwargs: Additional API arguments

        Returns:
            Response dict with 'content', 'usage', etc.
        """
        # Update status to running
        self.update_status('running', progress={'step': 'llm_request'})

        try:
            response = make_request_with_recovery(
                messages=messages,
                conversation_id=self.conversation_id,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            # Check if key was rotated
            current_key = self.key_manager.get_current_key()
            if self.last_key and current_key != self.last_key:
                self.log_rotation_event(self.last_key, current_key, "automatic")

            self.last_key = current_key

            return response

        except AllKeysExhaustedError as e:
            # Update status to failed
            self.update_status('failed', error={
                'type': 'AllKeysExhaustedError',
                'message': str(e)
            })
            raise

    def checkpoint_and_continue(self,
                               messages: List[Dict[str, Any]],
                               callback: Callable,
                               **kwargs) -> Any:
        """
        Execute a callback with checkpoint-based recovery.

        If the callback fails due to rate limits, the checkpoint is saved
        and can be resumed.

        Args:
            messages: Current conversation messages
            callback: Function to execute (receives messages)
            **kwargs: Additional arguments for callback

        Returns:
            Result from callback
        """
        # Create checkpoint before starting
        checkpoint_id = self.state_manager.create_checkpoint(
            conversation_id=self.conversation_id,
            messages=messages,
            current_key=self.key_manager.get_current_key(),
            metadata={
                'agent_name': self.agent_name,
                'task_id': self.task_id,
                'callback': callback.__name__ if hasattr(callback, '__name__') else 'unknown'
            }
        )

        try:
            result = callback(messages, **kwargs)

            # Success - update status
            self.update_status('completed', progress={'checkpoint_id': checkpoint_id})

            return result

        except AllKeysExhaustedError:
            # All keys exhausted - save state for retry
            self.state_manager.save_conversation_state(
                conversation_id=self.conversation_id,
                messages=messages,
                current_key=self.key_manager.get_current_key(),
                compacted=True
            )

            self.update_status('failed', error={
                'type': 'AllKeysExhaustedError',
                'recoverable': True,
                'checkpoint_id': checkpoint_id
            })

            raise

    def get_resume_info(self) -> Optional[Dict[str, Any]]:
        """Get information for resuming a failed task."""
        state = self.state_manager.load_conversation_state(self.conversation_id)

        if not state:
            return None

        return {
            'conversation_id': self.conversation_id,
            'messages': state.get('messages', []),
            'last_key': state.get('current_key'),
            'compacted': state.get('compacted', False),
            'last_updated': state.get('last_updated')
        }

    def create_key_status_report(self) -> Path:
        """
        Create a key status report in the outbox for orchestrator.

        Returns:
            Path to the report file
        """
        stats = self.key_manager.get_stats()

        report = {
            'agent_name': self.agent_name,
            'task_id': self.task_id,
            'timestamp': time.time(),
            'key_pool_status': stats,
            'rotations_this_session': self.rotation_count
        }

        report_path = self.outbox / 'keymaster_status.json'

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        return report_path


def create_agent_bridge(agent_name: str, task_id: str,
                       workspace_path: Optional[str] = None) -> AgentKeymasterBridge:
    """
    Create a Keymaster bridge for an agent-orchestrator sub-agent.

    Args:
        agent_name: Name of the sub-agent
        task_id: Task ID
        workspace_path: Optional workspace path

    Returns:
        Configured AgentKeymasterBridge instance

    Example:
        bridge = create_agent_bridge("code-agent", "task-123")
        response = bridge.llm_request(messages=[{"role": "user", "content": "Hello"}])
    """
    return AgentKeymasterBridge(
        agent_name=agent_name,
        task_id=task_id,
        workspace_path=Path(workspace_path) if workspace_path else None
    )


def get_key_rotation_summary(agent_name: str, task_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a summary of key rotations for an agent task.

    Args:
        agent_name: Name of the agent
        task_id: Task ID

    Returns:
        Summary dict or None if no log exists
    """
    workspace = Path.home() / ".openclaw" / "workspace" / agent_name
    log_path = workspace / "outbox" / "keymaster_log.json"

    if not log_path.exists():
        return None

    try:
        with open(log_path, 'r') as f:
            logs = json.load(f)

        rotations = [l for l in logs if l.get('type') == 'key_rotation']

        return {
            'agent_name': agent_name,
            'task_id': task_id,
            'total_rotations': len(rotations),
            'rotations': rotations
        }
    except:
        return None


def main():
    """CLI for testing agent bridge."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: agent_bridge.py <command> [args]")
        print("Commands:")
        print("  create <agent> <task>  - Create bridge for agent")
        print("  status <agent>         - Get key status for agent")
        print("  report <agent>         - Create status report")
        sys.exit(1)

    command = sys.argv[1]

    if command == "create":
        if len(sys.argv) < 4:
            print("Usage: create <agent> <task>")
            sys.exit(1)

        agent = sys.argv[2]
        task = sys.argv[3]
        bridge = create_agent_bridge(agent, task)
        print(f"Created bridge for {agent}/{task}")
        print(f"Current key: {bridge.key_manager.get_current_key()}")

    elif command == "status":
        if len(sys.argv) < 3:
            print("Usage: status <agent>")
            sys.exit(1)

        agent = sys.argv[2]
        summary = get_key_rotation_summary(agent, "*")
        if summary:
            print(f"Total rotations: {summary['total_rotations']}")
            for rot in summary['rotations']:
                print(f"  {rot['from_key']} -> {rot['to_key']} ({rot['reason']})")
        else:
            print("No rotation data found")

    elif command == "report":
        if len(sys.argv) < 3:
            print("Usage: report <agent>")
            sys.exit(1)

        agent = sys.argv[2]
        bridge = AgentKeymasterBridge(agent, "report")
        path = bridge.create_key_status_report()
        print(f"Report created at: {path}")

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
