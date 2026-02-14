"""Tests for YAML configuration support."""

from pathlib import Path
from tempfile import TemporaryDirectory

from nanobot.config.loader import load_config, save_config
from nanobot.config.schema import Config


def test_load_yaml_with_comments():
    """Test that YAML files with comments can be loaded."""
    with TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        config_content = """
# This is a comment
agents:
  defaults:
    model: anthropic/claude-opus-4-5
    # Tiered models
    chat_model: anthropic/claude-sonnet-4
    task_model: anthropic/claude-opus-4-5

providers:
  anthropic:
    api_key: test-key
"""
        config_path.write_text(config_content)

        config = load_config(config_path)
        assert config.agents.defaults.model == "anthropic/claude-opus-4-5"
        assert config.agents.defaults.chat_model == "anthropic/claude-sonnet-4"
        assert config.agents.defaults.task_model == "anthropic/claude-opus-4-5"
        assert config.providers.anthropic.api_key == "test-key"


def test_snake_case_consistency():
    """Test that YAML uses snake_case (same as Python code)."""
    with TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        config_content = """
agents:
  defaults:
    max_tokens: 4096
    memory_window: 100
  main:
    max_tool_iterations: 30
"""
        config_path.write_text(config_content)

        config = load_config(config_path)
        assert config.agents.defaults.max_tokens == 4096
        assert config.agents.defaults.memory_window == 100
        assert config.agents.main.max_tool_iterations == 30


def test_tiered_agents_config():
    """Test separate main and task agent configuration."""
    with TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        config_content = """
agents:
  defaults:
    model: anthropic/claude-opus-4-5
  main:
    model: anthropic/claude-sonnet-4
    temperature: 0.5
    max_tokens: 4096
  task:
    model: anthropic/claude-opus-4-5
    temperature: 0.8
    max_iterations: 50
"""
        config_path.write_text(config_content)

        config = load_config(config_path)
        assert config.agents.main.model == "anthropic/claude-sonnet-4"
        assert config.agents.main.temperature == 0.5
        assert config.agents.main.max_tokens == 4096
        assert config.agents.task.model == "anthropic/claude-opus-4-5"
        assert config.agents.task.temperature == 0.8
        assert config.agents.task.max_iterations == 50


def test_save_and_reload():
    """Test that config can be saved and reloaded."""
    with TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"

        # Create and save
        config = Config()
        config.agents.defaults.model = "test-model"
        config.agents.main.temperature = 0.9
        config.providers.anthropic.api_key = "test-key"
        save_config(config, config_path)

        # Reload
        loaded = load_config(config_path)
        assert loaded.agents.defaults.model == "test-model"
        assert loaded.agents.main.temperature == 0.9
        assert loaded.providers.anthropic.api_key == "test-key"


def test_multiline_strings():
    """Test YAML multi-line string support."""
    with TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        config_content = """
agents:
  defaults:
    workspace: |
      /home/user/.nanobot/workspace
      # This could be multi-line if needed
"""
        config_path.write_text(config_content)

        config = load_config(config_path)
        assert "/home/user/.nanobot/workspace" in config.agents.defaults.workspace


def test_fallback_to_default_on_error():
    """Test that invalid YAML falls back to defaults."""
    with TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        config_path.write_text("{ invalid yaml: [")

        config = load_config(config_path)
        # Should return default config
        assert config.agents.defaults.model == "anthropic/claude-opus-4-5"
