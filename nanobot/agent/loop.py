"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.memory import MemoryStore
from nanobot.agent.subagent import SubagentManager
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.subagent import (
    SpawnTool,
    SubagentCancelTool,
    SubagentHistoryTool,
    SubagentMessageTool,
    SubagentStatusTool,
)
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.agent.tools.zai_web import ZaiWebFetchTool, ZaiWebSearchTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from nanobot.config.schema import Config, ExecToolConfig
    from nanobot.cron.service import CronService


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        memory_window: int | None = None,
        brave_api_key: str | None = None,
        exec_config: ExecToolConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        config: Config | None = None,
    ):
        from nanobot.config.schema import Config, ExecToolConfig

        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.config = config or Config()

        # Main agent configuration (with fallbacks)
        main_cfg = self.config.agents.main
        self.chat_model = (
            main_cfg.model
            or self.config.agents.defaults.chat_model
            or self.config.agents.defaults.model
        )
        self.model = model or self.chat_model

        # Use passed values if provided, otherwise use config.agents.main, otherwise signature defaults
        self.temperature = temperature if temperature is not None else main_cfg.temperature
        self.max_tokens = max_tokens if max_tokens is not None else main_cfg.max_tokens
        self.max_iterations = (
            max_iterations if max_iterations is not None else main_cfg.max_tool_iterations
        )
        self.memory_window = memory_window if memory_window is not None else main_cfg.memory_window

        # Task agent configuration
        task_cfg = self.config.agents.task
        self.task_model = (
            task_cfg.model
            or self.config.agents.defaults.task_model
            or self.config.agents.defaults.model
        )

        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace

        self.context = ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.task_model,
            temperature=task_cfg.temperature,
            max_tokens=task_cfg.max_tokens,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
            max_iterations=task_cfg.max_iterations,
            max_completed_tasks=task_cfg.max_completed_tasks,
        )

        self._running = False
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        # File tools (restrict to workspace if configured)
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        self.tools.register(ReadFileTool(allowed_dir=allowed_dir))
        self.tools.register(WriteFileTool(allowed_dir=allowed_dir))
        self.tools.register(EditFileTool(allowed_dir=allowed_dir))
        self.tools.register(ListDirTool(allowed_dir=allowed_dir))

        # Shell tool
        self.tools.register(
            ExecTool(
                working_dir=str(self.workspace),
                timeout=self.exec_config.timeout,
                restrict_to_workspace=self.restrict_to_workspace,
            )
        )

        # Web tools
        search_config = self.config.tools.web.search
        if search_config.provider == "zai":
            self.tools.register(
                ZaiWebSearchTool(
                    api_key=search_config.zai_api_key or self.config.get_api_key("zai"),
                    base_url=search_config.zai_base_url,
                )
            )
        else:
            self.tools.register(WebSearchTool(api_key=self.brave_api_key))

        fetch_config = self.config.tools.web.fetch
        if fetch_config.provider == "zai":
            self.tools.register(
                ZaiWebFetchTool(
                    api_key=fetch_config.zai_api_key or self.config.get_api_key("zai"),
                    base_url=fetch_config.zai_base_url,
                )
            )
        else:
            self.tools.register(WebFetchTool())

        # Message tool
        message_tool = MessageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(message_tool)

        # Subagent orchestration tools
        spawn_tool = SpawnTool(manager=self.subagents)
        self.tools.register(spawn_tool)
        self.tools.register(SubagentStatusTool(manager=self.subagents))
        self.tools.register(SubagentMessageTool(manager=self.subagents))
        self.tools.register(SubagentHistoryTool(manager=self.subagents))
        self.tools.register(SubagentCancelTool(manager=self.subagents))

        # Cron tool (for scheduling)
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

    def _set_tool_context(self, channel: str, chat_id: str) -> None:
        """Update context for all tools that need routing info."""
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.set_context(channel, chat_id)

        if spawn_tool := self.tools.get("spawn"):
            if isinstance(spawn_tool, SpawnTool):
                spawn_tool.set_context(channel, chat_id)

        if cron_tool := self.tools.get("cron"):
            if isinstance(cron_tool, CronTool):
                cron_tool.set_context(channel, chat_id)

    async def _run_agent_loop(self, initial_messages: list[dict]) -> tuple[str | None, list[str]]:
        """
        Run the agent iteration loop.

        Args:
            initial_messages: Starting messages for the LLM conversation.

        Returns:
            Tuple of (final_content, list_of_tools_used).
        """
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []

        while iteration < self.max_iterations:
            iteration += 1

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            if response.has_tool_calls:
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages,
                    response.content,
                    tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
                messages.append(
                    {"role": "user", "content": "Reflect on the results and decide next steps."}
                )
            else:
                final_content = response.content
                break

        return final_content, tools_used

    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
                try:
                    response = await self._process_message(msg)
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await self.bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=f"Sorry, I encountered an error: {str(e)}",
                        )
                    )
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(
        self, msg: InboundMessage, session_key: str | None = None
    ) -> OutboundMessage | None:
        """
        Process a single inbound message.

        Args:
            msg: The inbound message to process.
            session_key: Override session key (used by process_direct).

        Returns:
            The response message, or None if no response needed.
        """
        # System messages route back via chat_id ("channel:chat_id")
        if msg.channel == "system":
            return await self._process_system_message(msg)

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content

        # Bind context to logger for structured output
        with logger.contextualize(
            channel=msg.channel,
            user_id=msg.sender_id,
            chat_id=msg.chat_id,
            session_key=session_key or msg.session_key,
        ):
            logger.info(f"Processing message: {preview}")

            key = session_key or msg.session_key
            session = self.sessions.get_or_create(key)

            # Handle slash commands
            cmd = msg.content.strip().lower()
            if cmd == "/new":
                # Capture messages before clearing (avoid race condition with background task)
                messages_to_archive = session.messages.copy()
                session.clear()
                self.sessions.save(session)
                self.sessions.invalidate(session.key)

                async def _consolidate_and_cleanup():
                    temp_session = Session(key=session.key)
                    temp_session.messages = messages_to_archive
                    await self._consolidate_memory(temp_session, archive_all=True)

                asyncio.create_task(_consolidate_and_cleanup())
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="New session started. Memory consolidation in progress.",
                )
            if cmd == "/help":
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="🐈 nanobot commands:\n/new — Start a new conversation\n/help — Show available commands",
                )

            if len(session.messages) > self.memory_window:
                asyncio.create_task(self._consolidate_memory(session))

            # Add user message to history early
            session.add_message("user", msg.content)

            self._set_tool_context(msg.channel, msg.chat_id)

            # Build subagent awareness summary
            subagent_summary = self._build_subagent_summary()

            initial_messages = self.context.build_messages(
                history=session.get_history(max_messages=self.memory_window),
                current_message=msg.content,
                media=msg.media if msg.media else None,
                channel=msg.channel,
                chat_id=msg.chat_id,
                subagent_summary=subagent_summary,
            )
            final_content, tools_used = await self._run_agent_loop(initial_messages)

            if final_content is None:
                final_content = "I've completed processing but have no response to give."

            preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
            logger.info(f"Response: {preview}")

            session.add_message(
                "assistant", final_content, tools_used=tools_used if tools_used else None
            )
            self.sessions.save(session)

            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=final_content,
                metadata=msg.metadata or {},  # Pass through for channel-specific needs
            )

    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a system message (e.g., subagent announce).

        The chat_id field contains "original_channel:original_chat_id" to route
        the response back to the correct destination.
        """
        logger.info(f"Processing system message from {msg.sender_id}")

        # Parse origin from chat_id (format: "channel:chat_id")
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            # Fallback
            origin_channel = "cli"
            origin_chat_id = msg.chat_id

        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)
        self._set_tool_context(origin_channel, origin_chat_id)
        initial_messages = self.context.build_messages(
            history=session.get_history(max_messages=self.memory_window),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
        )
        final_content, _ = await self._run_agent_loop(initial_messages)

        if final_content is None:
            final_content = "Background task completed."

        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.sessions.save(session)

        return OutboundMessage(
            channel=origin_channel, chat_id=origin_chat_id, content=final_content
        )

    async def _consolidate_memory(self, session, archive_all: bool = False) -> None:
        """Consolidate old messages into MEMORY.md + HISTORY.md.

        Args:
            archive_all: If True, clear all messages and reset session (for /new command).
                       If False, only write to files without modifying session.
        """
        memory = MemoryStore(self.workspace)

        if archive_all:
            old_messages = session.messages
            keep_count = 0
            logger.info(
                f"Memory consolidation (archive_all): {len(session.messages)} total messages archived"
            )
        else:
            keep_count = self.memory_window // 2
            if len(session.messages) <= keep_count:
                logger.debug(
                    f"Session {session.key}: No consolidation needed (messages={len(session.messages)}, keep={keep_count})"
                )
                return

            messages_to_process = len(session.messages) - session.last_consolidated
            if messages_to_process <= 0:
                logger.debug(
                    f"Session {session.key}: No new messages to consolidate (last_consolidated={session.last_consolidated}, total={len(session.messages)})"
                )
                return

            old_messages = session.messages[session.last_consolidated : -keep_count]
            if not old_messages:
                return
            logger.info(
                f"Memory consolidation started: {len(session.messages)} total, {len(old_messages)} new to consolidate, {keep_count} keep"
            )

        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(
                f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {m['content']}"
            )
        conversation = "\n".join(lines)
        current_memory = memory.read_long_term()

        prompt = f"""You are a memory consolidation agent. Process this conversation and return a JSON object with exactly two keys:

1. "history_entry": A paragraph (2-5 sentences) summarizing the key events/decisions/topics. Start with a timestamp like [YYYY-MM-DD HH:MM]. Include enough detail to be useful when found by grep search later.

2. "memory_update": The updated long-term memory content. Add any new facts: user location, preferences, personal info, habits, project context, technical decisions, tools/services used. If nothing new, return the existing content unchanged.

## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{conversation}

Respond with ONLY valid JSON, no markdown fences."""

        try:
            response = await self.provider.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a memory consolidation agent. Respond only with valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
            )
            text = (response.content or "").strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json.loads(text)

            if entry := result.get("history_entry"):
                memory.append_history(entry)
            if update := result.get("memory_update"):
                if update != current_memory:
                    memory.write_long_term(update)

            if archive_all:
                session.last_consolidated = 0
            else:
                session.last_consolidated = len(session.messages) - keep_count
            logger.info(
                f"Memory consolidation done: {len(session.messages)} messages, last_consolidated={session.last_consolidated}"
            )
        except Exception as e:
            logger.error(f"Memory consolidation failed: {e}")

    def _build_subagent_summary(self) -> str | None:
        """Build a concise summary of active background subagents."""
        active = self.subagents.list_active()
        if not active:
            return None

        lines = [f"You have {len(active)} active background subagent(s):"]
        for s in active:
            from datetime import datetime

            elapsed = (datetime.now() - s.start_time).total_seconds()
            lines.append(f"- [{s.task_id}] {s.label} (running for {int(elapsed)}s)")
            lines.append(f"  Task: {s.task[:80]}...")

        lines.append(
            "\nYou can monitor them with subagent_status, send guidance with subagent_message, or inspect their progress with subagent_history."
        )
        return "\n".join(lines)

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
    ) -> str:
        """
        Process a message directly (for CLI or cron usage).

        Args:
            content: The message content.
            session_key: Session identifier (overrides channel:chat_id for session lookup).
            channel: Source channel (for tool context routing).
            chat_id: Source chat ID (for tool context routing).

        Returns:
            The agent's response.
        """
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)

        response = await self._process_message(msg, session_key=session_key)
        return response.content if response else ""
