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

A row whose `layout` holds `directory` is an index page rather than an
article: see directory.py for how its body is read, and render() for the
front matter it gets instead.
"""

import json
import re

from slugify import slugify

from . import richtext

TAG_ALIASES = {"tags", "tag", "태그"}
FILENAME_ALIASES = {"filename", "file name", "file-name", "파일명", "파일 이름"}
SUBTITLE_ALIASES = {"subtitle", "sub title", "부제", "부제목"}
CATEGORY_ALIASES = {"categories", "category", "카테고리"}
BANNER_ALIASES = {"banner", "cover", "배너"}
STATUS_ALIASES = {"상태", "status", "state"}
LAYOUT_ALIASES = {"layout", "레이아웃"}

# "2026-08-20-p5-MLA-USENIX2026.md" -> ("2026-08-20", "p5-MLA-USENIX2026")
FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+?)(?:\.(?:md|markdown))?$")
# "paper-LLM-Lineage-dir.md" -> "paper-LLM-Lineage-dir" (date comes from the page)
EXTENSION_RE = re.compile(r"\.(?:md|markdown)$")


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


def _q(value) -> str:
    """A YAML double-quoted scalar.

    JSON string escaping is valid YAML, so a title such as
    `Your "Pro" LLM Subscription` stays one string instead of ending the
    scalar at the first inner quote and breaking the whole front matter.
    Plain titles come out byte-identical to the old `"..."` form.
    """
    return json.dumps(value or "", ensure_ascii=False)


def _yaml_time(iso: str) -> str:
    """Notion's `2026-11-18T07:15:00.000Z` -> `2026-11-18 07:15:00 +0000`."""
    match = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})", iso or "")
    return f"{match.group(1)} {match.group(2)} +0000" if match else ""


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

    # The `filename` property is authoritative for both date and slug. Without
    # a date prefix it still names the slug, and the date falls back to the
    # page's own (a directory's filename usually carries no date).
    name = _plain(_find_prop(props, FILENAME_ALIASES))
    match = FILENAME_RE.match(name) if name else None
    if match:
        date, file_slug = match.group(1), match.group(2)
    else:
        date = _date(page)
        file_slug = re.sub(r"\s+", "-", EXTENSION_RE.sub("", name).strip()) or None

    if slug_override:
        slug = slugify(slug_override)
    elif file_slug:
        slug = file_slug  # verbatim: the author already chose the exact wording
    else:
        slug = (slugify(title) or slugify(title, allow_unicode=True)
                or page["id"].replace("-", "")[:8])

    # `layout` carries "post" (or "directory") once a page is meant to be
    # published; until then the sync writes it as a draft_ file, which Jekyll
    # ignores.
    layouts = _select_values(_find_prop(props, LAYOUT_ALIASES))
    layout_names = {v.strip().lower() for v in layouts}
    is_directory = "directory" in layout_names
    status = _plain(_find_prop(props, STATUS_ALIASES))

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
        "status": status,
        "layouts": layouts,
        "published": is_directory or "post" in layout_names,
        "is_directory": is_directory,
        "notion_id": page.get("id", ""),
        "last_edited": page.get("last_edited_time", ""),
        "from_filename_prop": bool(file_slug),
    }


def _directory_lines(intro: str, sections: list[dict]) -> list[str]:
    """The board a `layout: directory` page renders, as front matter.

    Each item keeps its Notion page id; the blog looks the post up by the
    `notion_id` in that post's own front matter at build time. The title is
    only a fallback for a linked page that is not published (yet).
    """
    lines = []
    if intro:
        lines.append(f"intro: {_q(intro)}")
    if not sections:
        return lines + ["directory: []"]
    lines.append("directory:")
    for section in sections:
        lines.append(f"  - title: {_q(section['title'])}")
        if section.get("note"):
            lines.append(f"    note: {_q(section['note'])}")
        if not section["items"]:
            lines.append("    items: []")
            continue
        lines.append("    items:")
        for item in section["items"]:
            if "label" in item:
                lines.append(f"      - label: {_q(item['label'])}")
                continue
            lines.append(f"      - id: {_q(item['id'])}")
            lines.append(f"        title: {_q(item['title'])}")
            if item.get("note"):
                lines.append(f"        note: {_q(item['note'])}")
    return lines


def render(meta: dict, banner_image: str = "", directory=None) -> str:
    """Front matter text. `banner_image` is the already-downloaded local path.

    `notion`/`notion_id`/`notion_synced` mark the file as database-owned: the
    sync looks an existing post up by notion_id rather than by filename, so a
    renamed page updates in place instead of landing as a second file.

    A directory (`directory=(intro, sections)`) differs in three ways:
      - `date` is the page's last edit, so every edit floats it to the top of
        the feed the way a new post would;
      - `permalink` is fixed, so that moving date does not move the URL (and
        the comments keyed on it);
      - its image goes to `cover`, not `banner`, because the board draws its
        own header and must not get the theme's full-height banner on top.
    """
    lines = [
        "---",
        "layout: directory" if directory is not None else "layout: post",
        f"title: {_q(meta['title'])}",
        f"subtitle: {_q(meta['subtitle'])}",
        f"categories: {_yaml_list(meta['categories'])}",
        f"tags: {_yaml_list(meta['tags'])}",
    ]
    if meta.get("status"):
        lines.append(f"status: {_q(meta['status'])}")
    if directory is not None:
        updated = _yaml_time(meta.get("last_edited", ""))
        if updated:
            lines.append(f"date: {updated}")
        lines.append(f"permalink: /directory/{meta['slug']}/")
    lines += [
        "notion: true",
        f'notion_id: "{meta.get("notion_id", "")}"',
        f'notion_synced: "{meta.get("last_edited", "")}"',
    ]
    if directory is not None:
        if banner_image:
            lines.append(f"cover: {_q(banner_image)}")
        lines += _directory_lines(*directory)
    else:
        lines += [
            "banner:",
            f'  image: "{banner_image}"',
            "  opacity: 0.5",
            '  background: "rgba(0, 0, 0, 0.7)"',
        ]
    lines.append("---")
    return "\n".join(lines) + "\n"