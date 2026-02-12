# Architecture: Messaging & Prompts

> How nanobot handles messages, channels, and context.

## System Prompt Assembly

The system prompt is built in layers (order matters):

```
┌─────────────────────────────────────┐
│ 1. Identity & Runtime               │  <- Time, OS, workspace path
├─────────────────────────────────────┤
│ 2. Conditional Features             │  <- Multi-agent, journaling (if enabled)
├─────────────────────────────────────┤
│ 3. Bootstrap Files                  │  <- AGENTS.md, SOUL.md, USER.md, etc.
├─────────────────────────────────────┤
│ 4. Memory Context                   │  <- MEMORY.md + recent daily notes
├─────────────────────────────────────┤
│ 5. Skills Summary                   │  <- Available skills list
├─────────────────────────────────────┤
│ 6. Current Session                  │  <- Channel, chat_id, sender_id
└─────────────────────────────────────┘
```

### Bootstrap Files (workspace)

| File | Purpose |
|------|---------|
| `AGENTS.md` | Instructions, behavior rules, multi-agent orchestration |
| `SOUL.md` | Personality, values, tone |
| `USER.md` | User preferences, context |
| `TOOLS.md` | Tool usage guidelines |
| `IDENTITY.md` | Additional identity info |

## Message Flow Architecture

### Normal Conversation Flow

```
User (Telegram) → ChannelManager → MessageBus → AgentLoop → LLM → Tool Execution → Response
                                        ↓
                              ┌─────────────────────────────────┐
                              │ OutboundMessage(channel, chat_id)│
                              └─────────────────────────────────┘
                                        ↓
                              ChannelManager → User (Telegram)
```

### Key Components

1. **ChannelManager** - Routes messages to/from platforms (Telegram, Discord, etc.)
2. **MessageBus** - Internal event queue (inbound/outbound)
3. **AgentLoop** - Core processing engine
4. **ToolRegistry** - Available tools for the agent

## Channel Context

### What is `channel` and `chat_id`?

Every message has context:

```python
channel: str    # Platform: "telegram", "discord", "cli", etc.
chat_id: str    # Conversation ID: user ID, group ID, etc.
sender_id: str  # Who sent the message
```

### How Context is Used

1. **For Agent Awareness** - Agent knows where it's responding
2. **For Tool Routing** - Tools like `message` use context to send replies
3. **For Session Management** - Sessions are keyed by `channel:chat_id`

## The `message` Tool

### Purpose

Send a message to the user **during** agent execution (before final response).

### When to Use

✅ **CORRECT usage:**
- Proactive notifications
- Progress updates
- Multiple messages in one task
- Explicit user communication

❌ **WRONG usage:**
- Final response (agent's natural response handles this)
- Echoing what you're going to do

### Example

```python
# Agent wants to send "Working on it..."
{
  "tool": "message",
  "arguments": {
    "content": "Working on it... I'll check the files.",
    "channel": "telegram",  # Optional, uses context
    "chat_id": "7221629441" # Optional, uses context
  }
}
```

## Special Execution Modes

### Startup Prompt

**Purpose:** Execute a task when gateway starts.

```json
{
  "agents": {
    "defaults": {
      "startup_prompt": "Send Hello, on channels.",
      "startup_target": "telegram:7221629441"
    }
  }
}
```

**Flow:**
1. Agent receives prompt with `channel="telegram"` context
2. Agent uses `message` tool to send "Hello! 👋"
3. **Final response goes to logs only** - NOT to channel
4. User sees: "Hello! 👋" (via message tool)

**Why final response doesn't go to channel:**
- Startup is internal operation
- Agent already communicated via `message` tool
- Avoids duplicate messages

### Heartbeat

**Purpose:** Periodic background tasks.

```json
{
  "agents": {
    "defaults": {
      "heartbeat_on_start": true,
      "heartbeat_target": "telegram:7221629441"
    }
  }
}
```

**Flow:**
1. Every N minutes, agent reads `HEARTBEAT.md`
2. If tasks exist, agent executes them
3. Agent uses `message` tool if user notification needed
4. **Final response goes to logs only**

### Cron Jobs

**Purpose:** Scheduled tasks.

```bash
nanobot cron add -n "morning" -m "Good morning!" --cron "0 9 * * *"
```

**Flow:**
1. At scheduled time, agent receives message
2. If `--deliver` flag set, response goes to channel
3. Otherwise, response to logs

## Tool Execution

### Parallel Execution

Multiple independent tool calls run concurrently:

```python
# Agent requests:
read_file("a.txt")
read_file("b.txt")  
read_file("c.txt")

# Executes in parallel via asyncio.gather()
```

### Sequential Execution

Tools can be chained:

```python
read_file("data.json") 
→ parse result
→ write_file("output.txt")
```

## Response Routing

### Where Do Responses Go?

| Scenario | Final Response | Message Tool |
|----------|---------------|--------------|
| Normal chat (Telegram) | To channel | To channel |
| Startup prompt | **Logs only** | To channel |
| Heartbeat | **Logs only** | To channel |
| Cron (no --deliver) | **Logs only** | To channel |
| Cron (--deliver) | To channel | To channel |

### Why This Matters

- **Startup/Heartbeat** are *internal* operations
- Agent uses `message` tool for intentional user communication
- Final response is just "confirmation" → logs
- Prevents duplicate messages

## Best Practices

### For Agent Behavior (AGENTS.md)

```markdown
# Communication Guidelines

1. **Use message tool for:**
   - Progress updates during long tasks
   - Proactive notifications
   - Multi-step task communication

2. **Don't use message tool for:**
   - Final responses (just respond naturally)
   - Echoing intentions (just do it)

3. **Be context-aware:**
   - Know which channel you're on
   - Adapt tone to platform
   - Use appropriate formatting
```

### For Configuration

```json
{
  "agents": {
    "defaults": {
      "startup_prompt": "Send greeting to users",
      "startup_target": "telegram:123456",
      "heartbeat_on_start": true,
      "heartbeat_target": "cli:direct"
    }
  }
}
```

## Debugging

### Check logs:
```bash
tail -f instance/workspace/logs/nanobot.log
```

### Look for:
- `Tool call: message(...)` - Agent using message tool
- `Response to telegram:user: ...` - Final response
- `OutboundMessage` - Messages sent to channels

### Common Issues:

1. **Duplicate messages** - Agent using message tool AND final response going to channel
2. **No response** - Check if message tool was used vs. final response
3. **Wrong channel** - Check channel context in logs
