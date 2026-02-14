import json
from datetime import datetime

from nanobot.utils.logging import jsonl_serializer


def test_jsonl_serializer():
    # Mock loguru record
    record = {
        "time": datetime(2026, 2, 14, 10, 0, 0),
        "level": type("Level", (), {"name": "INFO"})(),
        "message": "Test message",
        "module": "test_mod",
        "function": "test_func",
        "line": 42,
        "extra": {
            "channel": "telegram",
            "user_id": "123",
            "chat_id": "456",
            "metadata": {"foo": "bar"},
            "custom_field": "baz",
        },
    }

    result = jsonl_serializer(record)
    data = json.loads(result)

    assert data["timestamp"] == "2026-02-14T10:00:00"
    assert data["level"] == "INFO"
    assert data["message"] == "Test message"
    assert data["channel"] == "telegram"
    assert data["user_id"] == "123"
    assert data["chat_id"] == "456"
    assert data["metadata"] == {"foo": "bar"}
    assert data["custom_field"] == "baz"
    assert result.endswith("\n")
