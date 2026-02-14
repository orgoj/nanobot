# CLAUDE.md for nanobot (orgoj2)

## Development Safety Guidelines

> [!CAUTION]
> **DO NOT run nanobot locally outside of Docker for testing purposes.**
> This is especially critical for AI agents and automated scripts.
>
> Running `nanobot` commands directly on the host machine will modify or overwrite files in `~/.nanobot/`.

### Testing Protocols

- **Isolated Testing ONLY**: Only run code changes if they are covered by isolated unit tests that do not touch `~/.nanobot/`.
- **Use Docker**: All integration testing and runtime behavior checks must be performed inside a Docker container.

## Project Overview

nanobot is an ultra-lightweight, event-driven AI agent framework.

## Codebase Map
See `CODEBASE-MAP.md` for the full codebase context map.

- **Core Agent**: `{nanobot}/agent/` (Context building, loop)
- **Channels**: `{nanobot}/channels/` (Telegram, Discord, etc.)
- **Tools**: `{nanobot}/agent/tools/` (FileSystem, Shell, Web, ZAI)
- **Config**: `{nanobot}/config/` (Pydantic schema, JSONL logging config)
- **CLI**: `{nanobot}/cli/` (Interactive prompt_toolkit)
- **Logs**: `~/.nanobot/logs/nanobot.jsonl` (Structured PIMONO style)
- **Memory**: `{workspace}/memory/` (Purely file-based: MEMORY.md, HISTORY.md)
- **Failures**: `{workspace}/FAILURES.md` (Failure log for self-improvement)

## Build & Run Commands

### Docker

```bash
# Build
docker build -t nanobot .

# Run
./run-docker.sh
```

### Local Development

```bash
# Formatter & Linter (Mandatory)
uv run ruff format .
uv run ruff check --fix .

# Run Tests
uv run pytest tests/

# Verify Line Count (KISS target: ~4000)
bash core_agent_lines.sh
```

## Development Workflow

- **Pre-commit REQUIRED**: Every commit MUST pass `ruff format`, `ruff check`, and `pytest`. 
- **NO Bypass**: Never use `PRE_COMMIT_ALLOW_NO_CONFIG=1` or `--no-verify`.
- **KISS Principle**: Keep it simple. Prioritize text files over databases. No embeddings/vecdb in core.

## Coding Style
- Follow PEP 8
- Use type hints
- Keep core logic concise
- **Logging**: Use `logger.contextualize` for consistent JSONL metadata.
- **Formatting**: Ported `markdown-it` based Telegram formatter (HTML + Tables).
