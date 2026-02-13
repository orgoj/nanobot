"""Telegram HTML formatting utilities with ASCII table support."""

import html
import re

from markdown_it import MarkdownIt


def format_ascii_table(rows):
    """Render a 2D list of strings as an aligned ASCII table."""
    if not rows or not rows[0]:
        return ""

    # Calculate max width for each column
    num_cols = len(rows[0])
    widths = [0] * num_cols
    for row in rows:
        for i in range(min(len(row), num_cols)):
            widths[i] = max(widths[i], len(str(row[i])))

    # Build the table
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    result = [sep]

    for i, row in enumerate(rows):
        # Ensure row has correct number of columns
        cells = list(row) + [""] * (num_cols - len(row))
        formatted_row = (
            "|" + "|".join(f" {str(c).ljust(widths[j])} " for j, c in enumerate(cells)) + "|"
        )
        result.append(formatted_row)
        if i == 0:  # Add separator after header
            result.append(sep)

    result.append(sep)
    return "\n".join(result)


def markdown_to_html(text: str) -> str:
    """Convert Markdown to Telegram-compatible HTML with beautiful ASCII tables."""
    if not text:
        return ""

    md = MarkdownIt().enable("table")
    tokens = md.parse(text)

    def render(tokens):
        if not tokens:
            return ""
        result = ""

        # State for table parsing
        table_rows = []
        current_row = []
        in_table = False

        for i, token in enumerate(tokens):
            # --- Table Logic ---
            if token.type == "table_open":
                in_table = True
                table_rows = []
                continue
            elif token.type == "table_close":
                in_table = False
                result += f"<pre>\n{html.escape(format_ascii_table(table_rows))}\n</pre>\n"
                continue

            if in_table:
                if token.type == "tr_open":
                    current_row = []
                elif token.type == "tr_close":
                    table_rows.append(current_row)
                elif token.type == "inline" and tokens[i - 1].type in ["th_open", "td_open"]:
                    # Get the rendered content of the cell
                    current_row.append(render(token.children))
                continue

            # --- Standard Formatting ---
            if token.type == "inline":
                result += render(token.children)
                continue

            content = html.escape(token.content) if token.content else ""

            if token.type == "heading_open":
                result += "<b>"
            elif token.type == "heading_close":
                result += "</b>\n"
            elif token.type == "strong_open":
                result += "<b>"
            elif token.type == "strong_close":
                result += "</b>"
            elif token.type == "em_open":
                result += "<i>"
            elif token.type == "em_close":
                result += "</i>"
            elif token.type == "code_inline":
                result += f"<code>{content}</code>"
            elif token.type == "fence":
                result += f"<pre>{content}</pre>\n"
            elif token.type == "link_open":
                href = html.escape(token.attrGet("href") or "")
                result += f'<a href="{href}">'
            elif token.type == "link_close":
                result += "</a>"
            elif token.type == "text":
                result += content
            elif token.type == "list_item_open":
                result += "• "
            elif token.type == "list_item_close":
                result += "\n"
            elif token.type == "paragraph_close":
                result += "\n\n"
            elif token.type == "softbreak" or token.type == "hardbreak":
                result += "\n"
            elif token.type == "blockquote_open":
                result += "<blockquote>"
            elif token.type == "blockquote_close":
                result += "</blockquote>\n"

        return result

    output = render(tokens)
    return re.sub(r"\n{3,}", "\n\n", output).strip()


def markdown_to_telegram(text: str) -> str:
    return markdown_to_html(text)
