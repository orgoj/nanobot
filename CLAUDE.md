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

## Instance Directory

The `./instance/` directory contains symlinks to the Docker container's config and workspace:

```
instance/
├── .nanobot -> /path/to/actual/config    # Symlink to config directory
└── workspace -> /path/to/actual/workspace # Symlink to workspace
```

**How it works:**
- `run-docker.sh` uses `readlink -f` to resolve symlinks to absolute paths
- Docker mounts the resolved paths into the container
- This allows each developer to point to their own config/workspace locations
- To set up: create symlinks pointing to your actual directories

**Setup example:**
```bash
# Remove existing symlinks if any
rm -rf instance/.nanobot instance/workspace

# Create symlinks to your locations
ln -s ~/work/nanobot/.nanobot instance/.nanobot
ln -s ~/work/nanobot/workspace instance/workspace
```

## Build & Run Commands

### Docker (Recommended)

> [!CRITICAL]
> **Code changes in host filesystem do NOT affect running container!**
> 
> Docker containers run with the code that was baked into the image at build time.
> 
> **After ANY code changes, you MUST:**
> 1. Rebuild: `docker build -t nanobot .`
> 2. Restart: `./restart-docker.sh` (or stop + run)
> 
> **The running container will NEVER see your local code changes until rebuilt.**
> This includes fixes, new features, config changes - everything requires rebuild.

```bash
# Build (REQUIRED after any code change)
docker build -t nanobot .

# Run Gateway (uses instance/ symlinks)
./run-docker.sh

# Helper scripts
./start-docker.sh    # Start existing container
./stop-docker.sh     # Stop container
./restart-docker.sh  # Restart container (doesn't rebuild!)
```

**See [DOCKER.md](DOCKER.md) for detailed information about the Docker image structure, container layout, and common operations.**

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

## Development Workflow

- **Mandatory Quality Check**: After ANY code changes and before declaring a task as finished, you MUST run the formatter, linter, and tests. Everything must pass 100% to ensure the code is production-ready.
  ```bash
  # Local check (fast)
  uv run ruff format .
  uv run ruff check --fix .
  uv run pytest tests/

  # Docker check (isolated, recommended for final verification)
  ./test-docker.sh
  ```

## Coding Style
- Follow PEP 8
- Use type hints
- Keep core logic concise (the project goal is < 4000 lines)
- New providers should be added via `nanobot/providers/registry.py`
- Use `uv` for dependency management (pyproject.toml)
- Run `ruff` for linting: `uv run ruff check nanobot/`
