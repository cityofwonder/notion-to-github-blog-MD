"""Build Jekyll front matter and the `_posts` filename from a Notion page.

Front matter is emitted in a fixed shape so every post looks the same.
`subtitle` and `categories` are left as placeholders for the author to fill;
`tags` are read from a Notion multi-select; `banner.image` uses the cover.
"""

import re
from slugify import slugify

from . import richtext

TAG_ALIASES = {"tags", "tag", "태그"}


def _find_prop(props: dict, aliases: set[str]):
    for name, value in props.items():
        if name.strip().lower() in aliases:
            return value
    return None


def _select_values(prop: dict) -> list[str]:
    if not prop:
        return []
    if prop["type"] == "select":
        sel = prop.get("select")
        return [sel["name"]] if sel else []
    if prop["type"] == "multi_select":
        return [opt["name"] for opt in prop.get("multi_select", [])]
    return []


def _title(page: dict) -> str:
    for value in page.get("properties", {}).values():
        if value["type"] == "title":
            return richtext.plain(value["title"]).strip()
    return "untitled"


def _date(page: dict) -> str:
    for value in page.get("properties", {}).values():
        if value["type"] == "date" and value.get("date"):
            return value["date"]["start"][:10]
    return page.get("created_time", "")[:10]


def _cover_url(page: dict) -> str | None:
    cover = page.get("cover")
    if not cover:
        return None
    if cover["type"] == "external":
        return cover["external"]["url"]
    if cover["type"] == "file":
        return cover["file"]["url"]
    return None


def _yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(f'"{v}"' for v in values) + "]"


def build(page: dict, slug_override: str | None = None,
          title_override: str | None = None) -> tuple[str, dict]:
    """Return (front_matter_text, meta) where meta carries date/slug/cover.

    slug_override lets you supply a casual English slug instead of the default
    (which transliterates non-ASCII titles, e.g. Korean -> romaji).
    """
    props = page.get("properties", {})
    title = title_override or _title(page)
    date = _date(page)
    tags = _select_values(_find_prop(props, TAG_ALIASES))
    cover = _cover_url(page) or ""

    # Fixed shape: subtitle/categories are placeholders the author fills in.
    lines = [
        "---",
        "layout: post",
        f'title: "{title}"',
        'subtitle: ""',
        'categories: ["📂/"]',
        f"tags: {_yaml_list(tags)}",
        "banner:",
        f'  image: "{cover}"',
        "  opacity: 0.5",
        '  background: "rgba(0, 0, 0, 0.7)"',
        "---",
    ]

    if slug_override:
        slug = slugify(slug_override)
    else:
        slug = slugify(title) or slugify(title, allow_unicode=True) or page["id"].replace("-", "")[:8]
    meta = {"date": date, "slug": slug, "title": title}
    return "\n".join(lines) + "\n", meta
