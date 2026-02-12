"""Shared loop-guard helpers for tool call repetition and hashing."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from nanobot.providers.base import ToolCallRequest


def tool_call_hash(name: str, arguments: dict[str, Any]) -> str:
    """Stable hash for one tool call by name + sorted arguments."""
    args_json = json.dumps(arguments, sort_keys=True)
    return hashlib.sha256(f"{name}:{args_json}".encode()).hexdigest()


def collect_call_ids_and_hashes(tool_calls: list[ToolCallRequest]) -> tuple[list[str], list[str]]:
    """Extract call ids and stable hashes for a batch of tool calls."""
    ids = [tc.id for tc in tool_calls if tc.id]
    hashes = [tool_call_hash(tc.name, tc.arguments) for tc in tool_calls]
    return ids, hashes


def is_hash_loop(current_hashes: list[str], seen_hashes: set[str]) -> bool:
    """True when all current hashes already appeared in seen window."""
    return len([h for h in current_hashes if h in seen_hashes]) == len(current_hashes)


def is_id_loop(current_ids: list[str], seen_ids: set[str]) -> bool:
    """True when all current ids already appeared in seen window."""
    return bool(current_ids) and len([i for i in current_ids if i in seen_ids]) == len(current_ids)


@dataclass
class RepeatWindow:
    """Track repeated signatures across iterations."""

    last_signature: str | None = None
    repeat_count: int = 0

    def update(self, signature: str) -> int:
        if signature == self.last_signature:
            self.repeat_count += 1
        else:
            self.last_signature = signature
            self.repeat_count = 1
        return self.repeat_count
