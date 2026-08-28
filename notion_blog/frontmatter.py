"""Build Jekyll front matter and the `_posts` filename from a Notion page.

Everything is read from the page's database properties, so a page that has
them filled needs no CLI flags and no hand-editing afterwards:

    filename    "2026-08-20-p5-MLA-USENIX2026.md"  -> post date + slug
    이름/title  page title
    subtitle    subtitle line
    categories  path segments, joined in order
    tags        multi-select
    banner      file property (falls back to the page cover)

`--slug` / `--title` still win when passed.
"""

import re

from slugify import slugify

from . import richtext

TAG_ALIASES = {"tags", "tag", "태그"}
FILENAME_ALIASES = {"filename", "file name", "file-name", "파일명", "파일 이름"}
SUBTITLE_ALIASES = {"subtitle", "sub title", "부제", "부제목"}
CATEGORY_ALIASES = {"categories", "category", "카테고리"}
BANNER_ALIASES = {"banner", "cover", "배너"}

# "2026-08-20-p5-MLA-USENIX2026.md" -> ("2026-08-20", "p5-MLA-USENIX2026")
FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+?)(?:\.(?:md|markdown))?$")


def _find_prop(props: dict, aliases: set[str]):
    for name, value in props.items():
        if name.strip().lower() in aliases:
            return value
    return None


def _plain(prop: dict) -> str:
    """Text out of a rich_text / title / select / multi_select property."""
    if not prop:
        return ""
    kind = prop["type"]
    if kind in ("rich_text", "title"):
        return richtext.plain(prop[kind]).strip()
    if kind == "select":
        sel = prop.get("select")
        return sel["name"].strip() if sel else ""
    if kind == "multi_select":
        return "".join(opt["name"] for opt in prop.get("multi_select", [])).strip()
    return ""


def _select_values(prop: dict) -> list[str]:
    if not prop:
        return []
    if prop["type"] == "select":
        sel = prop.get("select")
        return [sel["name"]] if sel else []
    if prop["type"] == "multi_select":
        return [opt["name"] for opt in prop.get("multi_select", [])]
    return []


def _file_url(prop: dict) -> tuple[str | None, bool]:
    """First URL out of a `files` property, plus whether Notion hosts it.

    A Notion-hosted file comes back as a signed S3 link that expires within
    the hour, so it has to be downloaded. An external URL is somebody else's
    permanent address -- leave it linked, the way the hand-written posts link
    their Unsplash banners.
    """
    if not prop or prop["type"] != "files":
        return None, False
    for item in prop.get("files", []):
        if item.get("type") == "external":
            return item["external"]["url"], False
        if item.get("type") == "file":
            return item["file"]["url"], True
    return None, False


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


def _cover_url(page: dict) -> tuple[str | None, bool]:
    cover = page.get("cover")
    if not cover:
        return None, False
    if cover["type"] == "external":
        return cover["external"]["url"], False
    if cover["type"] == "file":
        return cover["file"]["url"], True
    return None, False


def _yaml_list(values: list[str]) -> str:
    return "[" + ", ".join('"' + v.replace('"', "'") + '"' for v in values) + "]"


def collect(page: dict, slug_override: str | None = None,
            title_override: str | None = None) -> dict:
    """Read every front-matter input off the page. No I/O."""
    props = page.get("properties", {})

    title = title_override or _title(page)
    subtitle = _plain(_find_prop(props, SUBTITLE_ALIASES))
    tags = _select_values(_find_prop(props, TAG_ALIASES))

    # Category path segments are stored as a multi-select ("📂/", "paper-review/",
    # "fingerprint/") and concatenated in order, matching the hand-written posts'
    # `categories: ["📂/paper-review/ml-stealing/HW/"]`.
    segments = _select_values(_find_prop(props, CATEGORY_ALIASES))
    categories = ["".join(segments)] if segments else ["📂/"]

    # The `filename` property is authoritative for both date and slug.
    name = _plain(_find_prop(props, FILENAME_ALIASES))
    match = FILENAME_RE.match(name) if name else None
    if match:
        date, file_slug = match.group(1), match.group(2)
    else:
        date, file_slug = _date(page), None

    if slug_override:
        slug = slugify(slug_override)
    elif file_slug:
        slug = file_slug  # verbatim: the author already chose the exact wording
    else:
        slug = (slugify(title) or slugify(title, allow_unicode=True)
                or page["id"].replace("-", "")[:8])

    banner_url, banner_hosted = _file_url(_find_prop(props, BANNER_ALIASES))
    if not banner_url:
        banner_url, banner_hosted = _cover_url(page)

    return {
        "title": title,
        "subtitle": subtitle,
        "categories": categories,
        "tags": tags,
        "date": date,
        "slug": slug,
        "banner_url": banner_url,
        "banner_hosted": banner_hosted,
        "from_filename_prop": bool(match),
    }


def render(meta: dict, banner_image: str = "") -> str:
    """Front matter text. `banner_image` is the already-downloaded local path."""
    return "\n".join([
        "---",
        "layout: post",
        f'title: "{meta["title"]}"',
        f'subtitle: "{meta["subtitle"]}"',
        f"categories: {_yaml_list(meta['categories'])}",
        f"tags: {_yaml_list(meta['tags'])}",
        "banner:",
        f'  image: "{banner_image}"',
        "  opacity: 0.5",
        '  background: "rgba(0, 0, 0, 0.7)"',
        "---",
    ]) + "\n"
