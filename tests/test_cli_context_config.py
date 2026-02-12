from pathlib import Path

from nanobot.config.schema import Config, ContextConfig


def _fake_asyncio_run(coro):
    coro.close()


class DummySessionManager:
    def __init__(self, *args, **kwargs):
        pass


def test_gateway_passes_context_config(monkeypatch, tmp_path: Path) -> None:
    from nanobot.cli import commands

    captured: dict[str, object] = {}

    class DummyAgent:
        def __init__(self, *args, **kwargs):
            captured["context_config"] = kwargs.get("context_config")

        async def process_direct(self, *args, **kwargs):
            return ""

        async def run(self):
            return None

        def stop(self):
            return None

    config = Config()
    config.context = ContextConfig(
        context_plugin_package="pkg",
        context_plugin_class="Cls",
        context_plugin_config={"k": "v"},
    )

    monkeypatch.setattr("nanobot.agent.loop.AgentLoop", DummyAgent)
    monkeypatch.setattr("nanobot.session.manager.SessionManager", DummySessionManager)
    monkeypatch.setattr("nanobot.config.loader.load_config", lambda: config)
    monkeypatch.setattr("nanobot.config.loader.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nanobot.cli.commands._make_provider", lambda cfg: object())
    monkeypatch.setattr("nanobot.cli.commands.asyncio.run", _fake_asyncio_run)

    commands.gateway(port=18790, verbose=False)

    assert captured["context_config"] == config.context


def test_agent_passes_context_config(monkeypatch) -> None:
    from nanobot.cli import commands

    captured: dict[str, object] = {}

    class DummyAgent:
        def __init__(self, *args, **kwargs):
            captured["context_config"] = kwargs.get("context_config")

        async def process_direct(self, *args, **kwargs):
            return ""

        async def run(self):
            return None

        def stop(self):
            return None

    config = Config()
    config.context = ContextConfig(
        context_plugin_package="pkg",
        context_plugin_class="Cls",
        context_plugin_config={"k": "v"},
    )

    monkeypatch.setattr("nanobot.agent.loop.AgentLoop", DummyAgent)
    monkeypatch.setattr("nanobot.session.manager.SessionManager", DummySessionManager)
    monkeypatch.setattr("nanobot.config.loader.load_config", lambda: config)
    monkeypatch.setattr("nanobot.cli.commands._make_provider", lambda cfg: object())
    monkeypatch.setattr("nanobot.cli.commands.asyncio.run", _fake_asyncio_run)

    commands.agent(message="hi", session_id="cli:test", markdown=False, logs=False)

    assert captured["context_config"] == config.context
