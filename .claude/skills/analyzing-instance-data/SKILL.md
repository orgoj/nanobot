---
name: analyzing-instance-data
description: "This skill should be used when the user asks to analyze the live agent's state, logs, or workspace from the instance directory. Use it to diagnose failures, evaluate prompt performance, and plan upgrades."
---

# Analyzing Instance Data

This skill provides a workflow for inspecting the "live" state of a nanobot instance located in the `instance/` directory. This data is a snapshot of an active agent and should be used for diagnostic and planning purposes.

## CRITICAL: READ-ONLY ACCESS (Snapshots Only)

**DO NOT MODIFY** any files in `/home/michael/projects/nanobot/instance/nanobotnb/.nanobot/` directly with the expectation of persistence.
These files are **snapshots** synchronized from the running instance. Any changes made here **will be overwritten** during the next sync from the source.

### PROPER WORKFLOW FOR CHANGES:
If you need to update agent behavior, prompts, or configuration:
1.  **Update the source** in the main project directories:
    - Code/Logic: `nanobot/`
    - Global Prompts: `nanobot/agent/prompts/` (or wherever defined in the code)
    - Config Templates: `config.example.yaml`
    - Workspace Baseline: `workspace/` (including `AGENTS.md`, `HEARTBEAT.md`, etc.)
2.  **Deploy changes** to the instance (e.g., via `ru sync`, git push/pull, or the deployment script).
3.  **Emergency Live Edits**: If you *must* make an emergency fix directly on the live instance to stop a loop (like double reporting), you **MUST** immediately mirror those exact changes back to the source files in `nanobot/workspace/` or `nanobot/skills/` to prevent them from being lost.

Use the insights gained from instance data to:
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

## Diagnostic & Action Protocol

1. **Check Failures**: Start with `FAILURES.md` to see what went wrong from the agent's perspective.
2. **Trace Logs**: Use the `task_id` from a failure to grep through `nanobot.jsonl` for the full context.
3. **Analyze Root Cause**: Determine if it's a **Code Bug** or an **Agent Logic/Config** issue.

### How to Apply Fixes:

- **If it's a CODE BUG**: Fix the logic in `nanobot/` (source code).
- **If it's a SYSTEMIC PROMPT issue**: Create an upgrade script or update the global templates in `nanobot/`.
- **If it's an AGENT-SPECIFIC issue (logic/config/prompts)**: 
    - **DO NOT** modify the source files in `workspace/` or `skills/` of this project.
    - **DO NOT** perform "emergency live edits" on the instance unless explicitly asked for a quick fix that doesn't need to be systemic.
    - **REPORT** the finding to the USER. The user or the agent itself will handle the correction within that specific instance.
    - An agent is responsible for its own self-improvement and fixing its local workspace.

**CRITICAL**: Modifications to `workspace/` or `skills/` in this repository act as a baseline for *new* or *synced* instances. Changing them here to fix a single bot's mistake can cause regressions or overwrite unique logic in other bots.
