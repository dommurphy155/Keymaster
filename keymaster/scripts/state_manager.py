#!/usr/bin/env python3
"""
State Manager - Persists and restores conversation state for key rotation.

Maintains state in ~/.openclaw/keymaster_state.json including:
- Current active key
- Key cooldown status
- Conversation checkpoints
- Compaction history
"""

import json
import os
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict

STATE_PATH = Path.home() / ".openclaw" / "keymaster_state.json"
CHECKPOINT_DIR = Path.home() / ".openclaw" / "keymaster_checkpoints"


@dataclass
class ConversationCheckpoint:
    """A saved point in a conversation."""
    id: str
    timestamp: float
    messages: List[Dict[str, Any]]
    current_key: str
    metadata: Dict[str, Any]


class StateManager:
    """Manages persistent state for Keymaster."""

    def __init__(self):
        self.state_path = STATE_PATH
        self.checkpoint_dir = CHECKPOINT_DIR
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure state directories exist."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> Optional[Dict[str, Any]]:
        """Load state from disk."""
        if not self.state_path.exists():
            return None

        try:
            with open(self.state_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[Keymaster] Error loading state: {e}")
            return None

    def save_state(self, state: Dict[str, Any]):
        """Save state to disk."""
        self._ensure_directories()

        # Add timestamp
        state['_last_saved'] = time.time()

        with open(self.state_path, 'w') as f:
            json.dump(state, f, indent=2)

    def create_checkpoint(self,
                         conversation_id: str,
                         messages: List[Dict[str, Any]],
                         current_key: str,
                         metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Create a conversation checkpoint.

        Args:
            conversation_id: Unique ID for the conversation
            messages: Current conversation messages
            current_key: Current API key being used
            metadata: Additional metadata

        Returns:
            Checkpoint ID
        """
        checkpoint = ConversationCheckpoint(
            id=f"{conversation_id}_{int(time.time())}",
            timestamp=time.time(),
            messages=messages,
            current_key=current_key,
            metadata=metadata or {}
        )

        checkpoint_path = self.checkpoint_dir / f"{checkpoint.id}.json"

        with open(checkpoint_path, 'w') as f:
            json.dump(asdict(checkpoint), f, indent=2)

        # Clean up old checkpoints (keep last 20)
        self._cleanup_old_checkpoints(conversation_id, keep=20)

        return checkpoint.id

    def load_checkpoint(self, checkpoint_id: str) -> Optional[ConversationCheckpoint]:
        """Load a specific checkpoint."""
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.json"

        if not checkpoint_path.exists():
            return None

        try:
            with open(checkpoint_path, 'r') as f:
                data = json.load(f)
                return ConversationCheckpoint(**data)
        except (json.JSONDecodeError, IOError):
            return None

    def load_latest_checkpoint(self, conversation_id: str) -> Optional[ConversationCheckpoint]:
        """Load the most recent checkpoint for a conversation."""
        checkpoints = self.list_checkpoints(conversation_id)

        if not checkpoints:
            return None

        # Sort by timestamp (newest first)
        latest = sorted(checkpoints, key=lambda x: x['timestamp'], reverse=True)[0]
        return self.load_checkpoint(latest['id'])

    def list_checkpoints(self, conversation_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List checkpoints, optionally filtered by conversation ID."""
        checkpoints = []

        if not self.checkpoint_dir.exists():
            return checkpoints

        for file_path in self.checkpoint_dir.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)

                # Filter by conversation ID if specified
                if conversation_id:
                    if data.get('id', '').startswith(f"{conversation_id}_"):
                        checkpoints.append({
                            'id': data['id'],
                            'timestamp': data['timestamp'],
                            'current_key': data['current_key'],
                            'message_count': len(data.get('messages', []))
                        })
                else:
                    checkpoints.append({
                        'id': data['id'],
                        'timestamp': data['timestamp'],
                        'current_key': data['current_key'],
                        'message_count': len(data.get('messages', []))
                    })
            except (json.JSONDecodeError, IOError):
                continue

        return checkpoints

    def _cleanup_old_checkpoints(self, conversation_id: str, keep: int = 20):
        """Remove old checkpoints, keeping only the most recent."""
        checkpoints = self.list_checkpoints(conversation_id)

        if len(checkpoints) <= keep:
            return

        # Sort by timestamp (oldest first)
        to_remove = sorted(checkpoints, key=lambda x: x['timestamp'])[:-keep]

        for checkpoint in to_remove:
            checkpoint_path = self.checkpoint_dir / f"{checkpoint['id']}.json"
            try:
                checkpoint_path.unlink()
            except IOError:
                pass

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a specific checkpoint."""
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.json"

        if checkpoint_path.exists():
            try:
                checkpoint_path.unlink()
                return True
            except IOError:
                pass

        return False

    def clear_all_checkpoints(self, conversation_id: Optional[str] = None):
        """Clear all checkpoints, optionally for a specific conversation."""
        if conversation_id:
            checkpoints = self.list_checkpoints(conversation_id)
            for checkpoint in checkpoints:
                self.delete_checkpoint(checkpoint['id'])
        else:
            # Clear all
            for file_path in self.checkpoint_dir.glob("*.json"):
                try:
                    file_path.unlink()
                except IOError:
                    pass

    def save_conversation_state(self,
                                conversation_id: str,
                                messages: List[Dict[str, Any]],
                                current_key: str,
                                compacted: bool = False):
        """
        Save current conversation state.

        This is a lightweight save vs. full checkpoint.
        """
        state = self.load_state() or {}

        if 'conversations' not in state:
            state['conversations'] = {}

        state['conversations'][conversation_id] = {
            'messages': messages,
            'current_key': current_key,
            'last_updated': time.time(),
            'compacted': compacted
        }

        self.save_state(state)

    def load_conversation_state(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Load conversation state."""
        state = self.load_state()

        if not state or 'conversations' not in state:
            return None

        return state['conversations'].get(conversation_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get state manager statistics."""
        state = self.load_state()
        checkpoints = self.list_checkpoints()

        return {
            'state_file_exists': self.state_path.exists(),
            'state_last_saved': state.get('_last_saved') if state else None,
            'checkpoint_count': len(checkpoints),
            'checkpoint_dir_size': sum(
                f.stat().st_size for f in self.checkpoint_dir.glob("*.json")
            ) if self.checkpoint_dir.exists() else 0,
            'conversations_tracked': len(state.get('conversations', {})) if state else 0
        }


# Convenience functions
def save_state(state: Dict[str, Any]):
    """Save state to disk."""
    manager = StateManager()
    manager.save_state(state)


def load_state() -> Optional[Dict[str, Any]]:
    """Load state from disk."""
    manager = StateManager()
    return manager.load_state()


def create_checkpoint(conversation_id: str,
                     messages: List[Dict[str, Any]],
                     current_key: str,
                     metadata: Optional[Dict[str, Any]] = None) -> str:
    """Create a conversation checkpoint."""
    manager = StateManager()
    return manager.create_checkpoint(conversation_id, messages, current_key, metadata)


def load_checkpoint(checkpoint_id: str) -> Optional[ConversationCheckpoint]:
    """Load a checkpoint."""
    manager = StateManager()
    return manager.load_checkpoint(checkpoint_id)


def main():
    """CLI for state management."""
    import sys

    manager = StateManager()

    if len(sys.argv) < 2:
        print("Usage: state_manager.py <action> [args]")
        print("Actions:")
        print("  stats                    - Show statistics")
        print("  checkpoints [conv_id]    - List checkpoints")
        print("  clear [conv_id]           - Clear checkpoints")
        print("  test                      - Create test checkpoint")
        sys.exit(1)

    action = sys.argv[1]

    if action == "stats":
        import pprint
        pprint.pprint(manager.get_stats())

    elif action == "checkpoints":
        conv_id = sys.argv[2] if len(sys.argv) > 2 else None
        checkpoints = manager.list_checkpoints(conv_id)

        if not checkpoints:
            print("No checkpoints found")
        else:
            for cp in sorted(checkpoints, key=lambda x: x['timestamp'], reverse=True)[:10]:
                print(f"  {cp['id']}: {cp['current_key']} ({len(cp['message_count'])} msgs)")

    elif action == "clear":
        conv_id = sys.argv[2] if len(sys.argv) > 2 else None
        manager.clear_all_checkpoints(conv_id)
        print("Checkpoints cleared")

    elif action == "test":
        checkpoint_id = manager.create_checkpoint(
            conversation_id="test_conv",
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ],
            current_key="nvidia:primary",
            metadata={"test": True}
        )
        print(f"Created checkpoint: {checkpoint_id}")

    else:
        print(f"Unknown action: {action}")


if __name__ == "__main__":
    main()
