"""Convert Notion rich_text arrays into markdown/HTML inline strings.

kramdown parses span-level markdown inside inline HTML by default, so we can
safely wrap markdown emphasis (`**`, `*`, `~~`) inside `<span class="...">`
without losing formatting.
"""

from .mappings import TEXT_COLOR_CLASS, HIGHLIGHT_CLASS


def _classes_for_color(color: str) -> list[str]:
    if not color or color == "default":
        return []
    if color.endswith("_background"):
        cls = HIGHLIGHT_CLASS.get(color)
    else:
        cls = TEXT_COLOR_CLASS.get(color)
    return [cls] if cls else []


def _render_segment(seg: dict) -> str:
    seg_type = seg.get("type")
    annotations = seg.get("annotations", {})

    if seg_type == "equation":
        # Inline math: rendered by jekyll-spaceship / MathJax.
        expr = seg.get("equation", {}).get("expression", "")
        text = f"${expr}$"
        href = seg.get("href")
        return f"[{text}]({href})" if href else text

    text = seg.get("plain_text", "")
    if not text:
        return ""

    # `code` is exclusive: markdown code spans can't contain other markdown.
    if annotations.get("code"):
        text = f"`{text}`"
    else:
        if annotations.get("bold"):
            text = f"**{text}**"
        if annotations.get("italic"):
            text = f"*{text}*"
        if annotations.get("strikethrough"):
            text = f"~~{text}~~"

    href = seg.get("href")
    if href:
        text = f"[{text}]({href})"

    classes = _classes_for_color(annotations.get("color", "default"))
    if annotations.get("underline"):
        classes.append("text-underline")
    if classes:
        text = f'<span class="{" ".join(classes)}">{text}</span>'

    return text


def render(rich_text: list[dict]) -> str:
    """Render a Notion rich_text array to an inline markdown string."""
    return "".join(_render_segment(seg) for seg in (rich_text or []))


def plain(rich_text: list[dict]) -> str:
    """Plain-text concatenation, ignoring all annotations."""
    return "".join(seg.get("plain_text", "") for seg in (rich_text or []))
