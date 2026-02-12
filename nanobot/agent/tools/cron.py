"""Tool for managing scheduled jobs."""

from typing import TYPE_CHECKING, Any

from nanobot.agent.tools.base import Tool
from nanobot.cron.types import CronSchedule

if TYPE_CHECKING:
    from nanobot.cron.service import CronService


class CronTool(Tool):
    """Tool to manage scheduled jobs."""

    def __init__(self, cron_service: "CronService"):
        self._cron = cron_service
        self._channel = None
        self._chat_id = None

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the delivery context for new jobs."""
        self._channel = channel
        self._chat_id = chat_id

    @property
    def name(self) -> str:
        return "cron"

    @property
    def description(self) -> str:
        return (
            "Schedule background tasks or reminders. "
            "Supports periodic execution (every X seconds), "
            "cron expressions ('0 9 * * *'), or one-time 'at' datetime."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "remove"],
                    "description": "The action to perform.",
                },
                "message": {
                    "type": "string",
                    "description": "The message to send/process when the job runs.",
                },
                "every_seconds": {
                    "type": "integer",
                    "description": "Execution interval in seconds.",
                },
                "cron_expr": {
                    "type": "string",
                    "description": "Cron expression like '0 9 * * *' (for scheduled tasks)",
                },
                "at": {
                    "type": "string",
                    "description": "ISO datetime for one-time execution (e.g. '2026-02-12T10:30:00')",
                },
                "job_id": {"type": "string", "description": "Job ID (for remove)"},
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        message: str = "",
        every_seconds: int | None = None,
        cron_expr: str | None = None,
        at: str | None = None,
        job_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        if action == "add":
            return self._add_job(message, every_seconds, cron_expr, at)
        elif action == "list":
            return self._list_jobs()
        elif action == "remove":
            return self._remove_job(job_id)
        return f"Unknown action: {action}"

    def _add_job(
        self,
        message: str,
        every_seconds: int | None,
        cron_expr: str | None,
        at: str | None,
    ) -> str:
        if not message:
            return "Error: message is required for add"
        if not self._channel or not self._chat_id:
            return "Error: no session context (channel/chat_id)"

        # Build schedule
        delete_after = False
        if every_seconds:
            schedule = CronSchedule(kind="every", every_ms=every_seconds * 1000)
        elif cron_expr:
            schedule = CronSchedule(kind="cron", expr=cron_expr)
        elif at:
            from datetime import datetime

            dt = datetime.fromisoformat(at)
            at_ms = int(dt.timestamp() * 1000)
            schedule = CronSchedule(kind="at", at_ms=at_ms)
            delete_after = True
        else:
            return "Error: either every_seconds, cron_expr, or at is required"

        job = self._cron.add_job(
            name=message[:30],
            schedule=schedule,
            message=message,
            deliver=True,
            channel=self._channel,
            to=self._chat_id,
            delete_after_run=delete_after,
        )
        return f"Created job '{job.name}' (id: {job.id})"

    def _list_jobs(self) -> str:
        jobs = self._cron.list_jobs()
        if not jobs:
            return "No active jobs."

        lines = ["Active jobs:"]
        for job in jobs:
            sched = job.schedule
            if sched.kind == "every":
                info = f"every {sched.every_ms / 1000}s"
            elif sched.kind == "cron":
                info = f"cron '{sched.expr}'"
            elif sched.kind == "at":
                from datetime import datetime

                dt = datetime.fromtimestamp(sched.at_ms / 1000)
                info = f"at {dt.isoformat()}"
            else:
                info = "unknown schedule"

            lines.append(f"- {job.id}: '{job.name}' ({info})")

        return "\n".join(lines)

    def _remove_job(self, job_id: str | None) -> str:
        if not job_id:
            return "Error: job_id is required for remove"

        if self._cron.remove_job(job_id):
            return f"Job {job_id} removed."
        return f"Job {job_id} not found."
