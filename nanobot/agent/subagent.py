"""Subagent manager for background task execution with interactive orchestration."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.agent.tools.zai_web import ZaiWebFetchTool, ZaiWebSearchTool
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider

if TYPE_CHECKING:
    from nanobot.config.schema import ExecToolConfig


@dataclass
class SubagentState:
    """State of an active or recently completed subagent."""

    task_id: str
    task: str
    label: str
    origin: dict[str, str]
    start_time: datetime = field(default_factory=datetime.now)
    status: str = "running"  # running, completed, failed, cancelled
    end_time: datetime | None = None
    last_result: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    mailbox: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    task_handle: asyncio.Task | None = None


class SubagentManager:
    """
    Manages background subagent execution with interactive orchestration.

    Supports:
    - Spawning subagents for long-running tasks.
    - Message injection (mailbox) for supervisor guidance.
    - Observability via state tracking and contextualized logging.
    - Iterative task execution with tiered models.
    """

    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        bus: MessageBus,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        brave_api_key: str | None = None,
        exec_config: ExecToolConfig | None = None,
        restrict_to_workspace: bool = False,
        max_iterations: int = 30,
        max_completed_tasks: int = 100,
        llm_timeout: float | None = None,
        config: Any | None = None,
    ):
        from nanobot.config.schema import ExecToolConfig

        self.provider = provider
        self.workspace = workspace
        self.bus = bus
        self.model = model or provider.get_default_model()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.restrict_to_workspace = restrict_to_workspace
        self.max_iterations = max_iterations
        self.max_completed_tasks = max_completed_tasks
        # LLM timeout with fallback to config or default 120s
        self.llm_timeout: float = (
            llm_timeout
            if llm_timeout is not None
            else (
                float(config.agents.task.llm_timeout)
                if config and config.agents.task.llm_timeout is not None
                else (
                    float(config.agents.defaults.llm_timeout)
                    if config
                    else 120.0
                )
            )
        )
        self.config = config
        self._registry: dict[str, SubagentState] = {}

    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
    ) -> str:
        """Spawn a subagent to execute a task in the background."""
        task_id = str(uuid.uuid4())[:8]
        display_label = label or (task[:30] + "..." if len(task) > 30 else task)

        origin = {
            "channel": origin_channel,
            "chat_id": origin_chat_id,
        }

        state = SubagentState(
            task_id=task_id,
            task=task,
            label=display_label,
            origin=origin,
        )
        self._registry[task_id] = state

        # Create background task
        bg_task = asyncio.create_task(self._run_subagent(state))
        state.task_handle = bg_task

        logger.info(f"Spawned subagent [{task_id}]: {display_label}")
        return f"Subagent [{display_label}] started (id: {task_id}). You can monitor it or send guidance."

    def get_state(self, task_id: str) -> SubagentState | None:
        """Get the state of a subagent by ID."""
        return self._registry.get(task_id)

    def list_active(self) -> list[SubagentState]:
        """List all currently running subagents."""
        return [s for s in self._registry.values() if s.status == "running"]

    def list_all(self) -> list[SubagentState]:
        """List all subagents in the registry."""
        return list(self._registry.values())

    async def send_message(self, task_id: str, message: str) -> bool:
        """Inject a message into a subagent's mailbox."""
        if state := self._registry.get(task_id):
            if state.status == "running":
                await state.mailbox.put(message)
                return True
        return False

    async def cancel(self, task_id: str) -> bool:
        """Cancel a running subagent."""
        if state := self._registry.get(task_id):
            if state.status == "running" and state.task_handle:
                state.task_handle.cancel()
                state.status = "cancelled"
                state.end_time = datetime.now()
                return True
        return False

    async def _run_subagent(self, state: SubagentState) -> None:
        """Execute the subagent task loop with mailbox checking and observability."""
        task_id = state.task_id
        session_key = f"subagent:{task_id}"

        with logger.contextualize(
            task_id=task_id,
            session_key=session_key,
            channel="system",
            chat_id=f"{state.origin['channel']}:{state.origin['chat_id']}",
        ):
            logger.info(f"Subagent [{task_id}] starting loop: {state.label}")

            try:
                # Build subagent tools
                tools = ToolRegistry()
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
                # Web tools
                if self.config:
                    search_config = self.config.tools.web.search
                    if search_config.provider == "zai":
                        tools.register(
                            ZaiWebSearchTool(
                                api_key=self.config.resolve_value(
                                    search_config.zai_api_key or search_config.api_key
                                ),
                                base_url=search_config.zai_base_url,
                            )
                        )
                    else:
                        tools.register(WebSearchTool(api_key=self.brave_api_key))

                    fetch_config = self.config.tools.web.fetch
                    if fetch_config.provider == "zai":
                        tools.register(
                            ZaiWebFetchTool(
                                api_key=self.config.resolve_value(
                                    fetch_config.zai_api_key or search_config.zai_api_key
                                ),
                                base_url=fetch_config.zai_base_url,
                            )
                        )
                    else:
                        tools.register(WebFetchTool())
                else:
                    tools.register(WebSearchTool(api_key=self.brave_api_key))
                    tools.register(WebFetchTool())

                # Initial messages
                system_prompt = self._build_subagent_prompt(state)
                state.messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": state.task},
                ]

                iteration = 0
                while iteration < self.max_iterations:
                    iteration += 1

                    try:
                        # 1. Check mailbox for supervisor guidance
                        while not state.mailbox.empty():
                            guidance = await state.mailbox.get()
                            logger.info(
                                f"Subagent [{task_id}] received guidance: {guidance[:50]}..."
                            )
                            state.messages.append(
                                {
                                    "role": "user",
                                    "content": f"<SupervisorCorrection>\n{guidance}\n</SupervisorCorrection>",
                                }
                            )

                        # 2. Call LLM
                        logger.debug(f"Subagent [{task_id}] calling LLM ({self.model})...")
                        response = await self.provider.chat(
                            messages=state.messages,
                            tools=tools.get_definitions(),
                            model=self.model,
                            temperature=self.temperature,
                            max_tokens=self.max_tokens,
                            timeout=self.llm_timeout,
                        )
                        logger.debug(f"Subagent [{task_id}] LLM response received")

                        # Add assistant message to history
                        assistant_msg: dict[str, Any] = {
                            "role": "assistant",
                            "content": response.content or "",
                        }
                        if response.has_tool_calls:
                            assistant_msg["tool_calls"] = [
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
                        if response.reasoning_content:
                            assistant_msg["reasoning_content"] = response.reasoning_content

                        state.messages.append(assistant_msg)

                        if response.has_tool_calls:
                            # Execute tools
                            for tc in response.tool_calls:
                                logger.debug(f"Subagent [{task_id}] tool: {tc.name}")
                                result = await tools.execute(tc.name, tc.arguments)
                                state.messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tc.id,
                                        "name": tc.name,
                                        "content": result,
                                    }
                                )
                            # Add a prompt to trigger the next step in multi-step tasks
                            state.messages.append(
                                {
                                    "role": "user",
                                    "content": "Continue with the next step based on the tool results.",
                                }
                            )
                        else:
                            state.last_result = response.content
                            break
                    except Exception as e:
                        logger.error(f"Subagent [{task_id}] loop iteration {iteration} error: {e}")
                        state.messages.append(
                            {
                                "role": "user",
                                "content": f"INTERNAL ERROR during subagent execution: {str(e)}\nPlease try to recover or summarize the failure.",
                            }
                        )
                        if iteration >= self.max_iterations:
                            state.last_result = f"Subagent failed after multiple internal errors. Last error: {str(e)}"
                            break

                if state.last_result is None:
                    state.last_result = "Task reached maximum iterations without final response."

                state.status = "completed"
                logger.info(f"Subagent [{task_id}] completed successfully")
                await self._announce_result(state, "ok")

            except asyncio.CancelledError:
                logger.warning(f"Subagent [{task_id}] was cancelled")
                state.status = "cancelled"
                raise
            except Exception as e:
                logger.error(f"Subagent [{task_id}] failed: {e}")
                state.status = "failed"
                state.last_result = f"Error: {str(e)}"
                await self._announce_result(state, "error")
            finally:
                state.end_time = datetime.now()
                # Cleanup old completed tasks to prevent memory leak
                self._cleanup_old_tasks()

    def _cleanup_old_tasks(self) -> None:
        """Remove old completed tasks to prevent memory leak."""
        completed = [
            s for s in self._registry.values() if s.status in ["completed", "failed", "cancelled"]
        ]
        if len(completed) > self.max_completed_tasks:
            # Sort by end_time, remove oldest
            completed.sort(key=lambda s: s.end_time or datetime.min)
            to_remove = completed[: len(completed) - self.max_completed_tasks]
            for state in to_remove:
                self._registry.pop(state.task_id, None)
                logger.debug(f"Cleaned up old task [{state.task_id}] from registry")

    async def _announce_result(self, state: SubagentState, status: str) -> None:
        """Announce the subagent result back to the main agent."""
        status_text = "completed successfully" if status == "ok" else "failed"

        announce_content = f"""[Subagent '{state.label}' {status_text}]
ID: {state.task_id}
Task: {state.task}

Result:
{state.last_result}

Summarize this naturally for the user. Keep it brief."""

        msg = InboundMessage(
            channel="system",
            sender_id="subagent",
            chat_id=f"{state.origin['channel']}:{state.origin['chat_id']}",
            content=announce_content,
        )
        await self.bus.publish_inbound(msg)

    def _build_subagent_prompt(self, state: SubagentState) -> str:
        """Build a focused system prompt for the subagent."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")

        return f"""# Subagent [{state.task_id}]

## Current Time
{now}

You are a subagent spawned by the main agent to complete a specific task.

## Rules
1. Stay focused - complete only the assigned task.
2. Your final response will be reported back to the main supervisor agent.
3. Be concise but thorough.
4. If you receive messages in <SupervisorCorrection> tags, adjust your course immediately.

## Capabilities
- Full file access in workspace: {self.workspace}
- Shell execution (timeout={self.exec_config.timeout}s)
- Web search and fetch

## Constraints
- No direct user messaging.
- No spawning other subagents.
- Limited iterations (max={self.max_iterations}).

When finished, provide a clear summary of your findings."""

    def get_running_count(self) -> int:
        """Return the number of currently running subagents."""
        return len(self.list_active())
