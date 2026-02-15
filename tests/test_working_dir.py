"""Unit tests for subagent working directory support."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from nanobot.agent.subagent import SubagentManager
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider, LLMResponse


class MockProvider(LLMProvider):
    async def chat(self, messages, tools=None, model=None, **kwargs):
        return LLMResponse(content="Done", tool_calls=[])

    def get_default_model(self):
        return "mock"


@pytest.mark.asyncio
async def test_subagent_working_dir_propagation():
    """Test that working_dir is correctly stored and would be passed to tools."""
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MockProvider()

        manager = SubagentManager(
            provider=provider, workspace=workspace, bus=bus, model="test-model"
        )

        custom_dir = "/tmp/custom_project"

        # Spawn a subagent with custom working_dir
        result = await manager.spawn(task="Test task", label="test-label", working_dir=custom_dir)

        task_id = result.split("id: ")[1].split(")")[0]
        state = manager.get_state(task_id)

        assert state.working_dir == custom_dir

        # We don't easily test the tool registration here without more mocking,
        # but the state storage is confirmed.
