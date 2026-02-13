"""Subagent management for background tasks."""

import asyncio
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.security.sanitizer import SecretSanitizer

if TYPE_CHECKING:
    from nanobot.config.schema import ExecToolConfig


class SubagentManager:
    """
    Manages background tasks using subagents.

    A subagent is an independent instance of an agent loop focused on a single task.
    It runs in the background and reports results back to the main agent.
    """

    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        bus: MessageBus,
        model: str | None = None,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        restrict_to_workspace: bool = False,
        max_iterations: int = 25,
        evolutionary: bool = False,
        allowed_paths: list[str] | None = None,
        protected_paths: list[str] | None = None,
    ):
        from nanobot.config.schema import ExecToolConfig

        self.provider = provider
        self.workspace = workspace
        self.bus = bus
        self.model = model or provider.get_default_model()
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.restrict_to_workspace = restrict_to_workspace
        self.max_iterations = max_iterations
        self.evolutionary = evolutionary
        self.allowed_paths = allowed_paths or []
        self.protected_paths = protected_paths or []
        self._running_tasks: dict[str, asyncio.Task] = {}

        # Initialize secret sanitizer for security
        self.sanitizer = SecretSanitizer()

    async def spawn(self, task: str, origin: dict[str, str]) -> str:
        """
        Spawn a new subagent to handle a task.

        Args:
            task: The description of the task.
            origin: Dict with 'channel' and 'chat_id' where results should go.

        Returns:
            A message confirming the subagent has started.
        """
        task_id = str(uuid.uuid4())[:8]
        logger.info(f"Spawning subagent [{task_id}] for task: {task[:50]}...")

        # Create background task
        future = asyncio.create_task(self._run_subagent(task_id, task, origin))
        self._running_tasks[task_id] = future

        return f"Subagent [{task_id}] started in background to handle: {task}"

    async def _run_subagent(self, task_id: str, task: str, origin: dict[str, str]) -> None:
        """Internal loop for the subagent."""
        try:
            # Subagents have their own tools (subset of main agent tools)
            tools = ToolRegistry()

            # Determine tool restrictions based on evolutionary mode
            if self.evolutionary and self.allowed_paths:
                allowed_dirs = [Path(p).expanduser().resolve() for p in self.allowed_paths]
                protected_dirs = [Path(p).expanduser().resolve() for p in self.protected_paths]
                tools.register(
                    ReadFileTool(allowed_paths=allowed_dirs, protected_paths=protected_dirs)
                )
                tools.register(
                    WriteFileTool(allowed_paths=allowed_dirs, protected_paths=protected_dirs)
                )
                tools.register(
                    EditFileTool(allowed_paths=allowed_dirs, protected_paths=protected_dirs)
                )
                tools.register(
                    ListDirTool(allowed_paths=allowed_dirs, protected_paths=protected_dirs)
                )
                tools.register(
                    ExecTool(
                        working_dir=str(self.workspace),
                        timeout=self.exec_config.timeout,
                        allowed_paths=self.allowed_paths,
                        protected_paths=self.protected_paths,
                    )
                )
            else:
                allowed_dir = self.workspace if self.restrict_to_workspace else None
                tools.register(ReadFileTool(allowed_dir=allowed_dir))
                tools.register(WriteFileTool(allowed_dir=allowed_dir))
                tools.register(EditFileTool(allowed_dir=allowed_dir))
                tools.register(ListDirTool(allowed_dir=allowed_dir))
                tools.register(
                    ExecTool(
                        working_dir=str(self.workspace),
                        timeout=self.exec_config.timeout,
                        restrict_to_workspace=self.restrict_to_workspace,
                    )
                )

            tools.register(WebSearchTool(api_key=self.brave_api_key))
            tools.register(WebFetchTool())

            # Build messages with subagent-specific prompt
            system_prompt = self._build_subagent_prompt(task)
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Please complete this task: {task}"},
            ]

            iteration = 0
            final_content = None

            while iteration < self.max_iterations:
                iteration += 1

                # Call LLM
                response = await self.provider.chat(
                    messages=messages,
                    tools=tools.get_definitions(),
                    model=self.model,
                )

                if response.has_tool_calls:
                    # Add assistant message with tool calls
                    tool_call_dicts = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in response.tool_calls
                    ]
                    messages.append(
                        {
                            "role": "assistant",
                            "content": response.content,
                            "tool_calls": tool_call_dicts,
                        }
                    )

                    # Execute tools
                    for tc in response.tool_calls:
                        args_str = json.dumps(tc.arguments, ensure_ascii=False)
                        sanitized_args = self.sanitizer.sanitize(args_str)
                        logger.debug(
                            f"Subagent [{task_id}] executing: {tc.name}({sanitized_args[:100]})"
                        )
                        result = await tools.execute(tc.name, tc.arguments)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "name": tc.name,
                                "content": str(result),
                            }
                        )
                else:
                    final_content = response.content
                    break

            if final_content is None:
                final_content = "Subagent task timed out or failed to produce a final response."

            # Report back to main loop via system channel
            await self._announce_result(task_id, task, final_content, origin)

        except Exception as e:
            logger.error(f"Error in subagent [{task_id}]: {e}")
            await self._announce_result(task_id, task, f"Subagent error: {str(e)}", origin)
        finally:
            self._running_tasks.pop(task_id, None)

    async def _announce_result(
        self, task_id: str, task: str, result: str, origin: dict[str, str]
    ) -> None:
        """Send subagent result back to the main agent loop."""
        announce_content = f"""### Subagent [{task_id}] Task Completed
**Task**: {task}

**Result**:
{result}

Summarize this naturally for the user."""

        # Send as an inbound system message
        msg = InboundMessage(
            channel="system",
            sender_id=f"subagent:{task_id}",
            chat_id=f"{origin['channel']}:{origin['chat_id']}",
            content=announce_content,
        )

        await self.bus.publish_inbound(msg)
        logger.debug(
            f"Subagent [{task_id}] announced result to {origin['channel']}:{origin['chat_id']}"
        )

    def _build_subagent_prompt(self, task: str) -> str:
        """Build a focused system prompt for the subagent."""
        import time as _time
        from datetime import datetime

        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = _time.strftime("%Z") or "UTC"

        return f"""# Subagent

## Current Time
{now} ({tz})

You are a subagent spawned by the main agent to complete a specific task.

## How to Save Your Results
- For extensive research, analysis or data, SAVE YOUR FINDINGS TO A FILE using the write_file tool.
- For brief answers or quick tasks, you may return the result directly as text.
- Your text response will be summarized for the user, but large amounts of data should always be stored in a file.
- If the task specifies a file path, use it exactly.

## Rules
1. Stay focused - complete only the assigned task, nothing else
2. Your final response will be reported back to the main agent
3. You have full access to workspace files and terminal
4. If you hit an error, explain what happened
5. Do NOT try to communicate with the user directly, only via your final response

## Workspace
Your workspace is at: {self.workspace}
Skills are available at: {self.workspace}/skills/ (read SKILL.md files as needed)

When you have completed the task, provide a clear summary of your findings or actions."""

    def get_running_count(self) -> int:
        """Return the number of currently running subagents."""
        return len(self._running_tasks)
