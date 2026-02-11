# CLAUDE.md for nanobot

## Development Safety Guidelines

> [!CAUTION]
> **DO NOT run nanobot locally outside of Docker for testing purposes.**
> This is especially critical for AI agents and automated scripts.
>
> Running `nanobot` commands (like `onboard`, `status`, `agent`, or `gateway`) directly on the host machine will modify or overwrite files in `~/.nanobot/`, including your personal `config.json`.

### Testing Protocols

- **Isolated Testing ONLY**: Only run code changes if they are covered by isolated unit tests that do not touch `~/.nanobot/`.
- **Use Docker**: All integration testing, configuration verification, and runtime behavior checks must be performed inside a Docker container.
- **Mock Config**: If you must run locally, always point to a temporary configuration file using environment variables or dedicated test arguments (if supported).

## Project Overview

nanobot is an ultra-lightweight AI agent framework.

- **Core Agent**: `nanobot/agent/`
- **Channels**: `nanobot/channels/`
- **Tools**: `nanobot/agent/tools/`
- **Config**: `nanobot/config/`
- **CLI**: `nanobot/cli/`
- **Logs**: `{workspace}/logs/nanobot.log` (when enabled)

## Build & Run Commands

### Docker (Recommended for Testing)
```bash
# Build
docker build -t nanobot .

# Run Gateway
docker run -v ~/.nanobot:/home/nanobot/.nanobot -p 18790:18790 nanobot gateway

# Run Status
docker run -v ~/.nanobot:/home/nanobot/.nanobot --rm nanobot status
```

### Local Development (DANGER: Read Safety Guidelines)
```bash
# Install in editable mode
pip install -e .

# Verify core agent lines
bash core_agent_lines.sh
```

## Coding Style
- Follow PEP 8
- Use type hints
- Keep core logic concise (the project goal is < 4000 lines)
- New providers should be added via `nanobot/providers/registry.py`
