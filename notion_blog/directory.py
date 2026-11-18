"""Read a `layout: directory` Notion page as the sections of a board.

A directory page is an index, not an article: its headings group posts, and
each post is linked under its heading as a page mention, a link-to-page
block, or an inline link to the page. The sync stores only the linked page
ids (plus titles as a fallback); the blog finds the post carrying the same
`notion_id` at build time. So editing a linked post never requires
re-syncing the directory -- only editing the directory itself does.

    # A. 출력만으로 판별            -> section "A. 출력만으로 판별"
    - @[paper #19] ...             ->   item (id, title)
    - @[paper #20] ... 핵심만 정리   ->   item (id, title, note "핵심만 정리")
    ## black-box                   ->   label row inside the section
    plain paragraph                ->   section note

The shallowest heading level used on the page is the column boundary, so a
page written with only `##` headings works the same as one using `#`.
Anything before the first heading is the page's intro.
"""

import html
import re

from . import richtext

_HEADINGS = {"heading_1": 1, "heading_2": 2, "heading_3": 3}
# Containers whose children are other pages' content, not this index's.
_NO_DESCEND = {"child_page", "child_database", "synced_block_reference"}
_HEX_ID = re.compile(r"([0-9a-fA-F]{32})(?![0-9a-fA-F])")
# Separators a bullet keeps once the link text is taken out of it.
_STRIP = " \t\n-–—:·|,/"


def _dashed(hex32: str) -> str:
    h = hex32.lower()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _walk(source, blocks):
    """Every block in document order, each block's children right after it."""
    for block in blocks:
        yield block
        if block.get("has_children") and block["type"] not in _NO_DESCEND:
            yield from _walk(source, source.get_block_children(block["id"]))


def _page_link(seg: dict) -> str | None:
    """The dashed page id a rich-text segment points at, if any."""
    mention = seg.get("mention") or {}
    if seg.get("type") == "mention" and mention.get("type") == "page":
        return mention["page"]["id"]
    href = seg.get("href") or ""
    # Inline links to a workspace page come back absolute (notion.so / app.
    # notion.com) or relative ("/<id>"). Anything else is an external link.
    if href.startswith("/") or richtext._is_workspace_url(href):
        hit = _HEX_ID.findall(href.split("?")[0].split("#")[0].replace("-", ""))
        if hit:
            return _dashed(hit[-1])
    return None


def _split_links(rich_text: list[dict]):
    """([(page id, label), ...], leftover plain text) for one block."""
    links, rest = [], []
    for seg in rich_text:
        page_id = _page_link(seg)
        if page_id:
            links.append((page_id, (seg.get("plain_text") or "").lstrip("‣").strip()))
        else:
            rest.append(seg.get("plain_text") or "")
    return links, " ".join("".join(rest).split()).strip(_STRIP)


def _page_title(source, page_id: str) -> str:
    """Title of a linked page, for link_to_page blocks (which carry none)."""
    try:
        page = source.get_page(page_id)
    except Exception:  # not shared with the integration, deleted, ...
        return ""
    for value in page.get("properties", {}).values():
        if value.get("type") == "title":
            return richtext.plain(value["title"]).strip()
    return ""


def collect(source, page_id: str):
    """(intro, sections) for a directory page. Network: the page's blocks."""
    blocks = list(_walk(source, source.get_block_children(page_id)))
    levels = [_HEADINGS[b["type"]] for b in blocks if b["type"] in _HEADINGS]
    top = min(levels) if levels else None

    intro: list[str] = []
    sections: list[dict] = []

    def current() -> dict:
        # Links above the first heading still need a column to sit in.
        if not sections:
            sections.append({"title": "", "note": "", "items": []})
        return sections[-1]

    def add(page, title, note=""):
        if page == page_id:
            return  # the directory linking to itself
        section = current()
        if any(item.get("id") == page for item in section["items"]):
            return
        item = {"id": page, "title": title or _page_title(source, page) or "Untitled"}
        if note:
            item["note"] = note
        section["items"].append(item)

    for block in blocks:
        kind = block["type"]
        data = block.get(kind) or {}

        if kind in _HEADINGS:
            text = richtext.plain(data.get("rich_text", [])).strip()
            if _HEADINGS[kind] == top:
                sections.append({"title": text, "note": "", "items": []})
            elif text:
                current()["items"].append({"label": text})
            continue

        if kind == "link_to_page":
            if data.get("type") == "page_id" and data.get("page_id"):
                add(data["page_id"], "")
            continue

        links, rest = _split_links(data.get("rich_text", []))
        if links:
            # Text beside a single link is that post's note ("— 핵심만 정리");
            # beside several it is just separators, so it is dropped.
            for linked_id, label in links:
                add(linked_id, label, rest if len(links) == 1 else "")
        elif rest:
            if sections:
                section = sections[-1]
                section["note"] = f"{section['note']} {rest}".strip()
            else:
                intro.append(rest)

    return " ".join(intro), sections


def render_body(intro: str, sections: list[dict]) -> str:
    """A plain markdown version of the board.

    The directory layout draws the board from front matter, so this body is
    only what non-layout consumers see: the RSS feed, search, excerpts.
    """
    esc = lambda text: html.escape(text, quote=False)
    out = [esc(intro)] if intro else []
    for section in sections:
        if section["title"]:
            out.append(f"## {esc(section['title'])}")
        if section.get("note"):
            out.append(esc(section["note"]))
        lines = []
        for item in section["items"]:
            if "label" in item:
                lines.append(f"- <strong>{esc(item['label'])}</strong>")
            else:
                note = f" — {esc(item['note'])}" if item.get("note") else ""
                lines.append(f"- {esc(item['title'])}{note}")
        if lines:
            out.append("\n".join(lines))
    return "\n\n".join(out) + "\n"
