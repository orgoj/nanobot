---
name: analyzing-instance-data
description: "This skill should be used when the user asks to analyze the live agent's state, logs, or workspace from the instance directory. Use it to diagnose failures, evaluate prompt performance, and plan upgrades."
---

# Analyzing Instance Data

This skill provides a workflow for inspecting the "live" state of a nanobot instance located in the `instance/` directory. This data is a snapshot of an active agent and should be used for diagnostic and planning purposes.

## CRITICAL: READ-ONLY ACCESS

**DO NOT MODIFY** any files in `/home/michael/projects/nanobot/instance/nanobotnb/.nanobot/`.
These files are managed by the running instance or synchronized from other sources. Any changes made here will likely be overwritten.

Use the insights gained from this analysis to:
1. Update source code in `nanobot/`.
2. Update system prompts in `nanobot/agent/prompts/`.
3. Update configuration templates like `config.example.yaml`.
4. Plan and implement new features or bug fixes.

## Key Data Locations

- **Bootstrap Files**: `/home/michael/projects/nanobot/instance/nanobotnb/.nanobot/workspace/`
  - `AGENTS.md`: Multi-agent project context.
  - `SOUL.md`: Behavioral guidelines and persona.
  - `USER.md`: Information about the user.
  - `TOOLS.md`: Documentation of available tools.
  - `IDENTITY.md`: Core identity definition.
  - `HEARTBEAT.md`: Periodic tasks and instructions.
- **Workspace Memory**: `/home/michael/projects/nanobot/instance/nanobotnb/.nanobot/workspace/memory/`
  - `MEMORY.md`: Long-term facts and preferences.
  - `HISTORY.md`: Session logs and past events.
- **Failures**: `/home/michael/projects/nanobot/instance/nanobotnb/.nanobot/workspace/FAILURES.md`
  - Critical log of agent self-reported failures.
- **Logs**: `/home/michael/projects/nanobot/instance/nanobotnb/.nanobot/logs/nanobot.jsonl`
  - Contains structured JSONL logs with `task_id` and `session_key`.
- **Sessions**: `/home/michael/projects/nanobot/instance/nanobotnb/.nanobot/sessions/`
  - Raw session data and message history.

## Diagnostic Workflow

1. **Check Failures**: Start with `FAILURES.md` to see what went wrong from the agent's perspective.
2. **Trace Logs**: Use the `task_id` from a failure to grep through `nanobot.jsonl` for the full context.
3. **Inspect Context**: Look at the files in `workspace/memory/` to understand why the agent made certain decisions.
4. **Propose Fixes**: Map the failures to specific logic in `nanobot/` or instructions in prompts.
