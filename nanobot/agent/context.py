"""Context builder for LLM messages."""

import platform
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillManager

if TYPE_CHECKING:
    from nanobot.config.schema import AgentFeaturesConfig, LegacyMemoryConfig, TurboMemoryConfig


class ContextBuilder:
    """
    Builds the system and user messages for the LLM.

    The context includes:
    - Agent identity and instructions
    - Current time and environment
    - Persistent memory (Legacy or Turbo)
    - Available skills
    - Conversation history
    """

    def __init__(
        self,
        workspace: Path,
        memory_config: "LegacyMemoryConfig | TurboMemoryConfig | None" = None,
        features_config: "AgentFeaturesConfig | None" = None,
    ):
        self.workspace = workspace
        # We handle both legacy and turbo memory store initialization here or in the loop
        self.memory = MemoryStore(workspace, memory_config=memory_config)
        self.skills = SkillManager(workspace)
        self.features = features_config

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str | None = None,
        media: list[dict[str, Any]] | None = None,
        memory_context: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Build the list of messages for the LLM.

        Args:
            history: Conversation history.
            current_message: The latest user message.
            media: Optional list of media attachments.
            memory_context: Optional context from TurboMemory.
            **kwargs: Additional context (channel, chat_id, etc.)

        Returns:
            List of messages ready for the LLM.
        """
        messages = []

        # 1. System message (identity + skills + memory)
        system_content = self._build_system_prompt(memory_context=memory_context, **kwargs)
        messages.append({"role": "system", "content": system_content})

        # 2. History
        messages.extend(history)

        # 3. Current user message
        if current_message:
            user_msg: dict[str, Any] = {"role": "user", "content": current_message}
            if media:
                user_msg["media"] = media
            messages.append(user_msg)

        return messages

    def _build_system_prompt(self, memory_context: str | None = None, **kwargs: Any) -> str:
        """Assemble the full system prompt."""
        sections = [
            self._get_identity(),
            self._load_bootstrap_files(),
            self._get_skills_context(),
            self._get_memory_context(memory_context),
            self._get_feature_instructions(),
        ]

        # Add session info if provided
        channel = kwargs.get("channel")
        chat_id = kwargs.get("chat_id")
        if channel and chat_id:
            sections.append(f"## Current Session\nChannel: {channel}\nChat ID: {chat_id}")

        return "\n\n".join([s for s in sections if s])

    def _get_identity(self) -> str:
        """Get the core identity section."""
        import time as _time
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = _time.strftime("%Z") or "UTC"
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        return f"""# nanobot 🐈

You are nanobot, a helpful AI assistant.

## 🎯 CRITICAL: Tool-First Behavior

When asked to DO something:
1. CALL THE TOOL FIRST
2. Wait for result
3. THEN respond

Pattern: User request → TOOL CALL → Verify result → Respond with proof

## Current Time
{now} ({tz})

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Memory: memory/MEMORY.md | Daily notes: memory/YYYY-MM-DD.md
- Skills: skills/{{skill-name}}/SKILL.md

Always be helpful, accurate, and concise. When using tools, explain what you're doing."""

    def _load_bootstrap_files(self) -> str:
        """Load bootstrap files from workspace."""
        parts = []
        bootstrap_files = ["BOOTSTRAP.md", "INSTRUCTIONS.md", "GOALS.md", "SOUL.md", "USER.md"]

        for filename in bootstrap_files:
            file_path = self.workspace / filename
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding="utf-8")
                    parts.append(f"## {filename}\n{content}")
                except Exception:
                    pass

        return "\n\n".join(parts)

    def _get_skills_context(self) -> str:
        """Get context from available skills."""
        context = self.skills.get_skills_context()
        return f"## Active Skills\n\n{context}" if context else ""

    def _get_memory_context(self, turbo_context: str | None = None) -> str:
        """Get context from memory store (Legacy and/or Turbo)."""
        parts = []
        if turbo_context:
            parts.append(f"### TurboMemory Context\n{turbo_context}")

        legacy_context = self.memory.get_memory_context()
        if legacy_context:
            parts.append(f"### File-based Memory\n{legacy_context}")

        return "## Memory\n\n" + "\n\n".join(parts) if parts else ""

    def _get_feature_instructions(self) -> str:
        """Get instructions for enabled features."""
        if not self.features:
            return ""

        instructions = []
        if self.features.multi_agent:
            instructions.append(
                "### Multi-Agent Mode\n"
                "You can delegate complex tasks to specialized models using the 'spawn' tool."
            )

        if self.features.journaling:
            instructions.append(
                "### Journaling Requirement\n"
                "Maintain a clear record of your actions in daily memory files."
            )

        return "\n\n".join(instructions)

    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """Add an assistant message to the list."""
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        messages.append(msg)
        return messages

    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        name: str,
        result: str,
    ) -> list[dict[str, Any]]:
        """Add a tool result message to the list."""
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": name,
                "content": str(result),
            }
        )
        return messages
