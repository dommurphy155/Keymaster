#!/usr/bin/env python3
"""
Orchestrator Bridge - Integrates Keymaster with Agent Orchestrator.

This module provides seamless key rotation for sub-agents spawned by the
agent-orchestrator skill. It uses the file-based communication protocol
to report key status and handle failures.

Usage:
    from orchestrator_bridge import OrchestratorKeymaster
    bridge = OrchestratorKeymaster(agent_path="/path/to/agent")
    response = bridge.request(messages, task_id="task-123")
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# Import keymaster components
sys.path.insert(0, str(Path(__file__).parent))
from request_wrapper import RequestWrapper, AllKeysExhaustedError
from key_pool_manager import KeyPoolManager
from state_manager import StateManager


@dataclass
class AgentKeyStatus:
    """Status of a sub-agent's key usage."""
    agent_name: str
    current_key: str
    keys_used: List[str]
    rotations: int
    last_error: Optional[str]
    status: str  # 'active', 'failed', 'completed'


class OrchestratorKeymaster:
    """
    Keymaster integration for agent-orchestrator sub-agents.

    Handles key rotation for long-running agent tasks and reports
    status via the file-based communication protocol.
    """

    def __init__(self, agent_path: Optional[str] = None, agent_name: Optional[str] = None):
        """
        Initialize the orchestrator bridge.

        Args:
            agent_path: Path to the agent's workspace (for file-based protocol)
            agent_name: Name of the agent
        """
        self.agent_path = Path(agent_path) if agent_path else None
        self.agent_name = agent_name or "unknown"
        self.wrapper = RequestWrapper()
        self.manager = KeyPoolManager()
        self.state_manager = StateManager()
        self.keys_used = []
        self.rotations = 0
        self.last_error = None

    def _write_keymaster_status(self, status: Dict[str, Any]):
        """Write keymaster status to agent's outbox for orchestrator to read."""
        if not self.agent_path:
            return

        status_file = self.agent_path / "outbox" / "keymaster_status.json"
        status_file.parent.mkdir(parents=True, exist_ok=True)

        status.update({
            'timestamp': time.time(),
            'agent_name': self.agent_name,
            'keys_available': self.manager.get_all_available_keys()
        })

        with open(status_file, 'w') as f:
            json.dump(status, f, indent=2)

    def _write_checkpoint(self, task_id: str, messages: List[Dict[str, Any]]):
        """Create a checkpoint for the current task."""
        conversation_id = f"{self.agent_name}-{task_id}"
        checkpoint_id = self.state_manager.create_checkpoint(
            conversation_id=conversation_id,
            messages=messages,
            current_key=self.manager.get_current_key(),
            metadata={
                'agent_name': self.agent_name,
                'task_id': task_id,
                'keys_used': self.keys_used.copy()
            }
        )
        return checkpoint_id

    def request(self,
                messages: List[Dict[str, Any]],
                task_id: str = "default",
                **kwargs) -> Dict[str, Any]:
        """
        Make a request with full agent-orchestrator integration.

        This method:
        1. Creates a checkpoint before the request
        2. Writes status updates to the outbox
        3. Handles key rotation on failures
        4. Reports final status

        Args:
            messages: Conversation messages
            task_id: Unique task identifier
            **kwargs: Additional API arguments

        Returns:
            Response dict

        Raises:
            AllKeysExhaustedError: If all keys fail
        """
        conversation_id = f"{self.agent_name}-{task_id}"

        # Write initial status
        self._write_keymaster_status({
            'status': 'starting',
            'current_key': self.manager.get_current_key(),
            'checkpoint': None
        })

        # Create checkpoint
        checkpoint_id = self._write_checkpoint(task_id, messages)

        try:
            # Make the request with recovery
            response = self.wrapper.make_request_with_recovery(
                messages=messages,
                conversation_id=conversation_id,
                **kwargs
            )

            # Track key usage
            current_key = self.manager.get_current_key()
            if current_key not in self.keys_used:
                self.keys_used.append(current_key)

            # Update stats
            self.rotations = self.manager.state.rotation_count

            # Write success status
            self._write_keymaster_status({
                'status': 'success',
                'current_key': current_key,
                'keys_used': self.keys_used,
                'rotations': self.rotations,
                'checkpoint': checkpoint_id
            })

            return response

        except AllKeysExhaustedError as e:
            # All keys exhausted - report failure
            self.last_error = str(e)
            self._write_keymaster_status({
                'status': 'failed',
                'error': 'all_keys_exhausted',
                'message': str(e),
                'keys_used': self.keys_used,
                'checkpoint': checkpoint_id
            })
            raise

        except Exception as e:
            # Other error - report but don't necessarily fail
            self.last_error = str(e)
            self._write_keymaster_status({
                'status': 'error',
                'error': type(e).__name__,
                'message': str(e),
                'checkpoint': checkpoint_id
            })
            raise

    def resume_from_failure(self, task_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Resume a task after a key failure.

        Loads the last checkpoint and returns the messages so the
        agent can continue from where it left off.

        Args:
            task_id: The task ID to resume

        Returns:
            Messages from the checkpoint or None if not found
        """
        conversation_id = f"{self.agent_name}-{task_id}"
        state = self.state_manager.load_conversation_state(conversation_id)

        if state:
            return state.get('messages')

        return None

    def get_key_for_role(self, role: str) -> Dict[str, Any]:
        """
        Get the appropriate key for an agent's role.

        Args:
            role: Agent role (coordinator, strategist, heavy_lifter, worker, fixer)

        Returns:
            Key configuration dict
        """
        role_to_key = {
            'coordinator': 'nvidia:primary',
            'strategist': 'nvidia:secondary',
            'heavy_lifter': 'nvidia:tertiary',
            'worker': 'nvidia:quaternary',
            'fixer': 'nvidia:quinary'
        }

        key_name = role_to_key.get(role, 'nvidia:primary')

        # Force switch to this key if available
        if key_name in self.manager.get_all_available_keys():
            self.manager.state.current_key = key_name
            self.manager._save_state()

        return {
            'key_name': key_name,
            'provider': self.manager.KEY_NAME_MAP.get(key_name),
            'role': role,
            'api_key': self.manager.get_key_api_key(key_name)
        }

    def report_status(self) -> AgentKeyStatus:
        """Get current status for this agent."""
        return AgentKeyStatus(
            agent_name=self.agent_name,
            current_key=self.manager.get_current_key(),
            keys_used=self.keys_used.copy(),
            rotations=self.rotations,
            last_error=self.last_error,
            status='active' if not self.last_error else 'failed'
        )


class MultiAgentCoordinator:
    """
    Coordinates keys across multiple sub-agents.

    Ensures different agents use different keys when possible
    to maximize throughput and avoid rate limits.
    """

    def __init__(self):
        self.manager = KeyPoolManager()
        self.agent_assignments: Dict[str, str] = {}

    def assign_key_to_agent(self, agent_name: str, agent_role: str) -> str:
        """
        Assign the best available key to an agent.

        Args:
            agent_name: Name of the agent
            agent_role: Role of the agent

        Returns:
            Key name assigned to the agent
        """
        # Role-based priority
        role_priority = {
            'coordinator': ['nvidia:primary'],
            'strategist': ['nvidia:secondary'],
            'heavy_lifter': ['nvidia:tertiary'],
            'worker': ['nvidia:quaternary'],
            'fixer': ['nvidia:quinary']
        }

        preferred = role_priority.get(agent_role, [])
        available = self.manager.get_all_available_keys()

        # Find first preferred key that's available
        for key in preferred:
            if key in available:
                self.agent_assignments[agent_name] = key
                return key

        # Fallback to any available key
        if available:
            key = available[0]
            self.agent_assignments[agent_name] = key
            return key

        # No keys available
        return self.manager.get_current_key()

    def get_agent_key(self, agent_name: str) -> str:
        """Get the key assigned to an agent."""
        return self.agent_assignments.get(agent_name, self.manager.get_current_key())

    def release_agent_key(self, agent_name: str):
        """Release a key when an agent completes."""
        if agent_name in self.agent_assignments:
            del self.agent_assignments[agent_name]

    def get_all_assignments(self) -> Dict[str, str]:
        """Get all key assignments."""
        return self.agent_assignments.copy()


# Convenience functions
def create_orchestrator_bridge(agent_path: str, agent_name: str) -> OrchestratorKeymaster:
    """Create a bridge for a sub-agent."""
    return OrchestratorKeymaster(agent_path=agent_path, agent_name=agent_name)


def get_key_for_agent_role(role: str) -> Dict[str, Any]:
    """Get key configuration for an agent role."""
    manager = KeyPoolManager()
    bridge = OrchestratorKeymaster()
    return bridge.get_key_for_role(role)


def coordinate_multi_agent(agent_roles: List[Dict[str, str]]) -> Dict[str, str]:
    """
    Coordinate keys for multiple agents.

    Args:
        agent_roles: List of dicts with 'name' and 'role' keys

    Returns:
        Dict mapping agent names to key names
    """
    coordinator = MultiAgentCoordinator()
    assignments = {}

    for agent in agent_roles:
        name = agent.get('name')
        role = agent.get('role')
        if name and role:
            key = coordinator.assign_key_to_agent(name, role)
            assignments[name] = key

    return assignments


def main():
    """CLI for testing orchestrator integration."""
    import argparse

    parser = argparse.ArgumentParser(description="Keymaster Orchestrator Bridge")
    parser.add_argument("--test-assign", action="store_true", help="Test key assignment")
    parser.add_argument("--role", type=str, help="Agent role for testing")
    parser.add_argument("--agent-name", type=str, default="test-agent", help="Agent name")

    args = parser.parse_args()

    if args.test_assign:
        print(f"[Bridge] Testing key assignment for role: {args.role}")
        key_config = get_key_for_agent_role(args.role or 'worker')
        print(f"[Bridge] Assigned key: {key_config['key_name']}")
        print(f"[Bridge] Provider: {key_config['provider']}")
        print(f"[Bridge] Role: {key_config['role']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
