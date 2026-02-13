"""Cron tool for scheduling reminders, tasks, and routing calibration."""

from typing import TYPE_CHECKING, Any

from nanobot.agent.tools.base import Tool
from nanobot.cron.types import CronSchedule

if TYPE_CHECKING:
    from nanobot.cron.service import CronService


class CronTool(Tool):
    """
    Tool to schedule reminders, recurring tasks, and routing calibration.
    
    Supports two job types:
    1. User reminders (delivered back to user via chat/channel)
    2. System calibration (optimizes routing performance in background)
    """
    
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
            "Schedule reminders, recurring tasks, and routing calibration. "
            "Supports periodic execution (every X seconds), cron expressions ('0 9 * * *'), "
            "or one-time 'at' datetime. Use 'calibrate' to schedule routing optimization."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "calibrate", "list", "remove"],
                    "description": "Action to perform: 'add' for reminders/tasks, 'calibrate' for routing optimization",
                },
                "message": {
                    "type": "string",
                    "description": "Reminder message or task description (for add action)",
                },
                "every_seconds": {
                    "type": "integer",
                    "description": "Execution interval in seconds.",
                },
                "cron_expr": {
                    "type": "string",
                    "description": "Cron expression like '0 9 * * *'",
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
        elif action == "calibrate":
            return self._add_calibration_job(every_seconds, cron_expr)
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

    def _add_calibration_job(self, every_seconds: int | None, cron_expr: str | None) -> str:
        """Add a routing calibration job."""
        if not every_seconds and not cron_expr:
            cron_expr = "0 2 * * *"
            schedule = CronSchedule(kind="cron", expr=cron_expr)
            schedule_desc = "daily at 2:00 AM"
        elif every_seconds:
            schedule = CronSchedule(kind="every", every_ms=every_seconds * 1000)
            schedule_desc = f"every {every_seconds}s"
        elif cron_expr:
            schedule = CronSchedule(kind="cron", expr=cron_expr)
            schedule_desc = f"on schedule '{cron_expr}'"
        else:
            return "Error: either every_seconds or cron_expr is required"
        
        job = self._cron.add_job(
            name="Routing Calibration",
            schedule=schedule,
            message="CALIBRATE_ROUTING",
            deliver=False,
            channel="internal",
            to="calibration",
        )
        return f"Scheduled routing calibration {schedule_desc} (job id: {job.id})"

    def _list_jobs(self) -> str:
        """List all jobs."""
        jobs = self._cron.list_jobs()
        if not jobs:
            return "No scheduled jobs."
        
        user_jobs = []
        calibration_jobs = []
        for job in jobs:
            if job.payload.message == "CALIBRATE_ROUTING":
                calibration_jobs.append(job)
            else:
                user_jobs.append(job)
        
        lines = []
        if user_jobs:
            lines.append("📅 User Reminders:")
            for job in user_jobs:
                lines.append(f"  • {job.id}: '{job.name}' ({job.schedule.kind})")
        if calibration_jobs:
            if user_jobs: lines.append("")
            lines.append("🔧 System Calibration:")
            for job in calibration_jobs:
                lines.append(f"  • {job.id}: '{job.name}' ({job.schedule.kind})")
        
        return "\n".join(lines)

    def _remove_job(self, job_id: str | None) -> str:
        if not job_id:
            return "Error: job_id is required for remove"

        if self._cron.remove_job(job_id):
            return f"Job {job_id} removed."
        return f"Job {job_id} not found."
