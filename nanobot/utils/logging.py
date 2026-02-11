import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

from nanobot.config.schema import Config


def setup_logging(config: Config):
    """
    Setup logging based on configuration.

    If file logging is enabled:
    1. Rotates any existing nanobot.log by appending its last modified timestamp.
    2. Adds a new file sink for workspace/logs/nanobot.log at DEBUG level.
    3. Configures stderr sink to only show ERROR level messages (to keep docker logs clean).
    """

    # Enable nanobot namespace logs
    logger.enable("nanobot")

    if not config.logging.file_logging_enabled:
        return

    if config.logging.file_log_path:
        log_file = Path(config.logging.file_log_path).expanduser()
    else:
        log_file = config.workspace_path / "logs" / "nanobot.log"

    log_dir = log_file.parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # 1. Rotate existing log file on start
    if log_file.exists():
        try:
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            timestamp = mtime.strftime("%Y%m%d-%H%M%S")
            rotated_name = f"nanobot.{timestamp}.log"
            log_file.rename(log_dir / rotated_name)
        except Exception as e:
            # We don't want to crash if rotation fails, just log it to stderr
            print(f"Warning: Failed to rotate log file: {e}", file=sys.stderr)

    # 2. Configure loguru sinks

    # Remove default handler (which is usually stderr at DEBUG/INFO)
    logger.remove()

    # Add stderr handler for ERRORs only (as requested for Docker)
    logger.add(
        sys.stderr,
        level="ERROR",
        format="<red>{level: <8}</red> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )

    # Add file handler for all details
    logger.add(
        str(log_file),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        encoding="utf-8",
    )

    logger.info(f"File logging initialized in {log_file}")
