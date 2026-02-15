# Codebase Map: nanobot
> Ultra-lightweight AI agent framework with subagent orchestration | Tech: Python, LiteLLM, YAML, JSONL logs | Generated: 2026-02-15

## Architecture
nanobot is a minimalist, event-driven agent framework built on a "KISS" (Keep It Simple, Stupid) philosophy. It routes messages from multi-platform chat channels (Telegram, Discord, Slack, etc.) via an asynchronous `MessageBus` to the `AgentLoop`. The system supports tiered models (fast for chat, powerful for tasks) and interactive subagent orchestration using a mailbox pattern for background guidance. Memory is strictly file-based (`MEMORY.md`, `HISTORY.md`), and observability is provided through structured JSONL logging.

## Module Index
| Directory | Purpose | Key Files | Depends On |
|-----------|---------|-----------|------------|
| `nanobot/agent/` | Core orchestration: loop, subagent management, and memory | `loop.py`, `subagent.py`, `memory.py` | `nanobot/bus/`, `nanobot/providers/` |
| `nanobot/agent/tools/` | Built-in capabilities: FileSystem, Shell, Web, Subagent Control | `subagent.py`, `shell.py`, `web.py` | `nanobot/agent/` |
| `nanobot/channels/` | Multi-platform chat integrations (adapters) | `manager.py`, `telegram.py`, `discord.py` | `nanobot/bus/` |
| `nanobot/bus/` | Internal asynchronous event routing | `queue.py`, `events.py` | N/A |
| `nanobot/config/` | YAML-based configuration with Pydantic validation | `schema.py`, `loader.py` | N/A |
| `nanobot/providers/` | LLM provider registry and unified LiteLLM interface | `registry.py`, `litellm_provider.py` | `nanobot/config/` |
| `nanobot/session/` | Conversation history and state management | `manager.py` | `nanobot/agent/` |
| `nanobot/cron/` | Scheduled task service (cron-like) | `service.py` | `nanobot/bus/` |
| `nanobot/skills/` | Bundled agent capabilities (plugins) | `github/`, `weather/`, `tmux/` | N/A |
| `bridge/` | TypeScript-based WhatsApp bridge | `src/server.ts`, `package.json` | N/A |

## Entry Points & Config
- `nanobot.cli.commands:app` - Main CLI entry point (via `__main__.py`)
- `~/.nanobot/config.yaml` - Primary user configuration (YAML)
- `~/.nanobot/logs/nanobot.jsonl` - Structured JSONL logs
- `~/.nanobot/workspace/` - Default agent storage (memory, sandboxes)
- `nanobot.sh` - Development entry point

## Patterns & Conventions
- **Tiered Models**: Optimized model selection (chat_model vs task_model) based on workload.
- **Subagent Mailbox**: Supervisors inject guidance into running subagents via `asyncio.Queue`.
- **KISS Memory**: Purely file-based storage; periodic consolidation summarizes history into text files.
- **Structured Logging**: Uses `loguru.contextualize` for consistent metadata across agent/subagent boundaries.
- **Async-First**: Core loop and channel communication are fully asynchronous.

## File Index
| File | Role |
|------|------|
| `nanobot/__main__.py` | Application entry point and CLI command mapping |
| `nanobot/agent/loop.py` | Main processing engine handling chat flow and tool iterations |
| `nanobot/agent/subagent.py` | Manager for background tasks with state tracking and mailbox support |
| `nanobot/agent/context.py` | Constructs dynamic system prompts with history and subagent awareness |
| `nanobot/agent/memory.py` | Handles reading/writing persistent memory to markdown files |
| `nanobot/agent/tools/subagent.py` | Tools exposed to the agent for spawning and managing subagents |
| `nanobot/bus/queue.py` | Core `asyncio` message broker for internal event distribution |
| `nanobot/bus/events.py` | Data classes for Inbound and Outbound message routing |
| `nanobot/channels/manager.py` | Central registry and lifecycle manager for all chat channels |
| `nanobot/config/schema.py` | Pydantic schema defining the validated configuration structure |
| `nanobot/config/loader.py` | Loads YAML config with environment variable expansion |
| `nanobot/providers/registry.py` | Source of truth for supported LLM providers and model matching |
| `nanobot/providers/litellm_provider.py` | Unified LLM interface wrapping LiteLLM for multi-provider support |
| `nanobot/session/manager.py` | Manages active conversation sessions and their persistence |
| `nanobot/utils/logging.py` | Structured JSONL logger configuration (PIMONO style) |
| `nanobot/utils/telegram_markdown.py` | Robust formatter for Telegram-compatible HTML and tables |
| `nanobot/cron/service.py` | Implements scheduled message execution |
| `nanobot/heartbeat/service.py` | Periodic proactive agent wake-up service |
| `bridge/src/server.ts` | Node.js bridge for linking WhatsApp via socket.io |
| `scripts/manual_zai_integration.py` | Manual integration test for network-dependent ZAI tools |
| `workspace/memory/MEMORY.md` | Persistent long-term memory file for the agent |
