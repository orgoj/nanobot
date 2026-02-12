"""Simple TODO tool."""

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


class TodoTool(Tool):
    """Manage TODO tasks in memory/TODO.md."""

    name = "todo"
    description = "Manage tasks in memory/TODO.md. Actions: list, add, done, remove."
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "add", "done", "remove"]},
            "task": {"type": "string", "description": "Task description (for add)"},
            "index": {
                "type": "integer",
                "description": "Task index (for done, remove), starting from 1",
            },
        },
        "required": ["action"],
    }

    def __init__(self, workspace: Path):
        self.todo_file = workspace / "memory" / "TODO.md"

    async def execute(self, action: str, task: str = None, index: int = None, **kwargs: Any) -> str:
        if not self.todo_file.parent.exists():
            self.todo_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.todo_file.exists():
            self.todo_file.write_text("# TODO\n\n")

        lines = self.todo_file.read_text().splitlines()
        # Find lines that look like tasks
        task_indices = [i for i, line in enumerate(lines) if line.strip().startswith("- [")]

        if action == "list":
            if not task_indices:
                return "No tasks found in TODO.md."
            result = []
            for i, idx in enumerate(task_indices):
                result.append(f"{i + 1}. {lines[idx].strip()}")
            return "\n".join(result)

        if action == "add":
            if not task:
                return "Error: Task description required for 'add' action."
            new_line = f"- [ ] {task}"
            if lines and lines[-1].strip():
                lines.append(new_line)
            else:
                if not lines:
                    lines = ["# TODO", "", new_line]
                else:
                    lines[-1] = new_line
            self.todo_file.write_text("\n".join(lines) + "\n")
            return f"Added task: {task}"

        if action == "done" or action == "remove":
            if index is None or index < 1 or index > len(task_indices):
                return f"Error: Invalid task index {index}. Valid range: 1-{len(task_indices)}."

            line_idx = task_indices[index - 1]
            target_line = lines[line_idx]

            if action == "done":
                if "- [ ]" in target_line:
                    lines[line_idx] = target_line.replace("- [ ]", "- [x]", 1)
                    self.todo_file.write_text("\n".join(lines) + "\n")
                    return f"Marked as done: {target_line.strip()[6:]}"
                else:
                    return f"Task already completed: {target_line.strip()}"

            if action == "remove":
                removed_task = lines.pop(line_idx)
                self.todo_file.write_text("\n".join(lines) + "\n")
                return f"Removed task: {removed_task.strip()[6:]}"

        return "Error: Unknown action."
