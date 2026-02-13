"""Session management for conversation history."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.utils.helpers import ensure_dir, safe_filename


@dataclass
class Session:
    """
    A conversation session.
    Stores messages in JSONL format for easy reading and persistence.
    """

    key: str  # channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str | None = None, **kwargs: Any) -> None:
        """Add a message to the session."""
        msg = {
            "role": role,
            "content": content or "",
            "timestamp": datetime.now().isoformat(),
            **kwargs,
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()

    def get_history(
        self, max_messages: int = 50, preserve_tool_chains: bool = True
    ) -> list[dict[str, Any]]:
        """
        Get message history for LLM context.
        Ensures tool_use -> tool_result pairs are never separated.
        """
        recent = (
            self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        )

        if preserve_tool_chains and recent:
            recent = self._preserve_tool_chains(recent)

        history = []
        for m in recent:
            msg: dict[str, Any] = {"role": m["role"], "content": m["content"]}
            if "tool_calls" in m:
                msg["tool_calls"] = m["tool_calls"]
            if "reasoning_content" in m:
                msg["reasoning_content"] = m["reasoning_content"]
            if m.get("role") == "tool":
                if "tool_call_id" in m:
                    msg["tool_call_id"] = m["tool_call_id"]
                if "name" in m:
                    msg["name"] = m["name"]
            history.append(msg)
        return history

    def _preserve_tool_chains(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Ensure tool_use -> tool_result pairs are never separated."""
        if not messages:
            return messages

        # Check if first message is a tool result without its call
        if messages[0].get("role") == "tool":
            tool_id = messages[0].get("tool_call_id")
            # Find matching call in earlier history
            for msg in reversed(self.messages[: -len(messages)]):
                if msg.get("role") == "assistant" and "tool_calls" in msg:
                    if any(tc.get("id") == tool_id for tc in msg["tool_calls"]):
                        messages.insert(0, msg)
                        break
        return messages

    def clear(self) -> None:
        """Clear all messages in the session."""
        self.messages = []
        self.updated_at = datetime.now()


class SessionManager:
    """Manages conversation sessions."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        from nanobot.utils.helpers import get_data_path

        self.sessions_dir = ensure_dir(get_data_path() / "sessions")
        self._cache: dict[str, Session] = {}

    def _get_session_path(self, key: str) -> Path:
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / f"{safe_key}.jsonl"

    def get_or_create(self, key: str) -> Session:
        if key in self._cache:
            return self._cache[key]
        session = self._load(key) or Session(key=key)
        self._cache[key] = session
        return session

    def _load(self, key: str) -> Session | None:
        path = self._get_session_path(key)
        if not path.exists():
            return None
        try:
            messages, metadata, created_at = [], {}, None
            with open(path) as f:
                for line in f:
                    if not (line := line.strip()):
                        continue
                    data = json.loads(line)
                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        created_at = (
                            datetime.fromisoformat(data["created_at"])
                            if "created_at" in data
                            else None
                        )
                    else:
                        messages.append(data)
            return Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                metadata=metadata,
            )
        except Exception as e:
            logger.warning(f"Failed to load session {key}: {e}")
            return None

    def save(self, session: Session) -> None:
        path = self._get_session_path(session.key)
        with open(path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "_type": "metadata",
                        "created_at": session.created_at.isoformat(),
                        "updated_at": session.updated_at.isoformat(),
                        "metadata": session.metadata,
                    }
                )
                + "\n"
            )
            for msg in session.messages:
                f.write(json.dumps(msg) + "\n")
        self._cache[session.key] = session

    def delete(self, key: str) -> bool:
        self._cache.pop(key, None)
        path = self._get_session_path(key)
        if path.exists():
            path.unlink()
            return True
        return False
