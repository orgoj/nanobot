import inspect

from nanobot.channels.feishu import FeishuChannel
from pathlib import Path


def test_extract_explicit_attachments() -> None:
    text = "hello ![](/tmp/a.png) file:/tmp/b.txt world"
    cleaned, paths = FeishuChannel._extract_explicit_attachments(text)
    assert "/tmp/a.png" in paths
    assert "/tmp/b.txt" in paths
    assert "hello" in cleaned and "world" in cleaned


def test_normalize_attachment_paths(tmp_path: Path) -> None:
    ok = tmp_path / "ok.png"
    ok.write_bytes(b"x")
    cleaned = FeishuChannel._normalize_attachment_paths([str(ok), "rel.png", "/nope.jpg"])
    assert cleaned == [ok]


def test_normalize_attachment_paths_resolves_relative(tmp_path: Path) -> None:
    sig = inspect.signature(FeishuChannel._normalize_attachment_paths)
    assert "base_dir" in sig.parameters

    rel = tmp_path / "rel.png"
    rel.write_bytes(b"x")
    cleaned = FeishuChannel._normalize_attachment_paths(["rel.png"], base_dir=tmp_path)
    assert cleaned == [rel.resolve()]


def test_normalize_attachment_paths_enforces_allowed_dir(tmp_path: Path) -> None:
    sig = inspect.signature(FeishuChannel._normalize_attachment_paths)
    assert "allowed_dir" in sig.parameters

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    ok = allowed / "ok.txt"
    ok.write_text("x")
    outside = tmp_path / "outside.txt"
    outside.write_text("y")

    cleaned = FeishuChannel._normalize_attachment_paths(
        [str(ok), str(outside), "../outside.txt"],
        allowed_dir=allowed,
        base_dir=allowed,
    )
    assert cleaned == [ok.resolve()]
