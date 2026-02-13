# Codebase Map: nanobot
> Lightweight personal AI assistant framework | Tech: Python, TypeScript, Docker | Generated: 2026-02-13

## Architecture
Nanobot is a modular AI agent system with a decoupled architecture. The **Python Core** (`nanobot/`) manages the central `AgentLoop`, tool execution, and the "Turbo Memory" semantic storage. A **TypeScript Bridge** (`bridge/`) provides high-concurrency connectivity for WhatsApp using the Baileys library. The system uses an internal **Message Bus** (`nanobot/bus/`) to route events between the core, the bridges, and various communication channels. The agent's identity and operational state are externalized in the `workspace/` directory, allowing for dynamic personality and capability updates without code changes.

## Module Index
| Directory | Purpose | Key Files | Depends On |
|-----------|---------|-----------|------------|
| `nanobot/agent/` | Core orchestration and tool management | `loop.py`, `subagent.py`, `context.py` | `nanobot/bus/`, `nanobot/memory/` |
| `nanobot/memory/` | Turbo Memory system (RAG, entities, summaries) | `store.py`, `retrieval.py`, `summaries.py` | `nanobot/config/` |
| `nanobot/bus/` | Async message routing between components | `queue.py`, `events.py` | - |
| `bridge/` | WhatsApp connectivity bridge (Node.js/TS) | `src/whatsapp.ts`, `src/server.ts` | - |
| `workspace/` | Agent personality, tools, and user data | `SOUL.md`, `TOOLS.md`, `USER.md` | - |
| `nanobot/channels/` | Multi-platform messaging adapters | `manager.py`, `telegram.py`, `discord.py` | `nanobot/bus/` |
| `nanobot/cli/` | Command-line interface and setup | `commands.py`, `configure.py` | `nanobot/agent/` |
| `nanobot/providers/` | Unified LLM API abstraction (LiteLLM) | `litellm_provider.py`, `registry.py` | - |
| `instance/` | Docker environment orchestration & symlinks | `README.md`, `config.sh.example` | Dockerfile |
| `tests/` | Multi-layer testing (unit, router, integration) | `run_tests.py`, `test_docker.sh` | `nanobot/` |

## Entry Points & Config
- `nanobot/__main__.py` - Python application entry point
- `bridge/src/index.ts` - WhatsApp bridge entry point
- `nanobot.sh` - Host-side CLI wrapper
- `run-docker.sh` - Primary Docker orchestration script
- `config.example.json` - Global system configuration template
- `workspace/SOUL.md` - Agent personality and behavior definition

## Patterns & Conventions
- **Hybrid Stack**: Python for AI/Reasoning; TypeScript for socket-heavy messaging bridges.
- **Bus-Driven**: Components communicate via async events, enabling easy addition of new channels.
- **Turbo Memory**: Uses a combination of event logging, entity extraction, and periodic summary refreshing.
- **Containerization**: Everything is designed to run in Docker, with host-to-container mapping via `instance/`.
- **Smart Routing**: Multi-tier model selection based on task complexity (SIMPLE -> CODING -> REASONING).

## File Index
| File | Role |
|------|------|
| `nanobot/agent/loop.py` | The main execution engine managing the think-act-respond loop. |
| `nanobot/agent/router/llm_router.py` | Classifies user intent to select the most cost-effective LLM model. |
| `nanobot/bus/queue.py` | Asyncio-based internal message queue for system-wide events. |
| `nanobot/memory/store.py` | Persistent storage interface for entities, events, and relationships. |
| `nanobot/memory/summaries.py` | Logic for aggregating and refreshing entity-based long-term memory. |
| `bridge/src/whatsapp.ts` | Implements the WhatsApp protocol bridge using Baileys. |
| `bridge/src/server.ts` | WebSocket server for bridge-to-core communication. |
| `workspace/SOUL.md` | Core instructions defining the agent's persona and ethical bounds. |
| `workspace/TOOLS.md` | Documentation and configuration for the agent's available capabilities. |
| `nanobot/channels/manager.py` | Life-cycle manager for active messaging platform integrations. |
| `nanobot/agent/tools/registry.py` | Registry for dynamic tool discovery and execution. |
| `nanobot/cron/service.py` | Background service for scheduled tasks and proactive notifications. |
| `instance/README.md` | Documentation for the "instance" symlink pattern used in Docker. |
| `scripts/migrate-data-to-bot.sh` | Utility for importing existing data into the bot's workspace. |
| `tests/test_docker.sh` | Integration test suite runner within the Docker environment. |
| `pyproject.toml` | Python project metadata, dependencies, and CLI entry points. |
