"""Agent loop: the core processing engine."""

import asyncio
import inspect
import json
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.context_factory import ContextBuilderFactory
from nanobot.agent.loop_guard import tool_call_hash
from nanobot.agent.stages import RoutingContext, RoutingStage
from nanobot.agent.subagent import SubagentManager
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.todo import TodoTool
from nanobot.agent.tools.update_config import UpdateConfigTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.agent.work_log_manager import LogLevel, get_work_log_manager
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider, LLMResponse
from nanobot.security.sanitizer import SecretSanitizer
from nanobot.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from nanobot.config.schema import (
        Config,
        ContextConfig,
        ExecToolConfig,
        MemoryConfig,
        RoutingConfig,
    )
    from nanobot.cron.service import CronService


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls (possibly in parallel)
    5. Sends responses back
    """

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        memory_window: int = 50,
        subagent_max_iterations: int = 25,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        cron_service: "CronService | None" = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        config: "Config | None" = None,
        routing_config: "RoutingConfig | None" = None,
        evolutionary: bool = False,
        allowed_paths: list[str] | None = None,
        protected_paths: list[str] | None = None,
        memory_config: "MemoryConfig | None" = None,
        context_config: "ContextConfig | None" = None,
    ):
        from nanobot.config.schema import Config, ExecToolConfig

        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.memory_window = memory_window
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        self.config = config or Config()
        self.evolutionary = evolutionary
        self.allowed_paths = allowed_paths or self.config.tools.allowed_paths
        self.protected_paths = protected_paths or self.config.tools.protected_paths

        # Initialize secret sanitizer for security
        self.sanitizer = SecretSanitizer()

        # Initialize work log manager for transparency
        self.work_log_manager = get_work_log_manager()

        # Initialize context builder
        context_config = context_config or self.config.context
        if context_config and (
            context_config.context_plugin_package != "nanobot.agent.context"
            or context_config.context_plugin_class != "ContextBuilder"
        ):
            self.context = ContextBuilderFactory.create(
                workspace=workspace,
                context_provider_package=context_config.context_plugin_package,
                context_provider_class=context_config.context_plugin_class,
                plugin_config=context_config.context_plugin_config,
            )
        else:
            self.context = ContextBuilder(
                workspace,
                memory_config=self.config.legacy_memory,
                features_config=self.config.agents.defaults.features,
            )

        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()

        # Initialize smart router if enabled
        self.routing_config = routing_config or self.config.routing
        self.routing_stage = None
        if self.routing_config and self.routing_config.enabled:
            self.routing_stage = RoutingStage(
                config=self.routing_config,
                provider=provider,
                workspace=workspace,
                cron_service=cron_service,
            )
            logger.info("Smart routing enabled")

        # Initialize turbo memory system if enabled
        self.memory_config = memory_config or self.config.memory
        self.memory_store = None
        self.activity_tracker = None
        self.background_processor = None
        self.memory_retrieval = None
        self.context_assembler = None
        self.summary_manager = None
        self.preferences_aggregator = None
        self.session_compactor = None

        if self.memory_config and self.memory_config.enabled:
            from nanobot.memory.background import ActivityTracker, BackgroundProcessor
            from nanobot.memory.context import create_context_assembler
            from nanobot.memory.embeddings import EmbeddingProvider
            from nanobot.memory.retrieval import create_retrieval
            from nanobot.memory.store import TurboMemoryStore
            from nanobot.memory.summaries import create_summary_manager

            self.memory_store = TurboMemoryStore(self.memory_config, workspace)

            self.activity_tracker = ActivityTracker(
                quiet_threshold_seconds=self.memory_config.background.quiet_threshold_seconds
            )

            self.background_processor = BackgroundProcessor(
                memory_store=self.memory_store,
                activity_tracker=self.activity_tracker,
                interval_seconds=self.memory_config.background.interval_seconds,
            )

            self.summary_manager = create_summary_manager(
                self.memory_store,
                staleness_threshold=self.memory_config.summary.staleness_threshold,
                max_refresh_batch=self.memory_config.summary.max_refresh_batch,
            )

            self.context_assembler = create_context_assembler(
                self.memory_store,
                self.summary_manager,
            )

            embedding_provider = None
            if self.memory_config.embedding.provider == "local":
                embedding_provider = EmbeddingProvider(self.memory_config.embedding)

            self.memory_retrieval = create_retrieval(
                self.memory_store,
                embedding_provider=embedding_provider,
            )

            from nanobot.memory.learning import create_learning_manager
            from nanobot.memory.preferences import create_preferences_aggregator

            self.learning_manager = create_learning_manager(
                self.memory_store,
                embedding_provider=embedding_provider,
                decay_days=self.memory_config.learning.decay_days,
                decay_rate=self.memory_config.learning.relevance_decay_rate,
            )

            self.preferences_aggregator = create_preferences_aggregator(
                self.memory_store,
                self.summary_manager,
            )

            from nanobot.memory.session_compactor import SessionCompactor

            self.session_compactor = SessionCompactor(self.memory_config.session_compaction)

            logger.info("Turbo memory system enabled")

        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
            max_iterations=subagent_max_iterations,
            evolutionary=evolutionary,
            allowed_paths=self.allowed_paths,
            protected_paths=self.protected_paths,
        )

        self._running = False
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        # Determine tool restrictions based on evolutionary mode or restrict_to_workspace
        if self.evolutionary and self.allowed_paths:
            logger.info(f"Evolutionary mode enabled with allowed paths: {self.allowed_paths}")
            allowed_dirs = [Path(p).expanduser().resolve() for p in self.allowed_paths]
            protected_dirs = [Path(p).expanduser().resolve() for p in self.protected_paths]
            self.tools.register(
                ReadFileTool(allowed_paths=allowed_dirs, protected_paths=protected_dirs)
            )
            self.tools.register(
                WriteFileTool(allowed_paths=allowed_dirs, protected_paths=protected_dirs)
            )
            self.tools.register(
                EditFileTool(allowed_paths=allowed_dirs, protected_paths=protected_dirs)
            )
            self.tools.register(
                ListDirTool(allowed_paths=allowed_dirs, protected_paths=protected_dirs)
            )

            self.tools.register(
                ExecTool(
                    working_dir=str(self.workspace),
                    timeout=self.exec_config.timeout,
                    allowed_paths=self.allowed_paths,
                )
            )
        else:
            allowed_dir = self.workspace if self.restrict_to_workspace else None
            self.tools.register(ReadFileTool(allowed_dir=allowed_dir))
            self.tools.register(WriteFileTool(allowed_dir=allowed_dir))
            self.tools.register(EditFileTool(allowed_dir=allowed_dir))
            self.tools.register(ListDirTool(allowed_dir=allowed_dir))

            self.tools.register(
                ExecTool(
                    working_dir=str(self.workspace),
                    timeout=self.exec_config.timeout,
                    restrict_to_workspace=self.restrict_to_workspace,
                )
            )

        self.tools.register(WebSearchTool(api_key=self.brave_api_key))
        self.tools.register(WebFetchTool())

        message_tool = MessageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(message_tool)

        spawn_tool = SpawnTool(manager=self.subagents)
        self.tools.register(spawn_tool)

        self.tools.register(TodoTool(self.workspace))

        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

        self.tools.register(UpdateConfigTool())

        if self.memory_store and self.memory_retrieval:
            from nanobot.agent.tools.memory import create_memory_tools

            memory_tools = create_memory_tools(self.memory_store, self.memory_retrieval)
            for tool in memory_tools:
                self.tools.register(tool)

        from nanobot.agent.tools.security import create_security_tools

        security_tools = create_security_tools()
        for tool in security_tools:
            self.tools.register(tool)

    def _log_content(self, content: str, prefix: str = "", max_len: int = 120) -> str:
        """Return truncated or full content based on config."""
        if self.config.logging.log_full_messages:
            return content
        if len(content) <= max_len:
            return content
        return content[:max_len] + "..."

    def _log_tool_args(self, args: dict, max_len: int = 200) -> str:
        """Return truncated or full tool args based on config."""
        args_str = json.dumps(args, ensure_ascii=False)
        if self.config.logging.log_full_tool_args:
            return args_str
        if len(args_str) <= max_len:
            return args_str
        return args_str[:max_len] + "..."

    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        logger.info("Agent loop started")

        if self.background_processor:
            await self.background_processor.start()

        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0,
                )

                stream_callback = None
                if msg.stream_id:
                    stream_callback = self.bus.get_stream_callback(msg.stream_id)

                try:
                    response = await self._process_message(msg, stream_callback=stream_callback)
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    if msg.stream_id:
                        self.bus.mark_stream_done(msg.stream_id)
                    await self.bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=f"Sorry, I encountered an error: {str(e)}",
                        )
                    )
            except asyncio.TimeoutError:
                continue

    async def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        if self.background_processor:
            await self.background_processor.stop()
        logger.info("Agent loop stopped")

    def _build_messages_with_context(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Call context builder with only supported kwargs for compatibility."""
        build_messages = self.context.build_messages
        try:
            sig = inspect.signature(build_messages)
        except (TypeError, ValueError):
            return build_messages(**kwargs)

        if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()):
            return build_messages(**kwargs)

        filtered = {key: value for key, value in kwargs.items() if key in sig.parameters}
        return build_messages(**filtered)

    def _needs_continuation(self, content: str, finish_reason: str | None = None) -> bool:
        """Detect if a response indicates the agent wants to continue working."""
        if finish_reason == "length":
            return True
        if not content:
            return False
        tail = content[-200:].lower()
        continuation_phrases = [
            "let me check",
            "i will now",
            "next, i'll",
            "i'll continue",
            "searching for",
            "working on",
            "fetching the rest",
            "continuing",
        ]
        return any(phrase in tail for phrase in continuation_phrases)

    def _contains_unverified_actions(self, content: str) -> bool:
        """Detect if the agent claims to have taken actions without calling tools."""
        content_lower = content.lower()
        action_claims = [
            "i've created",
            "i have created",
            "i've modified",
            "i have modified",
            "i've updated",
            "i have updated",
            "i've deleted",
            "i have deleted",
            "i've written",
            "i have written",
            "i've saved",
            "i have saved",
        ]
        return any(claim in content_lower for claim in action_claims)

    async def _select_model(self, msg: InboundMessage, session: Session) -> str:
        """Select the appropriate model using smart routing."""
        if not self.routing_stage:
            self.work_log_manager.log(
                level=LogLevel.INFO,
                category="routing",
                message="Smart routing disabled, using default model",
            )
            return self.model

        try:
            routing_ctx = RoutingContext(
                message=msg,
                session=session,
                default_model=self.model,
                config=self.routing_config,
            )
            start_time = datetime.now()
            routing_ctx = await self.routing_stage.execute(routing_ctx)
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            if routing_ctx.decision:
                self.work_log_manager.log(
                    level=LogLevel.DECISION,
                    category="routing",
                    message=f"Classified as {routing_ctx.decision.tier.value} tier",
                    details={
                        "tier": routing_ctx.decision.tier.value,
                        "model": routing_ctx.model,
                        "confidence": routing_ctx.decision.confidence,
                        "layer": routing_ctx.decision.layer,
                    },
                    confidence=routing_ctx.decision.confidence,
                    duration_ms=duration_ms,
                )
            return routing_ctx.model
        except Exception as e:
            logger.warning(f"Smart routing failed, using default model: {e}")
            self.work_log_manager.log(
                level=LogLevel.WARNING,
                category="routing",
                message=f"Smart routing failed: {str(e)}, using default model",
            )
            return self.model

    async def _process_message(
        self,
        msg: InboundMessage,
        stream_callback: Callable[[str], Any] | None = None,
        session_key: str | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message."""
        if msg.channel == "system":
            return await self._process_system_message(msg)

        # Mark user activity for background processing
        if self.activity_tracker:
            self.activity_tracker.mark_activity()

        # Log message processing start
        preview = self._log_content(msg.content)
        sanitized_preview = self.sanitizer.sanitize(preview)
        self.work_log_manager.log(
            level=LogLevel.INFO,
            category="general",
            message=f"Processing user message: {sanitized_preview}",
        )
        logger.info(f"Processing message from {msg.channel}:{msg.sender_id}: {sanitized_preview}")

        # Get or create session
        session = self.sessions.get_or_create(session_key or msg.session_key)

        # Consolidate memory before processing if session is too large
        if len(session.messages) > self.memory_window:
            await self._consolidate_memory(session)

        # Add message to session history
        session.add_message("user", msg.content, media=msg.media)

        # Turbo Memory: Log event
        if self.memory_store:
            from nanobot.memory.models import Event

            sanitized_content = self.sanitizer.sanitize(msg.content)
            event = Event(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(),
                channel=msg.channel,
                direction="inbound",
                event_type="message",
                content=sanitized_content,
                session_key=msg.session_key,
            )
            self.memory_store.save_event(event)

            # Detect feedback for learning
            if hasattr(self, "learning_manager") and session.messages:
                try:
                    last_assistant_msgs = [
                        m for m in session.messages if m.get("role") == "assistant"
                    ]
                    if last_assistant_msgs:
                        learning = await self.learning_manager.process_message(
                            message=sanitized_content,
                            context=last_assistant_msgs[-1].get("content", ""),
                        )
                        if learning and self.preferences_aggregator:
                            self.preferences_aggregator.increment_staleness()
                            await self.preferences_aggregator.refresh_if_needed()
                except Exception as e:
                    logger.error(f"Failed to process feedback: {e}")

        # Turbo Memory: Assemble context
        memory_context = ""
        if self.context_assembler and self.memory_retrieval:
            try:
                self.work_log_manager.log(
                    level=LogLevel.THINKING, category="memory", message="Retrieving context"
                )
                start_time = datetime.now()
                relevant_entities = self.context_assembler.get_relevant_entities(
                    query=self.sanitizer.sanitize(msg.content), channel=msg.channel, limit=5
                )
                memory_context = self.context_assembler.assemble_context(
                    channel=msg.channel,
                    entity_ids=[e.id for e in relevant_entities],
                    include_preferences=True,
                )
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                self.work_log_manager.log(
                    level=LogLevel.INFO,
                    category="memory",
                    message=f"Retrieved {len(memory_context)} chars of memory context",
                    duration_ms=duration_ms,
                )
            except Exception as e:
                logger.error(f"Failed to assemble memory context: {e}")

        # Session Compaction
        if self.session_compactor:
            try:
                max_tokens = self.memory_config.enhanced_context.max_context_tokens
                if self.session_compactor.should_compact(session.messages, max_tokens):
                    result = await self.session_compactor.compact_session(session, max_tokens)
                    session.messages = result.messages
                    logger.info(
                        f"Session compacted: {result.tokens_before} -> {result.tokens_after}"
                    )
            except Exception as e:
                logger.error(f"Session compaction failed: {e}")

        # Update tool contexts
        for tool_name in ["message", "spawn", "cron"]:
            tool = self.tools.get(tool_name)
            if hasattr(tool, "set_context"):
                tool.set_context(msg.channel, msg.chat_id)

        # Select model
        selected_model = await self._select_model(msg, session)

        # Build initial messages
        messages = self._build_messages_with_context(
            history=session.get_history(),
            current_message=self.sanitizer.sanitize(msg.content),
            media=msg.media,
            channel=msg.channel,
            chat_id=msg.chat_id,
            sender_id=msg.sender_id,
            metadata=msg.metadata,
            memory_context=memory_context if memory_context else None,
        )

        # Agent loop
        iteration = 0
        final_content = None
        tools_called = 0
        seen_tool_hashes = set()
        tools_used: list[str] = []

        while iteration < self.max_iterations:
            iteration += 1

            # Call LLM
            logger.debug(
                f"LLM call (iteration {iteration}/{self.max_iterations}) using {selected_model}"
            )

            try:
                if stream_callback:
                    full_content = ""
                    full_reasoning = ""
                    tool_calls: list = []
                    async for chunk in self.provider.stream(
                        messages=messages,
                        tools=self.tools.get_definitions(),
                        model=selected_model,
                    ):
                        if chunk.content:
                            full_content += chunk.content
                            res = stream_callback(chunk.content)
                            if asyncio.iscoroutine(res):
                                await res
                        if chunk.reasoning_content:
                            full_reasoning += chunk.reasoning_content
                        if chunk.tool_calls:
                            tool_calls.extend(chunk.tool_calls)
                    response = LLMResponse(
                        content=full_content if full_content else None,
                        reasoning_content=full_reasoning if full_reasoning else None,
                        tool_calls=tool_calls,
                    )
                else:
                    response = await self.provider.chat(
                        messages=messages,
                        tools=self.tools.get_definitions(),
                        model=selected_model,
                    )
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                # Optional: try secondary model here as in turbo
                raise e

            # Handle tool calls
            if response.has_tool_calls:
                # Loop detection
                current_hashes = [
                    tool_call_hash(tc.name, tc.arguments) for tc in response.tool_calls
                ]
                if all(h in seen_tool_hashes for h in current_hashes):
                    logger.warning("Infinite loop detected")
                    messages.append(
                        {"role": "user", "content": "ERROR: Loop detected. Try another way."}
                    )
                    continue
                for h in current_hashes:
                    seen_tool_hashes.add(h)

                tools_called += len(response.tool_calls)
                for tc in response.tool_calls:
                    tools_used.append(tc.name)

                # Add assistant message with tool calls
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

                # Execute tools in parallel (MTAAP style)
                async def _exec_one(tc):
                    sanitized_args = self.sanitizer.sanitize(self._log_tool_args(tc.arguments))
                    logger.info(f"Tool call: {tc.name}({sanitized_args})")
                    start_t = datetime.now()
                    try:
                        res = await self.tools.execute(tc.name, tc.arguments)
                        dur = int((datetime.now() - start_t).total_seconds() * 1000)
                        self.work_log_manager.log_tool(tc.name, tc.arguments, res, "success", dur)
                        return tc, res
                    except Exception as err:
                        dur = int((datetime.now() - start_t).total_seconds() * 1000)
                        self.work_log_manager.log(
                            LogLevel.ERROR, "tool_execution", f"Tool {tc.name} failed: {err}", dur
                        )
                        return tc, f"Error: {err}"

                results = await asyncio.gather(*[_exec_one(tc) for tc in response.tool_calls])

                for tc, result in results:
                    messages = self.context.add_tool_result(messages, tc.id, tc.name, result)
                    session.add_message("tool", result, tool_call_id=tc.id, name=tc.name)

                # Interleaved CoT
                messages.append(
                    {"role": "user", "content": "Reflect on results and decide next steps."}
                )
            else:
                # No tool calls, check for continuation or final
                if (
                    iteration < self.max_iterations
                    and response.content
                    and self._needs_continuation(
                        response.content, getattr(response, "finish_reason", None)
                    )
                ):
                    logger.info("Auto-continuation triggered")
                    if response.content and not stream_callback:
                        await self.bus.publish_outbound(
                            OutboundMessage(
                                channel=msg.channel,
                                chat_id=msg.chat_id,
                                content=response.content,
                                metadata=msg.metadata or {},
                            )
                        )
                    messages = self.context.add_assistant_message(
                        messages, response.content, reasoning_content=response.reasoning_content
                    )
                    messages.append({"role": "user", "content": "Continue"})
                    continue

                if (
                    response.content
                    and tools_called == 0
                    and self._contains_unverified_actions(response.content)
                    and iteration < self.max_iterations
                ):
                    logger.warning("Action claim without tool use")
                    messages = self.context.add_assistant_message(
                        messages, response.content, reasoning_content=response.reasoning_content
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": "You claimed action but used no tools. Use a tool.",
                        }
                    )
                    continue

                final_content = response.content
                break

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        # Log and save response
        sanitized_final = self.sanitizer.sanitize(final_content)
        preview = self._log_content(sanitized_final)
        logger.info(f"Response to {msg.channel}:{msg.sender_id}: {preview}")
        self.work_log_manager.log(
            LogLevel.INFO,
            "general",
            "Response generated successfully",
            {"length": len(final_content)},
        )

        session.add_message(
            "assistant",
            sanitized_final,
            tools_used=tools_used if tools_used else None,
            reasoning_content=getattr(response, "reasoning_content", None),
        )
        self.sessions.save(session)

        # Log outbound to Turbo Memory
        if self.memory_store:
            event = Event(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(),
                channel=msg.channel,
                direction="outbound",
                event_type="message",
                content=sanitized_final,
                session_key=msg.session_key,
            )
            self.memory_store.save_event(event)

        if msg.stream_id:
            self.bus.mark_stream_done(msg.stream_id)

        if stream_callback:
            return None

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=msg.metadata or {},
        )

    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """Process a system message (e.g., subagent announce)."""
        logger.info(f"Processing system message from {msg.sender_id}")
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel, origin_chat_id = parts[0], parts[1]
        else:
            origin_channel, origin_chat_id = "cli", msg.chat_id

        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)

        for tool_name in ["message", "spawn", "cron"]:
            tool = self.tools.get(tool_name)
            if hasattr(tool, "set_context"):
                tool.set_context(origin_channel, origin_chat_id)

        messages = self._build_messages_with_context(
            history=session.get_history(),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
            sender_id=msg.sender_id,
            metadata=msg.metadata,
        )

        selected_model = await self._select_model(msg, session)

        iteration = 0
        final_content = None
        while iteration < self.max_iterations:
            iteration += 1
            response = await self.provider.chat(
                messages=messages, tools=self.tools.get_definitions(), model=selected_model
            )
            if response.has_tool_calls:
                # Basic sequential execution for announce handling
                for tc in response.tool_calls:
                    result = await self.tools.execute(tc.name, tc.arguments)
                    messages = self.context.add_tool_result(messages, tc.id, tc.name, result)
            else:
                final_content = response.content
                break

        if final_content:
            return OutboundMessage(
                channel=origin_channel, chat_id=origin_chat_id, content=final_content
            )
        return None

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:default",
        channel: str = "cli",
        chat_id: str = "direct",
        stream_callback: Callable[[str], Any] | None = None,
    ) -> str | None:
        """Process a message directly without going through the bus."""
        msg = InboundMessage(
            channel=channel,
            chat_id=chat_id,
            sender_id="user",
            content=content,
            session_key=session_key,
        )

        response = await self._process_message(msg, stream_callback=stream_callback)
        return response.content if response else None

    async def _consolidate_memory(self, session: Session) -> None:
        """Consolidate session history if it exceeds window size."""
        # Simple sliding window for now (or use SessionCompactor if enabled)
        if self.session_compactor:
            try:
                max_tokens = self.memory_config.enhanced_context.max_context_tokens
                await self.session_compactor.compact_session(session, max_tokens)
            except Exception as e:
                logger.error(f"Memory consolidation failed: {e}")
                session.messages = session.messages[-self.memory_window :]
        else:
            session.messages = session.messages[-self.memory_window :]

    async def _memory_flush_hook(self, session: Session, msg: InboundMessage) -> None:
        """Flush session context to memory before compaction."""
        if not self.memory_store:
            return
        # Logic to ensure important bits from session are in memory before they are summarized/truncated
        pass
