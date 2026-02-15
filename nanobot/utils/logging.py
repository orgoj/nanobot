import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.config.schema import Config


def jsonl_serializer(record: dict[str, Any]) -> str:
    """Serialize log record to JSONL format."""
    log_record = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "module": record["module"],
        "function": record["function"],
        "line": record["line"],
        "channel": record["extra"].get("channel"),
        "user_id": record["extra"].get("user_id"),
        "chat_id": record["extra"].get("chat_id"),
        "metadata": record["extra"].get("metadata", {}),
    }
    # Include any other extra fields
    for key, value in record["extra"].items():
        if key not in ["channel", "user_id", "chat_id", "metadata"]:
            log_record[key] = value

    try:
        return json.dumps(log_record, ensure_ascii=False, default=str) + "\n"
    except Exception:
        # Fallback if even default=str fails
        return (
            json.dumps(
                {
                    "timestamp": log_record["timestamp"],
                    "level": "ERROR",
                    "message": "Log serialization failed",
                }
            )
            + "\n"
        )


def setup_logging(config: Config):
    """Setup logging to JSONL file and stderr."""
    logger.remove()

    if not config.logging.enabled:
        return

    # Stderr handler - plain text, NO colors, no color tags to avoid parsing errors
    logger.add(
        sys.stderr,
        level=config.logging.stderr_level,
        format="{level: <8} | {name}:{function}:{line} - {message}\n",
        colorize=False,
    )

    # File handler (JSONL) - NO colors
    log_file = Path(config.logging.file_path).expanduser()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_file),
        level=config.logging.level,
        format=lambda r: jsonl_serializer(r).replace("{", "{{").replace("}", "}}"),
        colorize=False,
    )

    logger.info(f"Logging initialized. File: {log_file}")
