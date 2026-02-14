"""Integration tests for subagent orchestration and observability."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.agent.subagent import SubagentManager, SubagentState
from nanobot.bus.queue import MessageBus
from nanobot.config.schema import Config
from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class MockProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self):
        self.call_count = 0
        self.responses = []

    async def chat(self, messages, tools=None, model=None, **kwargs):
        self.call_count += 1
        if self.responses:
            return self.responses.pop(0)
        return LLMResponse(content="Mock response", tool_calls=[])

    def get_default_model(self):
        return "mock-model"


@pytest.mark.asyncio
async def test_subagent_spawn_and_complete():
    """Test that subagents can be spawned and complete tasks."""
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MockProvider()
        provider.responses = [LLMResponse(content="Task completed successfully", tool_calls=[])]

        manager = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model="test-model",
            max_iterations=5,
        )

        # Spawn a subagent
        result = await manager.spawn(
            task="Test task",
            label="test-label",
            origin_channel="test",
            origin_chat_id="123",
        )

        assert "test-label" in result
        assert len(manager.list_active()) == 1

        # Wait for completion
        await asyncio.sleep(0.5)

        # Check that it completed
        states = manager.list_all()
        assert len(states) == 1
        assert states[0].status in ["completed", "running"]


@pytest.mark.asyncio
async def test_subagent_message_injection():
    """Test that messages can be injected into running subagents."""
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MockProvider()

        # Simulate multiple iterations before completing
        for _ in range(3):
            provider.responses.append(
                LLMResponse(
                    content="",
                    tool_calls=[ToolCallRequest(id="mock", name="read_file", arguments={})],
                )
            )
        provider.responses.append(LLMResponse(content="Final result", tool_calls=[]))

        manager = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model="test-model",
            max_iterations=10,
        )

        # Spawn subagent
        result = await manager.spawn(
            task="Long running task",
            label="long-task",
            origin_channel="test",
            origin_chat_id="123",
        )

        task_id = result.split("id: ")[1].split(")")[0]

        # Inject a message immediately (before it completes)
        success = await manager.send_message(task_id, "Please change your approach")
        assert success is True

        # Wait for completion
        await asyncio.sleep(0.5)

        # Verify state exists
        state = manager.get_state(task_id)
        assert state is not None
        assert state.status in ["completed", "failed"]


@pytest.mark.asyncio
async def test_subagent_cancel():
    """Test that subagents can be cancelled."""
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MockProvider()

        # Create an async mock that will delay
        async def slow_chat(*args, **kwargs):
            await asyncio.sleep(0.2)
            return LLMResponse(
                content="", tool_calls=[ToolCallRequest(id="mock", name="exec", arguments={})]
            )

        provider.chat = slow_chat

        manager = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model="test-model",
            max_iterations=30,
        )

        # Spawn subagent
        result = await manager.spawn(
            task="Never-ending task",
            label="cancel-test",
            origin_channel="test",
            origin_chat_id="123",
        )

        task_id = result.split("id: ")[1].split(")")[0]

        # Allow it to start processing
        await asyncio.sleep(0.05)

        # Cancel it
        success = await manager.cancel(task_id)
        assert success is True

        # Check status
        state = manager.get_state(task_id)
        assert state.status == "cancelled"


@pytest.mark.asyncio
async def test_tiered_model_selection():
    """Test that AgentLoop uses tiered models correctly."""
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MockProvider()

        config = Config()
        config.agents.defaults.chat_model = "fast-chat-model"
        config.agents.defaults.task_model = "powerful-task-model"

        loop = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=workspace,
            config=config,
        )

        # Main loop should use chat model
        assert loop.model == "fast-chat-model"
        assert loop.chat_model == "fast-chat-model"
        assert loop.task_model == "powerful-task-model"

        # Subagent manager should use task model
        assert loop.subagents.model == "powerful-task-model"


@pytest.mark.asyncio
async def test_subagent_observability():
    """Test that subagent state is properly tracked and observable."""
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MockProvider()
        provider.responses = [LLMResponse(content="Done", tool_calls=[])]

        manager = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model="test-model",
            max_iterations=5,
        )

        # Spawn multiple subagents
        await manager.spawn("Task 1", "task-1", "test", "123")
        await manager.spawn("Task 2", "task-2", "test", "123")

        # Check that we can list them
        active = manager.list_active()
        assert len(active) >= 1  # At least one should still be running

        all_states = manager.list_all()
        assert len(all_states) == 2

        # Check state structure
        for state in all_states:
            assert isinstance(state, SubagentState)
            assert state.task_id
            assert state.task
            assert state.label
            assert state.start_time
            assert state.status in ["running", "completed", "failed", "cancelled"]


@pytest.mark.asyncio
async def test_subagent_history_access():
    """Test that subagent conversation history can be accessed."""
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MockProvider()
        provider.responses = [LLMResponse(content="Step 1 complete", tool_calls=[])]

        manager = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model="test-model",
            max_iterations=5,
        )

        result = await manager.spawn("Complex task", "history-test", "test", "123")
        task_id = result.split("id: ")[1].split(")")[0]

        # Wait for processing
        await asyncio.sleep(0.3)

        # Get state and verify history
        state = manager.get_state(task_id)
        assert state is not None
        assert len(state.messages) > 0
        assert state.messages[0]["role"] == "system"
        assert state.messages[1]["role"] == "user"
