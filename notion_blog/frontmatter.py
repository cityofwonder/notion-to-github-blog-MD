"""Build Jekyll front matter and the `_posts` filename from Notion page properties.

Property names are matched case-insensitively against a few common aliases
(English + Korean). Adjust the alias sets below if your Notion DB uses other
names.
"""

import re
from slugify import slugify

from . import richtext

CATEGORY_ALIASES = {"category", "categories", "카테고리", "분류"}
TAG_ALIASES = {"tags", "tag", "태그"}
SUBTITLE_ALIASES = {"subtitle", "부제", "description", "설명", "요약"}


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


def build(page: dict) -> tuple[str, dict]:
    """Return (front_matter_text, meta) where meta carries date/slug/cover."""
    props = page.get("properties", {})
    title = _title(page)
    date = _date(page)

    categories = [f"📂/{v}" for v in _select_values(_find_prop(props, CATEGORY_ALIASES))]
    tags = _select_values(_find_prop(props, TAG_ALIASES))

    subtitle_prop = _find_prop(props, SUBTITLE_ALIASES)
    subtitle = ""
    if subtitle_prop and subtitle_prop["type"] == "rich_text":
        subtitle = richtext.plain(subtitle_prop["rich_text"]).strip()

    cover = _cover_url(page)

    lines = ["---", "layout: post", f'title: "{title}"']
    if subtitle:
        lines.append(f'subtitle: "{subtitle}"')
    if categories:
        lines.append(f"categories: {_yaml_list(categories)}")
    if tags:
        lines.append(f"tags: {_yaml_list(tags)}")
    if cover:
        lines += [
            "banner:",
            f'  image: "{cover}"',
            "  opacity: 0.8",
            '  background: "rgba(0, 0, 0, 0.7)"',
        ]
    lines.append("---")

    slug = slugify(title) or slugify(title, allow_unicode=True) or page["id"].replace("-", "")[:8]
    meta = {"date": date, "slug": slug, "title": title}
    return "\n".join(lines) + "\n", meta
