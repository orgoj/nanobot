"""Telegram Markdown formatting utilities."""

import re


def markdown_to_telegram(text: str, parse_mode: str = "MarkdownV2") -> str:
    """
    Convert clean Markdown to Telegram-compatible format.

    Args:
        text: Markdown text from the agent
        parse_mode: "MarkdownV2" (default) or "Markdown" (legacy)

    Returns:
        Escaped text for Telegram
    """
    if not text:
        return ""

    if parse_mode == "Markdown":
        # Legacy Markdown: escape _, *, [, `
        return re.sub(r"([_*\[`])", r"\\\1", text)

    if parse_mode != "MarkdownV2":
        return text

    # MarkdownV2 requires escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
    # But we must NOT escape them if they are part of a valid Markdown construct.

    # 1. Protect code blocks and inline code
    code_parts = []

    def save_code(match):
        code_parts.append(match.group(0))
        return f"\x01C{len(code_parts) - 1}\x01"

    # Save triple backtick blocks first
    processed = re.sub(r"```[\s\S]*?```", save_code, text)
    # Save inline code
    processed = re.sub(r"`[^`\n]+`", save_code, processed)

    # 2. Protect links: [text](url)
    link_parts = []

    def save_link(match):
        link_parts.append(match.group(0))
        return f"\x01L{len(link_parts) - 1}\x01"

    processed = re.sub(r"\[[^\]]+\]\([^)]+\)", save_link, processed)

    # 3. Escape all special characters in the remaining text
    # Characters to escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
    processed = re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", processed)

    # 4. Restore links and escape their internal parts correctly
    # Inside (...) part of a link, only ) and \ must be escaped.
    for i, link in enumerate(link_parts):
        m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", link)
        if m:
            label, url = m.groups()
            # Telegram: In all other places [than pre/code], characters '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'
            # must be escaped with the preceding character '\'.
            # In (url) part of inline link, all characters ')' and '\' must be escaped with a preceding '\' character.

            # Special case for URLs: Telegram also seems to allow/require escapement of other chars
            # in MarkdownV2 URLs if they are not part of the URL spec, but basically ) and \ are MUST.
            escaped_url = url.replace("\\", "\\\\").replace(")", "\\)")

            # For the label, we want to allow standard Markdown like *bold* or _italic_
            # but escape other special characters like . or ! or -
            # Given the requirement "*bold*" -> "\*bold\*", it means they want to pass Markdown
            # through. To do that in MarkdownV2, you MUST escape the marks themselves.
            def escape_label(text):
                return re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", text)

            escaped_label = escape_label(label)
            processed = processed.replace(f"\x01L{i}\x01", f"[{escaped_label}]({escaped_url})")

    # 5. Restore code blocks
    for i, code in enumerate(code_parts):
        # Inside code blocks, only \ and ` must be escaped
        if code.startswith("```"):
            inner = code[3:-3]
            # Telegram says: inside pre and code entities, all '`' and '\' characters
            # must be escaped with a preceding '\' character.
            # However, my previous attempt was escaping OTHER chars inside code because
            # they were escaped in step 3. But code blocks were protected in step 1.
            # So they should be fine.
            escaped_inner = inner.replace("\\", "\\\\").replace("`", "\\`").replace("\x01", "")
            processed = processed.replace(f"\x01C{i}\x01", f"```{escaped_inner}```")
        else:
            inner = code[1:-1]
            escaped_inner = inner.replace("\\", "\\\\").replace("`", "\\`").replace("\x01", "")
            processed = processed.replace(f"\x01C{i}\x01", f"`{escaped_inner}`")

    return processed
