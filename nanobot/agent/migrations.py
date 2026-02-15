"""KISS migration engine for nanobot upgrades."""

import re
from pathlib import Path

from loguru import logger


class MigrationManager:
    """
    MigrationManager handles automatic execution of upgrade instructions.
    Uses a simple version number stored in .prompt_version file.
    """

    def __init__(self, workspace: Path, agent_loop):
        self.workspace = workspace
        self.upgrades_dir = Path(__file__).parent / "upgrades"
        self.version_file = workspace.parent / ".prompt_version"
        self.agent = agent_loop

    async def run_pending(self):
        """Run all upgrades with version higher than current."""
        current_v = self._get_version()

        # Scan for v{number}_*.md files
        pending = []
        if not self.upgrades_dir.exists():
            # In package mode, this should always exist if there are upgrades
            return

        for f in self.upgrades_dir.glob("v*.md"):
            match = re.match(r"v(\d+)", f.name)
            if match:
                version = int(match.group(1))
                if version > current_v:
                    pending.append((version, f))

        if not pending:
            logger.info(f"No pending prompt upgrades (current version: v{current_v})")
            return

        # Sort by version number and apply
        for version, f in sorted(pending):
            msg = f"🆙 Applying automatic prompt upgrade v{version}: {f.name}"
            logger.info(msg)
            print(msg, flush=True)
            try:
                instruction = f.read_text()
                await self.agent.process_direct(
                    instruction,
                    session_key=f"migration:v{version}",
                    channel="system",
                    chat_id="migration",
                )
                self._set_version(version)
                success_msg = f"✅ Upgrade to v{version} successful."
                logger.info(success_msg)
                print(success_msg, flush=True)
            except Exception as e:
                err_msg = f"❌ Failed to apply upgrade v{version}: {e}"
                logger.error(err_msg)
                print(err_msg, flush=True)
                break  # Stop at first failure to keep version consistent

    def _get_version(self) -> int:
        """Read the current version number."""
        if not self.version_file.exists():
            return 0
        try:
            return int(self.version_file.read_text().strip())
        except Exception:
            return 0

    def _set_version(self, version: int):
        """Write the new version number."""
        try:
            self.version_file.write_text(str(version))
        except Exception as e:
            logger.error(f"Error saving version {version}: {e}")
