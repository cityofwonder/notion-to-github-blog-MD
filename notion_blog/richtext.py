"""Convert Notion rich_text arrays into markdown/HTML inline strings.

Emphasis is emitted as `<strong>`/`<em>`/`<del>` tags instead of markdown
delimiters, so text with edge whitespace or literal asterisks survives. Links
stay markdown, which means any block-level HTML wrapper holding rendered text
needs a kramdown `markdown="1"` (or `markdown="span"`) attribute.
"""

import html
from urllib.parse import urlparse

from .mappings import TEXT_COLOR_CLASS, HIGHLIGHT_CLASS

# Links into the private workspace. A page/user mention carries one of these,
# and publishing it would put a dead (or access-requesting) link on the blog.
# `*.notion.site` is a *published* site, so it stays linkable.
_WORKSPACE_HOSTS = {"notion.so", "www.notion.so", "app.notion.com"}

# Mentions rendered as plain text: nothing on the public blog can resolve them,
# so they get a muted color to read as a reference rather than body text.
_MUTED_MENTIONS = {"user", "page", "database", "template_mention"}


def _is_workspace_url(href: str) -> bool:
    try:
        return (urlparse(href).hostname or "").lower() in _WORKSPACE_HOSTS
    except ValueError:
        return False


def _mention(seg: dict, text: str, href: str | None):
    """Return (text, href, extra_classes) for a mention segment.

    Notion resolves a page/database mention's `plain_text` to the target's
    title and a user mention's to "@Name", so the text is already readable;
    what has to go is the workspace href.
    """
    kind = (seg.get("mention") or {}).get("type", "")
    text = text.strip()
    if kind in _MUTED_MENTIONS:
        # Notion shows these with a `‣` marker; keep the label, drop the link.
        return text.lstrip("‣").strip(), None, ["text-gray"]
    if href and _is_workspace_url(href):
        return text, None, ["text-gray"]
    return text, href, []


def _classes_for_colors(colors: list[str]) -> list[str]:
    """Notion colour names -> blog classes.

    A span can carry both a text colour and a highlight; `annotations.color`
    only reports one, so the caller may pass both (see
    NotionSource.get_color_overrides).
    """
    out: list[str] = []
    for color in colors:
        if not color or color == "default":
            continue
        if color.endswith("_background"):
            cls = HIGHLIGHT_CLASS.get(color)
        else:
            cls = TEXT_COLOR_CLASS.get(color)
        if cls and cls not in out:
            out.append(cls)
    return out


def _render_segment(seg: dict, colors: list[str] | None = None) -> str:
    seg_type = seg.get("type")
    annotations = seg.get("annotations", {})
    palette = list(colors) if colors else [annotations.get("color", "default")]
    href = seg.get("href")
    extra_classes: list[str] = []

    if seg_type == "equation":
        # Inline math, rendered by jekyll-spaceship / MathJax. Emphasis is not
        # applied -- the processor scans the raw `$...$` -- but the colour span
        # wraps it fine, so a highlighted formula keeps its highlight.
        expr = seg.get("equation", {}).get("expression", "")
        text = f"${expr}$"
        return _wrap(text, href, palette, extra_classes, annotations)

    text = seg.get("plain_text", "")
    if seg_type == "mention":
        text, href, extra_classes = _mention(seg, text, href)
    if not text:
        return ""

    # `code` is exclusive: markdown code spans can't contain other markdown.
    if annotations.get("code"):
        # kramdown escapes code-span content itself; pre-escaping would double it.
        text = f"`{text}`"
    else:
        # plain_text is text the author typed, not markup: escape it so "a < b"
        # or "<TAG>" survives instead of being eaten as an HTML tag. Equations
        # and code spans are handled elsewhere and stay raw.
        text = html.escape(text, quote=False)
        # HTML tags rather than **/*/~~. Notion segments routinely carry edge
        # whitespace ("bold text ") or literal asterisks (footnote marks), and
        # markdown's delimiter-run rules silently drop the emphasis in both
        # cases -- `**bold text **` renders as plain text with the asterisks
        # showing. Tags have no such rule.
        if annotations.get("bold"):
            text = f"<strong>{text}</strong>"
        if annotations.get("italic"):
            text = f"<em>{text}</em>"
        if annotations.get("strikethrough"):
            text = f"<del>{text}</del>"

    return _wrap(text, href, palette, extra_classes, annotations)


def _wrap(text: str, href, palette: list[str], extra_classes: list[str],
          annotations: dict) -> str:
    if href and not _is_workspace_url(href):
        text = f"[{text}]({href})"

    classes = _classes_for_colors(palette)
    for cls in extra_classes:
        if cls not in classes:
            classes.append(cls)
    if annotations.get("underline"):
        classes.append("text-underline")
    if classes:
        text = f'<span class="{" ".join(classes)}">{text}</span>'
    return text


def render(rich_text: list[dict], colors: list[list[str]] | None = None) -> str:
    """Render a Notion rich_text array to an inline markdown string.

    `colors` is an optional per-segment override, aligned by index, carrying
    every colour Notion stored for that span (see get_color_overrides).
    """
    parts = []
    for i, seg in enumerate(rich_text or []):
        override = colors[i] if colors and i < len(colors) else None
        parts.append(_render_segment(seg, override))
    return "".join(parts)


def plain(rich_text: list[dict]) -> str:
    """Plain-text concatenation, ignoring all annotations."""
    return "".join(seg.get("plain_text", "") for seg in (rich_text or []))
