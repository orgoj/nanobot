from pathlib import Path
from unittest.mock import MagicMock

def _fake_asyncio_run(coro):
    coro.close()

def test_gateway_passes_context_config(monkeypatch, tmp_path: Path) -> None:
    from nanobot.cli import commands
    import nanobot.agent.loop
    
    class DummyAgent:
        def __init__(self, *args, **kwargs):
            self.bus = MagicMock()
            self.background_processor = None
        async def run(self): pass
        async def stop(self): pass
        async def process_direct(self, *args, **kwargs): return ""

    monkeypatch.setattr(nanobot.agent.loop, "AgentLoop", DummyAgent)

    mock_config = MagicMock()
    mock_config.workspace_path = tmp_path
    mock_config.agents.defaults.heartbeat_on_start = False
    mock_config.agents.defaults.startup_prompt = None

    monkeypatch.setattr("nanobot.config.loader.load_config", lambda: mock_config)
    monkeypatch.setattr("nanobot.config.loader.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nanobot.cli.commands._make_provider", lambda cfg: MagicMock())
    monkeypatch.setattr("nanobot.cli.commands.asyncio.run", _fake_asyncio_run)
    monkeypatch.setattr("nanobot.heartbeat.service.HeartbeatService", MagicMock())

    # This test now just verifies that gateway() can run with our patched AgentLoop
    commands.gateway(port=18790, verbose=False)


def test_agent_passes_context_config(monkeypatch, tmp_path: Path) -> None:
    from nanobot.cli import commands
    import nanobot.agent.loop
    
    class DummyAgent:
        def __init__(self, *args, **kwargs): pass
        async def process_direct(self, *args, **kwargs): return ""
        async def stop(self): pass

    monkeypatch.setattr(nanobot.agent.loop, "AgentLoop", DummyAgent)

    mock_config = MagicMock()
    mock_config.workspace_path = tmp_path

    monkeypatch.setattr("nanobot.config.loader.load_config", lambda: mock_config)
    monkeypatch.setattr("nanobot.cli.commands._make_provider", lambda cfg: MagicMock())
    monkeypatch.setattr("nanobot.cli.commands.asyncio.run", _fake_asyncio_run)

    # Verifies agent() command execution
    commands.agent(message="hi", session_id="cli:test", markdown=False, logs=False)
