"""Notion -> blog component mappings.

These mirror the custom CSS classes documented in the blog's
"마크다운 스타일링 정리" post (cityofwonder.github.io). The color maps cover
Notion's full palette, so no color is silently dropped on conversion.
"""

# Notion foreground text color -> blog `text-*` class.
# Covers all 9 non-default Notion text colors; "default" is intentionally
# absent (no span emitted).
TEXT_COLOR_CLASS = {
    "red": "text-red",
    "blue": "text-blue",
    "green": "text-green",
    "orange": "text-orange",
    "purple": "text-purple",
    "pink": "text-pink",
    "gray": "text-gray",
    "yellow": "text-yellow",
    "brown": "text-brown",
}

# Notion background color -> blog `highlight-*` class.
# Covers all 9 Notion background colors.
HIGHLIGHT_CLASS = {
    "yellow_background": "highlight-yellow",
    "green_background": "highlight-green",
    "blue_background": "highlight-blue",
    "pink_background": "highlight-pink",
    "orange_background": "highlight-orange",
    "purple_background": "highlight-purple",
    "red_background": "highlight-red",
    "gray_background": "highlight-gray",
    "brown_background": "highlight-brown",
}

# Notion callout color -> blog box class.
# Blog supports: box-note, box-success, box-warning, box-danger.
CALLOUT_BOX = {
    "default": "box-note",
    "gray": "box-note",
    "brown": "box-note",
    "blue": "box-note",
    "purple": "box-note",
    "green": "box-success",
    "yellow": "box-warning",
    "orange": "box-warning",
    "red": "box-danger",
    "pink": "box-danger",
}

# Default emoji used when a callout has no icon, keyed by box class.
BOX_DEFAULT_EMOJI = {
    "box-note": "💡",
    "box-success": "✅",
    "box-warning": "⚠️",
    "box-danger": "🚨",
}

# Notion heading level -> markdown prefix.
# The post title lives in front matter (rendered as H1), so body headings
# start at H2 to match the blog's existing posts.
HEADING_PREFIX = {
    "heading_1": "##",
    "heading_2": "###",
    "heading_3": "####",
}


def callout_box_class(color: str) -> str:
    """Map a Notion callout color (with or without `_background`) to a box class."""
    base = color.replace("_background", "")
    return CALLOUT_BOX.get(base, "box-note")


def toggle_color_class(color: str) -> str | None:
    """Notion block colour -> `toggle-*` class for an open <details> panel.

    Only background colours produce a panel; a plain text colour on the block
    is left alone (the blog styles the toggle chrome, not its text).
    """
    cls = HIGHLIGHT_CLASS.get(color or "")
    return cls.replace("highlight-", "toggle-") if cls else None
