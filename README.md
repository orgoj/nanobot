<div align="center">
  <img src="nanobot_logo.png" alt="nanobot" width="500">
  <h1>nanobot: Ultra-Lightweight Personal AI Assistant</h1>
  <p>
    <a href="https://pypi.org/project/nanobot-ai/"><img src="https://img.shields.io/pypi/v/nanobot-ai" alt="PyPI"></a>
    <a href="https://pepy.tech/project/nanobot-ai"><img src="https://static.pepy.tech/badge/nanobot-ai" alt="Downloads"></a>
    <img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <a href="./COMMUNICATION.md"><img src="https://img.shields.io/badge/Feishu-Group-E9DBFC?style=flat&logo=feishu&logoColor=white" alt="Feishu"></a>
    <a href="./COMMUNICATION.md"><img src="https://img.shields.io/badge/WeChat-Group-C5EAB4?style=flat&logo=wechat&logoColor=white" alt="WeChat"></a>
    <a href="https://discord.gg/MnCvHqpUGB"><img src="https://img.shields.io/badge/Discord-Community-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"></a>
  </p>
</div>

🐈 **nanobot** is an **ultra-lightweight** personal AI assistant inspired by [OpenClaw](https://github.com/openclaw/openclaw).

⚡️ Delivers core agent functionality in just **~17,000** lines of code — **96% smaller** than Clawdbot's 430k+ lines.

📏 Real-time line count: **3,562 lines** (run `bash core_agent_lines.sh` to verify anytime)

## 📢 News

- **2026-02-13** 📤 **Telegram MarkdownV2 Support** — Added robust Markdown converter with automatic escapement for Telegram.
- **2026-02-12** 🧠 **Redesigned memory system** — Integrated production-hardened TurboMemoryStore with SQLite, knowledge graphs, and semantic search!
- **2026-02-12** 🛠️ **Integrated advanced features** from useful forks (`bot2046`, `MTAAP`, `Kirayu173`, `ls1816`): Parallel Tool Execution, Auto-continuation, Loop Guard, and Streaming.
- **2026-02-11** 🔐 **Security & UX** — Added secret sanitizer, interactive configuration wizard, and skill security scanner.
- **2026-02-10** 🧬 **Evolutionary mode** — Bots can now self-improve while maintaining security boundaries!
- **2026-02-09** 🎯 **Enhanced Smart Routing** with CODING tier and per-tier secondary models.
- **2026-02-09** 💬 Added Slack, Email, and QQ support.

## Key Features

🪶 **Ultra-Lightweight**: Minimal code footprint, fast startup, and low resource usage.

🧠 **Production-Hardened Memory**: SQLite-based knowledge graph, semantic search, and intelligent context compaction.

🔒 **Comprehensive Security**: Automatic skill security scanning and secret sanitization to protect your credentials.

🎯 **Smart Routing**: Multi-tier model selection to save costs (up to 96%) while maintaining high quality.

💎 **Easy-to-Use**: Step-by-step onboarding wizard and interactive configuration.

## 🏗️ Architecture

<p align="center">
  <img src="nanobot_arch.png" alt="nanobot architecture" width="800">
</p>

## 🧠 Memory System

nanobot features a **production-hardened memory system** (TurboMemory) inspired by OpenClaw's battle-tested architecture.

### Core Capabilities
| Feature | Description |
|---------|-------------|
| **📊 Event Logging** | Every interaction stored in SQLite with WAL mode for reliability |
| **🔍 Semantic Search** | BGE embeddings enable finding relevant past conversations |
| **🕸️ Knowledge Graph** | Entities, relationships, and facts extracted automatically |
| **📝 Hierarchical Summaries** | Multi-level summaries for efficient context assembly |

### Context Compaction
Handles long conversations without losing context or breaking tool chains:
- **Token-Aware Counting**: Accurate tiktoken-based counting.
- **Tool Chain Preservation**: Never separates `tool_use` → `tool_result` pairs.
- **Proactive Trigger**: Compacts at 80% threshold.

## 🔒 Security

nanobot includes a **comprehensive security layer** to protect users from malicious skills.

### Skill Security Scanner
Automatically scans all skills for dangerous patterns:
- 🚫 **Critical**: Credential theft, malware indicators.
- ⚠️ **High**: `curl | bash`, sudo escalation.

### Secret Sanitizer 🔐
Automatically detects and masks sensitive information (API keys, passwords, tokens) before sending to LLMs or writing to logs.

## 📦 Install

```bash
git clone https://github.com/HKUDS/nanobot.git
cd nanobot
pip install -e .
```

To enable full memory features (local embeddings and entity extraction):
```bash
pip install -e ".[memory]"
```

## 🚀 Quick Start

**1. Initialize & Configure**

```bash
nanobot onboard
```

**2. Chat**

```bash
nanobot agent -m "Hello!"
```

## 💬 Chat Apps

nanobot supports: Telegram, Discord, WhatsApp, Feishu, Mochat, DingTalk, Slack, Email, and QQ.

Run `nanobot gateway` after configuring your preferred channel in `~/.nanobot/config.json`.

## 🧠 Advanced Agentic Features

Recently integrated advanced logic from community forks:
- **Loop Guard** (`ls1816`): Prevents infinite tool-calling loops.
- **Parallel Tool Execution** (`MTAAP`): Runs independent tool calls concurrently using `asyncio.gather`.
- **Auto-continuation** (`MTAAP`): Automatically prompts "Continue" on truncation.
- **Accountability Journaling** (`pyrevo`): Enforces recording actions in daily memory files.

## 🌐 Web Tools Configuration

Nanobot supports multiple providers for web search and content fetching.

### Search Providers
- **Brave Search** (default): Uses Brave Search API. Requires `BRAVE_API_KEY`.
- **Z.AI Search**: Uses Z.AI MCP via HTTP. Requires `Z_AI_API_KEY`.

### Fetch Providers
- **Readability** (default): Uses `readability-lxml` to extract content.
- **Z.AI Web Reader**: Uses Z.AI MCP via HTTP. Requires `Z_AI_API_KEY`.

### Configuration Example
To use Z.AI tools, update your `config.json`:

```json
{
  "tools": {
    "web": {
      "search": {
        "provider": "zai",
        "zai_api_key": "your-key-here",
        "max_results": 5
      },
      "fetch": {
        "provider": "zai",
        "zai_api_key": "your-key-here",
        "max_chars": 50000
      }
    }
  }
}
```

You can also set `Z_AI_API_KEY` environment variable instead of putting it in config.

## 🧪 Testing

nanobot uses `pytest` for testing. You can run tests locally or in an isolated Docker container.

### Local Testing
```bash
uv run pytest tests/
```

### Docker Testing (Isolated)
Run tests in a clean, isolated environment without affecting your local system. This method uses `Dockerfile.test` to ensure all dependencies are correctly installed.

```bash
./test-docker.sh
```

---
<sub>nanobot is for educational, research, and technical exchange purposes only</sub>
