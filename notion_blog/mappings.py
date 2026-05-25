"""Notion -> blog component mappings.

These mirror the custom CSS classes documented in the blog's
"마크다운 스타일링 정리" post (cityofwonder.github.io). Only colors the
blog actually styles are mapped; anything else falls back to plain text.
"""

# Notion foreground text color -> blog `text-*` class.
# Blog supports: red, blue, green, orange, purple, pink, gray.
TEXT_COLOR_CLASS = {
    "red": "text-red",
    "blue": "text-blue",
    "green": "text-green",
    "orange": "text-orange",
    "purple": "text-purple",
    "pink": "text-pink",
    "gray": "text-gray",
    # notion "brown", "yellow", "default" have no blog equivalent -> skipped
}

# Notion background color -> blog `highlight-*` class.
# Blog supports: yellow, green, blue, pink, orange, purple.
HIGHLIGHT_CLASS = {
    "yellow_background": "highlight-yellow",
    "green_background": "highlight-green",
    "blue_background": "highlight-blue",
    "pink_background": "highlight-pink",
    "orange_background": "highlight-orange",
    "purple_background": "highlight-purple",
    # red/gray/brown backgrounds have no blog equivalent -> skipped
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
