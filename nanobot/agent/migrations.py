"""KISS migration engine for nanobot upgrades."""

import re
from pathlib import Path

from loguru import logger


class MigrationManager:
    """
    MigrationManager handles automatic execution of upgrade instructions.
    Uses a simple version number stored in .version file.
    """

    def __init__(self, workspace: Path, agent_loop):
        self.workspace = workspace
        self.upgrades_dir = Path(__file__).parent / "upgrades"
        self.version_file = workspace.parent / ".version"
        self.agent = agent_loop

    async def run_pending(self):
        """Run all upgrades with version higher than current."""
        current_v = self._get_version()

        # Scan for v{number}_*.md files
        pending = []
        if not self.upgrades_dir.exists():
            return

        for f in self.upgrades_dir.glob("v*.md"):
            match = re.match(r"v(\d+)", f.name)
            if match:
                version = int(match.group(1))
                if version > current_v:
                    pending.append((version, f))

        # Sort by version number and apply
        for version, f in sorted(pending):
            logger.info(f"Applying upgrade v{version}: {f.name}")
            try:
                instruction = f.read_text()
                await self.agent.process_direct(
                    instruction,
                    session_key=f"migration:v{version}",
                    channel="system",
                    chat_id="migration",
                )
                self._set_version(version)
                logger.info(f"Upgrade to v{version} successful.")
            except Exception as e:
                logger.error(f"Failed to apply upgrade v{version}: {e}")
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
