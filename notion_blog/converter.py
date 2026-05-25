"""Convert a Notion block tree into a blog-flavored markdown body.

Maps Notion blocks to the blog's custom components (box-*, <details> toggles,
text-*/highlight-* spans, GFM tables, MathJax math, <figure> images) so the
output matches the existing hand-written posts.
"""

from . import richtext
from .mappings import HEADING_PREFIX, BOX_DEFAULT_EMOJI, callout_box_class

# Blocks where we inject inline `text` we can wrap with a comment highlight.
_COMMENTABLE = {
    "paragraph", "heading_1", "heading_2", "heading_3",
    "bulleted_list_item", "numbered_list_item", "to_do",
    "toggle", "callout", "quote",
}
_MEDIA = {"video", "embed", "bookmark", "link_preview"}
_SKIP = {"table_of_contents", "breadcrumb", "child_page", "child_database"}


class Converter:
    def __init__(self, source, asset_dir, web_image_base, slug, with_comments=True):
        self.source = source
        self.asset_dir = asset_dir
        self.web_image_base = web_image_base.rstrip("/")
        self.slug = slug
        self.with_comments = with_comments
        self._img_n = 0

    # --- public --------------------------------------------------------
    def convert(self, page_id: str) -> str:
        blocks = self.source.get_block_children(page_id)
        body = self._render_blocks(blocks, indent=0)

        appendix = self._page_comments(page_id)
        if appendix:
            body += "\n\n" + appendix
        return body.strip() + "\n"

    # --- block dispatch ------------------------------------------------
    def _render_blocks(self, blocks: list[dict], indent: int) -> str:
        parts = [self._render_block(b, indent) for b in blocks]
        return "\n\n".join(p for p in parts if p.strip())

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

        text = richtext.render(data.get("rich_text", []))
        if t in _COMMENTABLE:
            text = self._wrap_comment(block["id"], text)

        if t == "paragraph":
            return pad + text

        if t in HEADING_PREFIX:
            return f"{HEADING_PREFIX[t]} {text}"

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
            return self._image(data)

        if t == "table":
            return self._table(block, data)

        if t in _MEDIA:
            return self._media(t, data)

        if t in ("column_list", "column", "synced_block"):
            return self._render_blocks(self._children(block), indent)

        # Unhandled type: surface its plain text rather than dropping silently.
        return pad + text

    # --- composite blocks ---------------------------------------------
    def _list_item(self, block: dict, indent: int, line: str) -> str:
        children = self._children(block)
        if not children:
            return line
        return line + "\n" + self._render_blocks(children, indent + 1)

    def _toggle(self, block: dict, summary: str) -> str:
        inner = self._render_blocks(self._children(block), 0)
        return (
            "<details>\n"
            f"<summary>{summary}</summary>\n"
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

    def _image(self, data: dict) -> str:
        src = data.get("external", {}).get("url") if data.get("type") == "external" \
            else data.get("file", {}).get("url")
        if not src:
            return ""
        self._img_n += 1
        filename = self.source.download_image(
            src, self.asset_dir, f"{self.slug}-{self._img_n}"
        )
        web_path = f"{self.web_image_base}/{filename}"
        caption = richtext.plain(data.get("caption", []))
        if caption:
            return (
                '<figure style="text-align: center;">\n'
                f'    <img src="{web_path}" alt="{caption}">\n'
                '    <figcaption style="font-size: 0.9em; color: gray; margin-top: 5px;">'
                f"{caption}</figcaption>\n"
                "</figure>"
            )
        return f"![]({web_path})"

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
        # A bare URL on its own line lets jekyll-spaceship auto-embed media.
        return url or ""

    # --- comments ------------------------------------------------------
    @staticmethod
    def _esc(s: str) -> str:
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return s.replace("\n", "<br>")

    def _wrap_comment(self, block_id: str, text: str) -> str:
        """Highlight commented text; the comment shows in a hover bubble.

        Notion only anchors comments at block level, so the whole block's text
        is the hover target (no in-text character range available).
        """
        if not self.with_comments:
            return text
        comments = self.source.get_comments(block_id)
        if not comments:
            return text
        items = "".join(
            f'<span class="comment-item">💬 '
            f'{self._esc(richtext.plain(c.get("rich_text", [])).strip())}</span>'
            for c in comments
        )
        bubble = f'<span class="comment-bubble">{items}</span>'
        return f'<span class="notion-comment">{text}{bubble}</span>'

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
