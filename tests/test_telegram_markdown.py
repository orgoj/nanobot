"""Tests for Telegram Markdown formatting."""

from nanobot.utils.telegram_markdown import markdown_to_telegram


def test_basic_bold():
    # We use HTML for Telegram
    assert markdown_to_telegram("**bold**") == "<b>bold</b>"


def test_basic_italic():
    assert markdown_to_telegram("*italic*") == "<i>italic</i>"


def test_links():
    assert (
        markdown_to_telegram("[link](https://example.com)")
        == '<a href="https://example.com">link</a>'
    )


def test_inline_code():
    assert markdown_to_telegram("Use `code` here") == "Use <code>code</code> here"


def test_code_blocks():
    result = markdown_to_telegram('```python\nprint("Hello")\n```')
    assert "<pre>print(&quot;Hello&quot;)\n</pre>" in result


def test_nested_formatting():
    assert markdown_to_telegram("***bold italic***") == "<i><b>bold italic</b></i>"


def test_tables():
    md = "| col1 | col2 |\n|---|---|\n| val1 | val2 |"
    result = markdown_to_telegram(md)
    assert "<pre>" in result
    assert "col1" in result
    assert "val1" in result
    assert "+" in result  # ASCII table border
