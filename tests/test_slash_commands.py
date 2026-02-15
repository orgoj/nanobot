"""Tests for agent loop slash commands."""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.agent.subagent import SubagentState
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus


class MockProvider:
    def get_default_model(self):
        return "mock-model"

    async def chat(self, *args, **kwargs):
        return MagicMock()


@pytest.mark.asyncio
async def test_slash_help():
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MockProvider()
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace)

        msg = InboundMessage(channel="test", sender_id="user", chat_id="123", content="/help")

        response = await loop._process_message(msg)
        assert response is not None
        assert "/status" in response.content
        assert "/new" in response.content
        assert "/cancel" in response.content
        assert "/uptime" in response.content
        assert "/ping" in response.content
        assert "/help" in response.content


@pytest.mark.asyncio
async def test_slash_ping():
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MockProvider()
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace)

        msg = InboundMessage(channel="test", sender_id="user", chat_id="123", content="/ping")

        response = await loop._process_message(msg)
        assert response is not None
        assert "pong" in response.content


@pytest.mark.asyncio
async def test_slash_uptime():
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MockProvider()
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace)

        msg = InboundMessage(channel="test", sender_id="user", chat_id="123", content="/uptime")

        response = await loop._process_message(msg)
        assert response is not None
        assert "nanobot uptime:" in response.content


@pytest.mark.asyncio
async def test_slash_cancel():
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MockProvider()
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace)

        # Mock an active subagent
        state = SubagentState(
            task_id="killme",
            task="to be cancelled",
            label="killme-label",
            origin={"channel": "test", "chat_id": "123"},
            start_time=datetime.now(),
            status="running",
        )
        # Mock the task handle so it can be cancelled
        state.task_handle = MagicMock()
        loop.subagents._registry["killme"] = state

        msg = InboundMessage(
            channel="test", sender_id="user", chat_id="123", content="/cancel killme"
        )

        response = await loop._process_message(msg)
        assert response is not None
        assert "cancelled" in response.content
        assert state.status == "cancelled"


@pytest.mark.asyncio
async def test_slash_status_empty():
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MockProvider()
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace)

        msg = InboundMessage(channel="test", sender_id="user", chat_id="123", content="/status")

        response = await loop._process_message(msg)
        assert response is not None
        assert "No active background subagents" in response.content


@pytest.mark.asyncio
async def test_slash_status_active():
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MockProvider()
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace)

        # Mock an active subagent
        state = SubagentState(
            task_id="test-id",
            task="This is a very long task prompt that should be truncated at some point in the status output if it exceeds 100 characters, which this one hopefully does by now.",
            label="test-label",
            origin={"channel": "test", "chat_id": "123"},
            start_time=datetime.now(),
            status="running",
        )
        loop.subagents._registry["test-id"] = state

        msg = InboundMessage(channel="test", sender_id="user", chat_id="123", content="/status")

        response = await loop._process_message(msg)
        assert response is not None
        assert "### Active Subagents Status" in response.content
        assert "test-label" in response.content
        assert "test-id" in response.content
        assert "Uptime:" in response.content
        assert "Task:" in response.content
        assert "truncated" in response.content
        assert len(response.content) > 0
