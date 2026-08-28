"""Convert a Notion block tree into a blog-flavored markdown body.

Maps Notion blocks to the blog's custom components (box-*, <details> toggles,
text-*/highlight-* spans, GFM tables, MathJax math, <figure> images) so the
output matches the existing hand-written posts.
"""

import html
from urllib.parse import urlparse

from . import richtext
from .mappings import (HEADING_PREFIX, BOX_DEFAULT_EMOJI, callout_box_class,
                       toggle_color_class)

# Blocks where we inject inline `text` we can wrap with a comment highlight.
_COMMENTABLE = {
    "paragraph", "heading_1", "heading_2", "heading_3",
    "bulleted_list_item", "numbered_list_item", "to_do",
    "toggle", "callout", "quote",
}
_LIST_ITEMS = {"bulleted_list_item", "numbered_list_item", "to_do"}
_MEDIA = {"video", "embed", "bookmark", "link_preview"}

# Share pages jekyll-spaceship cannot auto-embed (it knows youtube, vimeo,
# dailymotion, spotify and soundcloud only). For these the page is fetched and
# its Open Graph metadata gives the direct media URL.
_OG_EMBED_HOSTS = ("tenor.com",)
_SKIP = {"table_of_contents", "breadcrumb", "child_page", "child_database"}


class Converter:
    def __init__(self, source, asset_dir, web_image_base, slug, with_comments=True):
        self.source = source
        self.asset_dir = asset_dir
        self.web_image_base = web_image_base.rstrip("/")
        self.slug = slug
        self.with_comments = with_comments
        self._anchors: dict[str, str] = {}
        self._colors: dict[str, list[list[str]]] = {}

    # --- public --------------------------------------------------------
    def convert(self, page_id: str) -> str:
        self._colors = self.source.get_color_overrides(page_id)
        if self.with_comments:
            self._anchors = self.source.get_comment_anchors(page_id)
        blocks = self.source.get_block_children(page_id)
        body = self._render_blocks(blocks, indent=0)

        appendix = self._page_comments(page_id)
        if appendix:
            body += "\n\n" + appendix
        return body.strip() + "\n"

    # --- block dispatch ------------------------------------------------
    def _render_blocks(self, blocks: list[dict], indent: int) -> str:
        """Join rendered blocks, keeping consecutive list items tight.

        A blank line between list items makes kramdown emit a "loose" list,
        wrapping every item in a <p> and adding paragraph margins -- which
        reads far airier than the hand-written posts. One newline keeps the
        list tight; everything else still gets a blank line.
        """
        out: list[str] = []
        prev_is_list = False
        for block in blocks:
            text = self._render_block(block, indent)
            if not text.strip():
                continue
            is_list = block.get("type") in _LIST_ITEMS
            if out:
                out.append("\n" if (is_list and prev_is_list) else "\n\n")
            out.append(text)
            prev_is_list = is_list
        return "".join(out)

    def _children(self, block: dict) -> list[dict]:
        if not block.get("has_children"):
            return []
        return self.source.get_block_children(block["id"])

    def _render_block(self, block: dict, indent: int) -> str:
        t = block["type"]
        data = block[t]
        pad = "  " * indent

        if t in _SKIP:
            return ""

        text = richtext.render(data.get("rich_text", []),
                               self._colors.get(block["id"]))
        if t in _COMMENTABLE:
            text = self._wrap_comment(block["id"], text)

        if t == "paragraph":
            return self._with_children(block, pad + text, indent)

        if t in HEADING_PREFIX:
            return self._with_children(
                block, f"{HEADING_PREFIX[t]} {text}", indent)

        if t == "bulleted_list_item":
            return self._list_item(block, indent, f"{pad}- {text}")
        if t == "numbered_list_item":
            return self._list_item(block, indent, f"{pad}1. {text}")
        if t == "to_do":
            mark = "x" if data.get("checked") else " "
            return self._list_item(block, indent, f"{pad}- [{mark}] {text}")

        if t == "toggle":
            return self._toggle(block, text)
        if t == "callout":
            return self._callout(block, data, text)
        if t == "quote":
            return self._quote(block, text)

        if t == "code":
            lang = data.get("language", "") or ""
            content = richtext.plain(data.get("rich_text", []))
            return f"```{lang}\n{content}\n```"

        if t == "equation":
            return f"$$\n{data.get('expression', '')}\n$$"

        if t == "divider":
            return "---"

        if t == "image":
            return self._image(block, data)

        if t == "table":
            return self._table(block, data)

        if t in _MEDIA:
            return self._media(t, data)

        if t in ("column_list", "column", "synced_block"):
            return self._render_blocks(self._children(block), indent)

        # Unhandled type: surface its plain text rather than dropping silently.
        return pad + text

    def _with_children(self, block: dict, rendered: str, indent: int) -> str:
        """Append blocks nested under a paragraph or heading.

        Notion allows nesting there, and dropping the children silently lost
        whole subtrees. They are emitted as siblings rather than indented:
        indenting a non-list block in markdown turns it into a code block.
        """
        children = self._children(block)
        if not children:
            return rendered
        return rendered + "\n\n" + self._render_blocks(children, indent)

    # --- composite blocks ---------------------------------------------
    def _list_item(self, block: dict, indent: int, line: str) -> str:
        children = self._children(block)
        if not children:
            return line
        return line + "\n" + self._render_blocks(children, indent + 1)

    def _toggle(self, block: dict, summary: str) -> str:
        # markdown="span" so links inside the summary still resolve; the
        # body div keeps markdown="1" because it holds block-level content.
        inner = self._render_blocks(self._children(block), 0)
        # An untitled Notion toggle would render as a bare disclosure
        # triangle with no clickable label.
        summary = summary.strip() or "더보기"
        # A Notion toggle can carry a block colour; the blog paints it on the
        # open panel only, so a closed toggle stays flush with the page.
        color_cls = toggle_color_class((block.get("toggle") or {}).get("color"))
        opening = f'<details class="{color_cls}">' if color_cls else "<details>"
        return (
            opening + "\n"
            f'<summary markdown="span">{summary}</summary>\n'
            '<div class="toggle-content" markdown="1">\n\n'
            f"{inner}\n\n"
            "</div>\n"
            "</details>"
        )

    def _callout(self, block: dict, data: dict, text: str) -> str:
        box = callout_box_class(data.get("color", "default"))
        icon_obj = data.get("icon") or {}
        emoji = icon_obj.get("emoji") if icon_obj.get("type") == "emoji" else None
        icon = emoji or BOX_DEFAULT_EMOJI.get(box, "💡")

        body = f"{icon} {text}"
        children = self._children(block)
        if children:
            body += "\n\n" + self._render_blocks(children, 0)
        return f'<div class="{box}" markdown="1">\n{body}\n</div>'

    def _quote(self, block: dict, text: str) -> str:
        # Notion quotes render as the blog's yellow box (box-warning), which
        # keeps inner text styling, instead of the default gray blockquote.
        body = text
        children = self._children(block)
        if children:
            body += "\n\n" + self._render_blocks(children, 0)
        return f'<div class="box-warning" markdown="1">\n{body}\n</div>'

    def _image(self, block: dict, data: dict) -> str:
        src = data.get("external", {}).get("url") if data.get("type") == "external" \
            else data.get("file", {}).get("url")
        if not src:
            return ""
        # Name the file after the image BLOCK id, not its position. A counter
        # renames every file whenever an image is added, removed or reordered
        # in Notion, so a re-run silently overwrites the wrong asset and
        # leaves orphans behind. Block ids survive all three.
        stem = block.get("id", "").replace("-", "")[:8] or "img"
        filename = self.source.download_image(
            src, self.asset_dir, f"{self.slug}-{stem}"
        )
        web_path = f"{self.web_image_base}/{filename}"

        # alt is an HTML attribute, so it takes plain text; the visible
        # caption keeps its formatting (bold, colors, links).
        #
        # markdown="span" goes on the figcaption, NOT markdown="1" on the
        # figure: the blog styles images with `figure > img`, and markdown="1"
        # makes kramdown wrap the img in a <p>, which breaks that selector and
        # adds a paragraph margin above the caption.
        return self._figure(web_path, data.get("caption", []))

    def _figure(self, src: str, rich_caption: list) -> str:
        """<figure> when there is a caption, a plain image otherwise.

        Shared by images and by embeds resolved to a direct media URL, so a
        captioned GIF keeps its caption just like a captioned screenshot.
        """
        alt = richtext.plain(rich_caption).strip()
        caption = richtext.render(rich_caption).strip()
        if not caption:
            return f"![]({src})"
        return (
            '<figure style="text-align: center;">\n'
            f'    <img src="{src}" alt="{html.escape(alt, quote=True)}">\n'
            '    <figcaption style="font-size: 0.9em; color: gray; margin-top: 5px;"'
            f' markdown="span">{caption}</figcaption>\n'
            "</figure>"
        )

    def _table(self, block: dict, data: dict) -> str:
        rows = self._children(block)
        if not rows:
            return ""

        def cells(row):
            return [
                richtext.render(c).replace("|", "\\|")
                for c in row["table_row"]["cells"]
            ]

        grid = [cells(r) for r in rows]
        width = max(len(r) for r in grid)
        grid = [r + [""] * (width - len(r)) for r in grid]

        if data.get("has_column_header"):
            header, body = grid[0], grid[1:]
        else:
            header, body = [""] * width, grid

        out = ["| " + " | ".join(header) + " |",
               "| " + " | ".join(["---"] * width) + " |"]
        for r in body:
            out.append("| " + " | ".join(r) + " |")
        return "\n".join(out)

    def _media(self, t: str, data: dict) -> str:
        if t == "bookmark" or t == "link_preview":
            url = data.get("url", "")
        elif t == "embed":
            url = data.get("url", "")
        else:  # video
            url = data.get("external", {}).get("url") if data.get("type") == "external" \
                else data.get("file", {}).get("url", "")
        if url and self._og_embeddable(url):
            direct = self.source.resolve_og_media(url)
            if direct:
                # Link, not download: the same rule the banner follows.
                return self._figure(direct, data.get("caption", []))

        # A bare URL on its own line lets jekyll-spaceship auto-embed media.
        return url or ""

    @staticmethod
    def _og_embeddable(url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == h or host.endswith("." + h) for h in _OG_EMBED_HOSTS)

    # --- comments ------------------------------------------------------
    @staticmethod
    def _esc(s: str) -> str:
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return s.replace("\n", "<br>")

    def _comment_span(self, inner: str, comments: list[dict]) -> str:
        items = "".join(
            f'<span class="comment-item">💬 '
            f'{self._esc(richtext.plain(c.get("rich_text", [])).strip())}</span>'
            for c in comments
        )
        bubble = f'<span class="comment-bubble">{items}</span>'
        return f'<span class="notion-comment">{inner}{bubble}</span>'

    def _wrap_comment(self, block_id: str, text: str) -> str:
        """Highlight commented text; the comment shows in a hover bubble.

        Prefers the exact anchored range (from get_comment_anchors). Falls back
        to highlighting the whole block when any of its comments can't be
        placed -- an un-shared page, an anchor split across formatting runs, or
        overlapping ranges. Nesting .notion-comment spans would break the hover
        script, so it is all-or-nothing per block.
        """
        if not self.with_comments:
            return text
        comments = self.source.get_comments(block_id)
        if not comments:
            return text

        by_discussion: dict[str, list[dict]] = {}
        for c in comments:
            by_discussion.setdefault(c.get("discussion_id"), []).append(c)

        spans: list[tuple[int, int, list[dict]]] = []
        for did, group in by_discussion.items():
            anchor = self._anchors.get(did)
            start = text.find(anchor) if anchor else -1
            if start < 0:
                spans = []
                break
            spans.append((start, start + len(anchor), group))

        spans.sort()
        disjoint = all(spans[i][1] <= spans[i + 1][0] for i in range(len(spans) - 1))
        if spans and disjoint:
            out, cursor = [], 0
            for start, end, group in spans:
                out.append(text[cursor:start])
                out.append(self._comment_span(text[start:end], group))
                cursor = end
            out.append(text[cursor:])
            return "".join(out)

        return self._comment_span(text, comments)

    def _page_comments(self, page_id: str) -> str:
        if not self.with_comments:
            return ""
        comments = self.source.get_comments(page_id)
        if not comments:
            return ""
        lines = ['<div class="box-note" markdown="1">', "💬 **페이지 댓글**", ""]
        for c in comments:
            body = richtext.plain(c.get("rich_text", [])).strip()
            lines.append(f"- {body}")
        lines.append("</div>")
        return "\n".join(lines)
