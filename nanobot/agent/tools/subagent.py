"""Tools for subagent orchestration and monitoring."""

from typing import TYPE_CHECKING, Any

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from nanobot.agent.subagent import SubagentManager


class SpawnTool(Tool):
    """
    Tool to spawn a subagent for background task execution.

    The subagent runs asynchronously and announces its result back
    to the main agent when complete.
    """

    def __init__(self, manager: "SubagentManager"):
        self._manager = manager
        self._origin_channel = "cli"
        self._origin_chat_id = "direct"

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the origin context for subagent announcements."""
        self._origin_channel = channel
        self._origin_chat_id = chat_id

    @property
    def name(self) -> str:
        return "spawn"

    @property
    def description(self) -> str:
        return (
            "Spawn a subagent to handle a task in the background. "
            "Use this for complex or time-consuming tasks that can run independently. "
            "The subagent will complete the task and report back when done."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task for the subagent to complete",
                },
                "label": {
                    "type": "string",
                    "description": "Optional short label for the task (for display)",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the subagent. Use absolute paths.",
                },
            },
            "required": ["task"],
        }

    async def execute(
        self,
        task: str,
        label: str | None = None,
        working_dir: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Spawn a subagent to execute the given task."""
        return await self._manager.spawn(
            task=task,
            label=label,
            working_dir=working_dir,
            origin_channel=self._origin_channel,
            origin_chat_id=self._origin_chat_id,
        )


class SubagentStatusTool(Tool):
    """Tool to list all subagents and their current status."""

    def __init__(self, manager: "SubagentManager"):
        self._manager = manager

    @property
    def name(self) -> str:
        return "subagent_status"

    @property
    def description(self) -> str:
        return "List all background subagents, their IDs, labels, and current execution status."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "active_only": {
                    "type": "boolean",
                    "description": "If true, only show currently running subagents.",
                    "default": False,
                }
            },
        }

    async def execute(self, active_only: bool = False, **kwargs: Any) -> str:
        states = self._manager.list_active() if active_only else self._manager.list_all()
        if not states:
            return "No subagents found."

        lines = ["Active Subagents:" if active_only else "Subagent Registry:"]
        for s in states:
            duration = ""
            if s.end_time:
                d = s.end_time - s.start_time
                duration = f" (duration: {int(d.total_seconds())}s)"
            lines.append(f"- [{s.task_id}] {s.label}: {s.status}{duration}")
            lines.append(f"  Task: {s.task[:100]}...")

        return "\n".join(lines)


class SubagentMessageTool(Tool):
    """Tool to send guidance or instructions to a running subagent."""

    def __init__(self, manager: "SubagentManager"):
        self._manager = manager

    @property
    def name(self) -> str:
        return "subagent_message"

    @property
    def description(self) -> str:
        return (
            "Send a message or correction to a running subagent. "
            "Use this to guide the subagent if it's going in the wrong direction."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the subagent to message.",
                },
                "message": {
                    "type": "string",
                    "description": "The instruction or correction for the subagent.",
                },
            },
            "required": ["task_id", "message"],
        }

    async def execute(self, task_id: str, message: str, **kwargs: Any) -> str:
        success = await self._manager.send_message(task_id, message)
        if success:
            return f"Message delivered to subagent [{task_id}]. It will process it in its next iteration."
        return f"Failed to deliver message. Subagent [{task_id}] may not be running."


class SubagentHistoryTool(Tool):
    """Tool to inspect the conversation history of a subagent."""

    def __init__(self, manager: "SubagentManager"):
        self._manager = manager

    @property
    def name(self) -> str:
        return "subagent_history"

    @property
    def description(self) -> str:
        return "Retrieve the conversation history of a subagent to see its progress and thought process."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the subagent to inspect.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to retrieve.",
                    "default": 10,
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, task_id: str, limit: int = 10, **kwargs: Any) -> str:
        state = self._manager.get_state(task_id)
        if not state:
            return f"Subagent [{task_id}] not found."

        history = state.messages[-limit:]
        lines = [f"History for subagent [{task_id}] ({state.label}):"]
        for m in history:
            role = m["role"].upper()
            content = m.get("content", "")
            if "tool_calls" in m:
                content += f" [Tool Calls: {len(m['tool_calls'])}]"
            lines.append(f"--- {role} ---")
            lines.append(content[:500] + ("..." if len(content) > 500 else ""))

        return "\n".join(lines)


class SubagentCancelTool(Tool):
    """Tool to cancel a running subagent."""

    def __init__(self, manager: "SubagentManager"):
        self._manager = manager

    @property
    def name(self) -> str:
        return "subagent_cancel"

    @property
    def description(self) -> str:
        return "Cancel a running subagent task immediately."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the subagent to cancel.",
                }
            },
            "required": ["task_id"],
        }

    async def execute(self, task_id: str, **kwargs: Any) -> str:
        success = await self._manager.cancel(task_id)
        if success:
            return f"Subagent [{task_id}] has been cancelled."
        return f"Failed to cancel. Subagent [{task_id}] may not be running."
