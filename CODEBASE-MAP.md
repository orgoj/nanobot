# Codebase Map: nanobot (orgoj2)
> Ultra-lightweight AI agent framework | Tech: Python, LiteLLM, JSONL logs | Generated: 2026-02-14

## Architecture
nanobot is a minimalist, event-driven agent framework. It routes messages from various channels (Telegram, Discord, etc.) via a central `MessageBus` to an `AgentLoop`. The loop uses LiteLLM for multi-provider interaction and maintains a KISS (Keep It Simple, Stupid) file-based memory system (`MEMORY.md`, `HISTORY.md`). Structured logs are saved in JSONL format for easy analysis.

## Module Index
| Directory | Purpose | Key Files | Depends On |
|-----------|---------|-----------|------------|
| `nanobot/agent/` | Core agent execution loop and context management | `loop.py`, `context.py`, `skills.py` | `nanobot/bus/`, `nanobot/providers/` |
| `nanobot/channels/` | Platform integrations for messaging | `manager.py`, `telegram.py`, `slack.py` | `nanobot/bus/` |
| `nanobot/bus/` | Internal asynchronous event bus | `queue.py`, `events.py` | N/A |
| `nanobot/cli/` | Command-line interface and onboarding | `commands.py` | `nanobot/agent/`, `nanobot/config/` |
| `nanobot/config/` | Pydantic-based configuration | `loader.py`, `schema.py` | N/A |
| `nanobot/providers/` | Unified LLM provider interface via LiteLLM | `litellm_provider.py` | `nanobot/config/` |
| `nanobot/utils/` | Shared utilities (logging, formatting) | `logging.py`, `telegram_markdown.py` | N/A |
| `nanobot/skills/` | Built-in capabilities (tools) | `zai_web.py`, `prompt-refactor/` | N/A |

## Entry Points & Config
- `nanobot.cli.commands:app` - Main CLI entry point
- `~/.nanobot/config.json` - User configuration
- `~/.nanobot/logs/nanobot.jsonl` - Structured JSONL logs
- `~/.nanobot/workspace/` - Agent's local storage

## Patterns & Conventions
- **Error Handling**: Uses `loguru` for logging; errors are reported back to users via channels.
- **Logging**: Structured JSONL format (PIMONO style) for automated analysis.
- **Memory**: Purely file-based (`MEMORY.md`, `HISTORY.md`, `FAILURES.md`).
- **KISS Principles**: Minimize dependencies, prioritize text files over complex databases.

## File Index
| File | Role |
|------|------|
| `nanobot/agent/loop.py` | Core orchestration of context, LLM, and tool execution |
| `nanobot/agent/context.py` | Assembles system prompts with time awareness and failure logs |
| `nanobot/utils/logging.py` | Implements structured JSONL logging with context |
| `nanobot/agent/tools/zai_web.py` | KISS web search and fetch using official MCP SDK |
| `nanobot/utils/telegram_markdown.py` | Robust Telegram HTML formatter with ASCII tables |
| `nanobot/channels/telegram.py` | Telegram bot implementation with HTML support |
| `nanobot/skills/prompt-refactor/SKILL.md` | Skill for upgrading existing bots to KISS prompts |
