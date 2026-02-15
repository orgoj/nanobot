"""Automatic migration engine for nanobot upgrades."""

from pathlib import Path

from loguru import logger


class MigrationManager:
    """
    MigrationManager handles automatic execution of upgrade instructions.

    It scans the 'upgrades' directory for .md files, executes them via
    the agent loop as instructions, and tracks which ones have been applied.
    """

    def __init__(self, workspace: Path, agent_loop):
        self.workspace = workspace
        # upgrades directory is inside the package: nanobot/agent/upgrades/
        self.upgrades_dir = Path(__file__).parent / "upgrades"
        self.state_file = workspace.parent / ".applied_migrations"
        self.agent = agent_loop

    async def run_pending(self):
        """Scan and run all pending migrations."""
        if not self.upgrades_dir.exists():
            self.upgrades_dir.mkdir(parents=True, exist_ok=True)
            return

        applied = self._get_applied()

        # Sort migrations by name to ensure consistent order
        migrations = sorted(self.upgrades_dir.glob("*.md"))

        for file in migrations:
            if file.name not in applied:
                logger.info(f"Applying automatic migration: {file.name}")
                try:
                    instruction = file.read_text()
                    # Execute the instruction via the agent loop
                    # We use a dedicated session key for migrations
                    await self.agent.process_direct(
                        instruction,
                        session_key=f"migration:{file.name}",
                        channel="system",
                        chat_id="migration",
                    )
                    self._mark_applied(file.name)
                    logger.info(f"Migration {file.name} applied successfully.")
                except Exception as e:
                    logger.error(f"Failed to apply migration {file.name}: {e}")
                    # We don't mark as applied so it can be retried on next start
                    # or fixed by the user

    def _get_applied(self) -> set[str]:
        """Read the set of already applied migrations."""
        if not self.state_file.exists():
            return set()
        try:
            return set(self.state_file.read_text().splitlines())
        except Exception as e:
            logger.error(f"Error reading migration state: {e}")
            return set()

    def _mark_applied(self, name: str):
        """Mark a migration as applied."""
        try:
            with open(self.state_file, "a") as f:
                f.write(f"{name}\n")
        except Exception as e:
            logger.error(f"Error marking migration {name} as applied: {e}")
