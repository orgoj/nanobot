# CLAUDE.md for nanobot

## Development Safety Guidelines

> [!CAUTION]
> **DO NOT run nanobot locally outside of Docker for testing purposes.**
> This is especially critical for AI agents and automated scripts.
>
> Running `nanobot` commands directly on the host machine will modify or overwrite files in `~/.nanobot/`.

### Testing Protocols

- **Isolated Testing ONLY**: Only run code changes if they are covered by isolated unit tests that do not touch `~/.nanobot/`.
- **Use Docker**: All integration testing and runtime behavior checks must be performed inside a Docker container.
- **NO SECRETS IN OUTPUT**: Never display, print, or log API keys, tokens, or credentials. Use environment variables. If a secret is accidentally leaked in the tool output, it must be reported and immediately redacted.

## Project Overview

nanobot is an ultra-lightweight, event-driven AI agent framework with interactive subagent orchestration.

### Core Features
- **Tiered Model Selection**: Separate `chat_model` (fast, responsive) and `task_model` (powerful, for complex subagent work)
- **Interactive Subagent Orchestration**: Spawn, monitor, and dynamically control long-running background tasks
- **Full Observability**: Structured JSONL logging with `logger.contextualize` for every agent and subagent
- **KISS Architecture**: File-based memory (no SQL/vecdb), modular tools, async message bus

## Codebase Map
See `CODEBASE-MAP.md` for the full codebase context map.

- **Core Agent**: `nanobot/agent/` (Context building, loop, subagent orchestration)
  - `loop.py`: Main agent loop with tiered model support
  - `subagent.py`: SubagentManager with registry, mailbox, and state tracking
  - `context.py`: ContextBuilder with subagent awareness injection
- **Channels**: `nanobot/channels/` (Telegram, Discord, WhatsApp, etc.)
- **Tools**: `nanobot/agent/tools/` 
  - Standard: FileSystem, Shell, Web, ZAI
  - Orchestration: `subagent.py` (spawn, status, message, history, cancel)
- **Config**: `nanobot/config/` (Pydantic schema with tiered models)
- **CLI**: `nanobot/cli/` (Interactive prompt_toolkit)
- **Logs**: `~/.nanobot/logs/nanobot.jsonl` (Structured PIMONO style)
- **Memory**: `{workspace}/memory/` (File-based: MEMORY.md, HISTORY.md)
- **Failures**: `{workspace}/FAILURES.md` (Failure log for self-improvement)

## Interactive Subagent Orchestration

The main agent can:
1. **Spawn** subagents for long-running tasks (`spawn` tool)
2. **Monitor** all active subagents (`subagent_status` tool)
3. **Inject guidance** into running subagents (`subagent_message` tool)
4. **Inspect progress** by viewing conversation history (`subagent_history` tool)
5. **Cancel** stuck or incorrect subagents (`subagent_cancel` tool)

### Subagent Mailbox Pattern
- Each subagent has an `asyncio.Queue` mailbox
- Main agent can inject messages via `subagent_message` tool
- Subagent checks mailbox at the start of every iteration
- Injected messages are wrapped in `<SupervisorCorrection>` XML tags
- Full audit trail in JSONL logs with unique `task_id` and `session_key`

### Tiered Model Configuration
```json
{
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5",
      "chat_model": "anthropic/claude-sonnet-4",  // Fast, for user interaction
      "task_model": "anthropic/claude-opus-4-5",  // Powerful, for subagents
      "task_max_iterations": 30
    }
  }
}
```

## Build & Run Commands

### Important: Script Execution Rules
- **CWD**: Always work in project root (`/home/michael/projects/nanobot`)
- **NO cd in subshell**: Scripts must be run from project root, not `(cd DIR && CMD)`
- **Direct execution**: All scripts have shebangs - call them directly (e.g., `./core_agent_lines.sh`, NOT `bash core_agent_lines.sh`)

### Docker

```bash
# Build (REQUIRED after code changes)
docker build -t nanobot .

# Run Gateway
./run-docker.sh

# Helper scripts
./start-docker.sh
./stop-docker.sh
./restart-docker.sh
```

### Local Development

```bash
# Formatter & Linter (Mandatory before commit)
uv run ruff format .
uv run ruff check --fix .

# Run Tests
uv run pytest tests/

# Run specific test suite
uv run pytest tests/test_orchestration.py -v

# Monitor Project Size
./core_agent_lines.sh
```

## Development Workflow

- **Pre-commit REQUIRED**: Every commit MUST pass `ruff format`, `ruff check`, and `pytest`. 
- **NO Bypass**: Never use `--no-verify`.
- **KISS Principle**: Keep it simple. Prioritize text files over databases. No embeddings/vecdb/SQL in core.
- **Modular Growth**: Focus on modularity over strict line limits. Core is ~4,200 lines (as of 2026-02-14).
- **Observability First**: All agent actions must be logged with context for debugging and evolution.

## Coding Style
- Follow PEP 8
- Use type hints
- Keep modules focused and cohesive
- **Logging**: Use `logger.contextualize(task_id=..., session_key=...)` for consistent JSONL metadata
- **Async Patterns**: Subagents run via `asyncio.create_task`, use `asyncio.Queue` for mailboxes
- **Error Handling**: Graceful degradation, log failures to `FAILURES.md`
- **Formatting**: Ported `markdown-it` based Telegram formatter (HTML + Tables)

## Testing

### Test Suites
- `tests/test_orchestration.py`: Subagent spawn, message injection, cancellation, tiered models
- `tests/test_*.py`: Core functionality tests (70 total as of 2026-02-14)

### Running Tests
```bash
# All tests
uv run pytest tests/

# With coverage
uv run pytest tests/ --cov=nanobot

# Specific test
uv run pytest tests/test_orchestration.py::test_subagent_message_injection -v
```

## Configuration

### Configuration File Format
nanobot uses **YAML** format for configuration:
- `~/.nanobot/config.yaml` (recommended)
- `~/.nanobot/config.yml` (also supported)

**Why YAML over JSON:**
- ✅ Native comments
- ✅ Clean syntax (no quotes/commas)
- ✅ Multi-line strings
- ✅ Easy to grep (same snake_case as Python code!)
- ✅ Industry standard (Docker, K8s, CI/CD)

Copy `config.example.yaml` from the project root to get started.

### Tiered Models and Agent Configuration

Configure different models and parameters for different workloads:

#### Model Selection
- **`defaults.model`**: Baseline model for everything
- **`defaults.chat_model`**: Fast model for user interaction (overrides defaults.model)
- **`defaults.task_model`**: Powerful model for subagents (overrides defaults.model)
- **`main.model`**: Override for main agent (highest priority for chat)
- **`task.model`**: Override for task agents (highest priority for subagents)

#### Main Agent Parameters
- **`main.temperature`**: Creativity (0.0 = deterministic, 1.0+ = creative)
- **`main.max_tokens`**: Max response length
- **`main.max_tool_iterations`**: Safety limit to prevent loops
- **`main.memory_window`**: Context size (number of recent messages)
- **`main.consolidation_threshold`**: When to trigger memory consolidation (0.8 = at 80%)
- **`main.consolidation_keep_ratio`**: How much to keep (0.5 = keep 50% newest)

#### Task Agent Parameters
- **`task.temperature`**: Lower = focused, higher = exploratory
- **`task.max_tokens`**: Max response length for subagents
- **`task.max_iterations`**: Max loop iterations (higher = more complex workflows)
- **`task.max_completed_tasks`**: Registry cleanup threshold (prevents memory leaks)

Falls back hierarchy: `specific.model` → `defaults.{chat|task}_model` → `defaults.model`

### Example Config (`~/.nanobot/config.yaml`)
```yaml
providers:
  openrouter:
    api_key: sk-or-v1-xxx

agents:
  defaults:
    model: anthropic/claude-opus-4-5
    chat_model: anthropic/claude-sonnet-4
    task_model: anthropic/claude-opus-4-5
    workspace: ~/.nanobot/workspace
  
  main:
    max_tool_iterations: 20
    memory_window: 50
  
  task:
    max_iterations: 30
    max_completed_tasks: 100

logging:
  enabled: true
  level: INFO
  file_path: ~/.nanobot/logs/nanobot.jsonl
```

## Architecture Decisions

### Why File-Based Memory?
- **Simplicity**: No database setup, just text files
- **Portability**: Copy workspace, copy state
- **Debuggability**: Human-readable, grep-friendly
- **KISS**: Proven pattern from upstream

### Why Subagent Registry (not Database)?
- **In-memory**: Fast state access, no I/O overhead
- **Ephemeral**: Subagents are transient, state tracked only while running
- **Observable**: Full conversation history in `SubagentState.messages`
- **Modular**: Clean separation from main agent loop

### Why Mailbox Pattern?
- **Non-blocking**: Main agent never waits for subagent
- **Async-native**: Uses `asyncio.Queue` for thread-safe message injection
- **Interactive**: Supervisor can correct subagent mid-execution
- **Traceable**: All injected messages logged with `<SupervisorCorrection>` tags
