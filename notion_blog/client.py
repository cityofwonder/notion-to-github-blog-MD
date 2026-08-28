"""Thin wrapper around the Notion SDK with the helpers the converter needs."""

import os
import re
import mimetypes
from urllib.parse import urlparse

import requests
from notion_client import Client

_INTERNAL_API = "https://www.notion.so/api/v3"

# Tenor serves a bot-hostile 403 to the requests default UA.
_UA = "Mozilla/5.0 (compatible; notion-to-blog/1.0)"


class NotionSource:
    def __init__(self, token: str | None = None):
        token = token or os.environ.get("NOTION_TOKEN")
        if not token:
            raise RuntimeError(
                "NOTION_TOKEN is not set. Create an internal integration at "
                "https://www.notion.so/my-integrations, share the page with it, "
                "and export NOTION_TOKEN."
            )
        self.client = Client(auth=token)
        self._chunk_cache: dict[str, dict] = {}

    # --- internal (undocumented) endpoint -------------------------------
    def _page_chunk(self, page_id: str) -> dict:
        """recordMap from notion.so/api/v3/loadPageChunk, or {} if unavailable.

        Serves any page that has a public share link, without auth. Used only
        for the two things the documented API does not expose: the exact text a
        comment is anchored to, and the second colour on a span that carries
        both a text colour and a highlight. Every caller must degrade
        gracefully -- this endpoint is not part of Notion's contract.
        """
        if page_id in self._chunk_cache:
            return self._chunk_cache[page_id]
        record_map = {}
        try:
            resp = requests.post(
                f"{_INTERNAL_API}/loadPageChunk",
                json={
                    "pageId": page_id,
                    "limit": 300,
                    "cursor": {"stack": []},
                    "chunkNumber": 0,
                    "verticalColumns": False,
                },
                timeout=20,
            )
            resp.raise_for_status()
            record_map = resp.json()["recordMap"]
        except (requests.RequestException, ValueError, KeyError):
            record_map = {}
        self._chunk_cache[page_id] = record_map
        return record_map

    @staticmethod
    def _unwrap(record):
        record = record.get("value", record)
        if isinstance(record, dict) and "value" in record:
            record = record["value"]
        return record

    # --- page + blocks -------------------------------------------------
    def get_page(self, page_id: str) -> dict:
        return self.client.pages.retrieve(page_id=page_id)

    def get_block_children(self, block_id: str) -> list[dict]:
        """Return all direct children of a block, following pagination."""
        blocks: list[dict] = []
        cursor = None
        while True:
            resp = self.client.blocks.children.list(
                block_id=block_id, start_cursor=cursor, page_size=100
            )
            blocks.extend(resp["results"])
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
        return blocks

    # --- comments ------------------------------------------------------
    def get_comment_anchors(self, page_id: str) -> dict[str, str]:
        """Map discussion_id -> the exact text the comment is anchored to.

        The public API gives comments only at block granularity, so a comment
        on two words would highlight the whole paragraph. Notion's own web
        client gets the character range from an internal endpoint, which
        serves any page that has a public share link -- no auth involved.

        Returns {} whenever that is unavailable (page not shared publicly,
        endpoint changed, network down); the caller then falls back to
        block-level highlighting.
        """
        anchors: dict[str, str] = {}
        for did, record in self._page_chunk(page_id).get("discussion", {}).items():
            value = self._unwrap(record)
            context = value.get("context")
            if not context:
                continue  # page-level comment: no in-text anchor
            text = "".join(
                seg[0] for seg in context if isinstance(seg, list) and seg
            ).strip()
            if text:
                anchors[did] = text
        return anchors

    def get_color_overrides(self, page_id: str) -> dict[str, list[list[str]]]:
        """block id -> per-segment list of Notion colour names.

        Notion lets one span carry a text colour *and* a highlight, but the
        documented API flattens `annotations.color` to a single value, so the
        other one is lost. The internal record keeps both, indexed the same way
        the API segments the text.
        """
        overrides: dict[str, list[list[str]]] = {}
        for bid, record in self._page_chunk(page_id).get("block", {}).items():
            value = self._unwrap(record)
            title = (value.get("properties") or {}).get("title")
            if not title:
                continue
            colors = [
                [a[1] for a in (seg[1] if len(seg) > 1 else []) if a[0] == "h"]
                for seg in title if isinstance(seg, list)
            ]
            if any(len(c) > 1 for c in colors):
                overrides[bid] = colors
        return overrides

    def get_comments(self, block_id: str) -> list[dict]:
        """Return unresolved comments anchored to a page or block.

        Notion's API only exposes unresolved comments and only at block-level
        granularity; pair this with get_comment_anchors() for the exact range.
        """
        comments: list[dict] = []
        cursor = None
        while True:
            resp = self.client.comments.list(block_id=block_id, start_cursor=cursor)
            comments.extend(resp["results"])
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
        return comments

    # --- embeds --------------------------------------------------------
    @staticmethod
    def resolve_og_media(url: str) -> str | None:
        """The direct media URL behind a share page, from its og:image tag.

        Tenor (and friends) hand Notion a page URL, which jekyll-spaceship
        cannot auto-embed -- it only knows youtube/vimeo/dailymotion/spotify/
        soundcloud. The page's Open Graph metadata points at the real .gif.
        Returns None on any failure so the caller can fall back to the link.
        """
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": _UA})
            resp.raise_for_status()
        except requests.RequestException:
            return None

        for prop in ("og:image", "og:video"):
            for tag in re.findall(r"<meta[^>]*>", resp.text):
                if f'"{prop}"' not in tag and f"'{prop}'" not in tag:
                    continue
                m = re.search(r"""content=["']([^"']+)["']""", tag)
                if m and m.group(1).startswith("http"):
                    return m.group(1)
        return None

    # --- assets --------------------------------------------------------
    @staticmethod
    def download_image(url: str, dest_dir: str, basename: str) -> str:
        """Download an image to dest_dir, returning the saved file's basename."""
        os.makedirs(dest_dir, exist_ok=True)
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()

        ext = os.path.splitext(urlparse(url).path)[1]
        if not ext:
            ext = mimetypes.guess_extension(
                resp.headers.get("Content-Type", "").split(";")[0].strip()
            ) or ".png"

        safe = re.sub(r"[^A-Za-z0-9_-]", "-", basename).strip("-") or "image"
        filename = f"{safe}{ext}"
        with open(os.path.join(dest_dir, filename), "wb") as f:
            f.write(resp.content)
        return filename
