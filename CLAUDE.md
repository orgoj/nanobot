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

- **Core Agent**: `{nanobot}/agent/`
- **Channels**: `{nanobot}/channels/`
- **Tools**: `{nanobot}/agent/tools/`
- **Config**: `{nanobot}/config/`
- **CLI**: `{nanobot}/cli/`
- **Providers**: `{nanobot}/providers/` (via LiteLLM)
- **Skills**: `{nanobot}/skills/`
- **Cron**: `{nanobot}/cron/`
- **Session**: `{nanobot}/session/`
- **Logs**: `{workspace}/logs/nanobot.log` (when enabled)

Directory "./instance" contains symlinks to docker container workspaces for analysis.

## Build & Run Commands

### Docker (Recommended)
```bash
# Build
docker build -t nanobot .

# Run Gateway (detached with restart) - use helper script
./run-docker.sh

# Or manually:
docker run -d --name nanobot \
  -v ~/work/nanobot/.nanobot:/home/nanobot/.nanobot \
  -v ~/work/nanobot/workspace:/home/nanobot/workspace \
  --restart unless-stopped \
  -p 18790:18790 nanobot gateway

# Helper scripts
./start-docker.sh    # Start existing container
./stop-docker.sh     # Stop container
./restart-docker.sh  # Restart container
```

### Local Development (DANGER: Read Safety Guidelines)
```bash
# Run isolated tests ONLY - safe, does not touch ~/.nanobot/
uv run pytest tests/

# Verify core agent lines (< 4000 goal)
bash core_agent_lines.sh
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `nanobot onboard` | Initialize config & workspace |
| `nanobot status` | Show configuration status |
| `nanobot agent` | Interactive chat mode |
| `nanobot agent -m "Hello"` | Single message mode |
| `nanobot gateway` | Start server (all channels) |
| `nanobot channels status` | Show channel configs |
| `nanobot channels login` | Link WhatsApp via QR |
| `nanobot cron list` | List scheduled jobs |
| `nanobot cron add -n "name" -m "msg" --every 3600` | Add job (every hour) |
| `nanobot cron remove <id>` | Remove job |
| `nanobot cron run <id>` | Run job manually |

## Coding Style
- Follow PEP 8
- Use type hints
- Keep core logic concise (the project goal is < 4000 lines)
- New providers should be added via `nanobot/providers/registry.py`
- Use `uv` for dependency management (pyproject.toml)
- Run `ruff` for linting: `uv run ruff check nanobot/`
