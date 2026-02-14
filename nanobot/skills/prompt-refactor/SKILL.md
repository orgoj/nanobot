---
name: prompt-refactor
description: Refactor agent system prompts using KISS principles. Removes complexity, adds time awareness, makes prompts portable. Use when agent has timing issues, over-complicated memory, or needs clean portable prompts.
---

# Prompt Refactor

Refactors agent prompts to be simple, accurate, and portable.

## What This Does

1. Adds time awareness (prevents duration hallucination)
2. Simplifies memory to file-based (MEM.md + grep)
3. Removes over-engineering
4. Makes prompts portable across agents

## Files to Refactor

### Primary Files
- `SYSTEM.md` or system prompt
- `SOUL.md` (personality)
- `USER.md` (user preferences)
- `MEMORY.md` (knowledge base)

### Check These
- Skill files (`skills/*/SKILL.md`)
- Channel configs (if they contain prompt text)

## Refactor Process

### Step 1: Audit Current State

Read all prompt files and identify:
- Time-related issues (missing timestamps, duration guesses)
- Over-complicated memory (vectors, embeddings, databases)
- Redundant information
- Non-portable elements (hardcoded paths, specific tools)

### Step 2: Add Time Awareness

Add to system prompt:

```markdown
## Current Time
- Now: [will be injected at runtime]
- Session started: [timestamp]
- Duration: [calculated, never guessed]
```

**Critical**: Agent must NEVER calculate or guess time without actual data.

### Step 3: Simplify Memory

**Remove**:
```markdown
❌ Vector databases
❌ Embeddings
❌ RAG pipelines
❌ Complex memory classes
```

**Keep**:
```markdown
✅ MEM.md (text file)
✅ Daily notes (YYYY-MM-DD.md)
✅ grep for search
```

### Step 4: Apply KISS Principles

For each file:
1. Remove explanations of what agent already knows
2. Remove duplicate information
3. Keep only essential context
4. Use examples instead of long descriptions

### Step 5: Make Portable

Ensure prompts work on:
- Different agents (Claude, GPT, etc.)
- Different systems (Linux, Mac, Windows)
- Different timezones

Remove:
- Hardcoded paths (use `$WORKSPACE` variable)
- Agent-specific features (unless critical)
- System-dependent tools

## Output Format

After refactoring, output:

```markdown
# Refactored: [filename]

## Changes Made
- [change 1]
- [change 2]

## File Size
- Before: X bytes
- After: Y bytes
- Reduction: Z%
```

## Validation Checklist

- [ ] Time awareness added
- [ ] Memory simplified to files
- [ ] No vector/embedding references
- [ ] No hardcoded paths
- [ ] Under 5,000 words per file
- [ ] Works on any agent
- [ ] Tested with grep search

## Example Refactor

**Before**:
```markdown
## Memory System
Uses vector embeddings with OpenAI API...
[50 lines of complex setup]
```

**After**:
```markdown
## Memory
- Read: `memory/MEMORY.md`
- Search: `grep -r "topic" memory/`
```

---

**Remember**: Less is more. When in doubt, delete.
