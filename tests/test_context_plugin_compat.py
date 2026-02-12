import asyncio
from pathlib import Path

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.config.schema import ExecToolConfig


class DummyProvider:
    def get_default_model(self) -> str:
        return "dummy"


class DummySessionManager:
    def get_or_create(self, session_key: str):
        raise AssertionError("not used")

    def save(self, session):
        raise AssertionError("not used")


class LegacyContext:
    def __init__(self) -> None:
        self.called = False

    def build_messages(
        self,
        history: list[dict[str, object]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict[str, str]]:
        self.called = True
        return [{"role": "user", "content": current_message}]


class KwargsContext:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    def build_messages(
        self,
        history: list[dict[str, object]],
        current_message: str,
        **kwargs: object,
    ) -> list[dict[str, str]]:
        self.kwargs = kwargs
        return [{"role": "user", "content": current_message}]


def _make_agent(tmp_path: Path) -> AgentLoop:
    return AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
        model="dummy",
        exec_config=ExecToolConfig(),
        session_manager=DummySessionManager(),
    )


def test_build_messages_filters_kwargs_for_legacy_context(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    legacy = LegacyContext()
    agent.context = legacy

    messages = agent._build_messages_with_context(
        history=[],
        current_message="hello",
        skill_names=None,
        media=None,
        channel="feishu",
        chat_id="oc_1",
        sender_id="ou_1",
        metadata={"foo": "bar"},
    )

    assert legacy.called
    assert messages == [{"role": "user", "content": "hello"}]


def test_build_messages_passes_kwargs_when_supported(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    ctx = KwargsContext()
    agent.context = ctx

    agent._build_messages_with_context(
        history=[],
        current_message="hello",
        sender_id="ou_1",
        metadata={"foo": "bar"},
    )

    assert ctx.kwargs == {"sender_id": "ou_1", "metadata": {"foo": "bar"}}


@pytest.mark.asyncio
async def test_run_marks_stream_done_on_error(tmp_path: Path) -> None:
    bus = MessageBus()
    agent = AgentLoop(
        bus=bus,
        provider=DummyProvider(),
        workspace=tmp_path,
        model="dummy",
        exec_config=ExecToolConfig(),
        session_manager=DummySessionManager(),
    )

    async def boom(msg: InboundMessage, stream_callback=None):
        raise RuntimeError("boom")

    agent._process_message = boom  # type: ignore[assignment]

    stream_id = "stream-1"
    bus.register_stream_callback(stream_id, lambda chunk: None)

    task = asyncio.create_task(agent.run())
    await bus.publish_inbound(
        InboundMessage(
            channel="feishu",
            sender_id="user",
            chat_id="oc_1",
            content="hi",
            stream_id=stream_id,
        )
    )

    done = await bus.wait_stream_done(stream_id, timeout=1)
    agent.stop()
    await asyncio.wait_for(task, timeout=2)

    assert done is True
