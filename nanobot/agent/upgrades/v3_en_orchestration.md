# Migration: Perfect Orchestration V3

This is an automatic upgrade to your Nanobot instructions and configuration.

## Task 1: Increase Line Limits
Update `AGENTS.md` and `HEARTBEAT.md` rules:
- `MEMORY.md` is now allowed to be up to 500 lines.
- `HEARTBEAT.md` is now allowed to be up to 100 lines.
- Update the relevant sections in both files to reflect these new limits.

## Task 2: Update Project Management Skill
Update `skills/project-management/SKILL.md`:
- Add a rule: "When spawning a subagent for a project in `workspace/projects/`, ALWAYS specify the `working_dir` parameter as an absolute path."
- Add a 'Liveness Check' to the Heartbeat workflow: "If a subagent has been running for >10 minutes, use `subagent_history` to check progress. If it is stuck in a loop of tool errors, send a `subagent_message` to correct it or stop it."

## Task 3: Git Hygiene
Add `workspace/projects/*` to the `.gitignore` file in your root configuration directory (`~/.nanobot/.gitignore`). This prevents nested git repository issues while keeping your core nanobot files (soul, skills, memory) versioned.

## Task 4: English Enforcement
Ensure that all system instructions and skill documentation are strictly in English. If you find any Czech text in `AGENTS.md`, `HEARTBEAT.md`, or `skills/`, translate it to English immediately. All subagent tasks must also be assigned in English.

**Execution:**
Use your tools (`read_file`, `edit_file`, `write_file`, `exec`) to perform these updates across your workspace. Verify the changes after editing.
