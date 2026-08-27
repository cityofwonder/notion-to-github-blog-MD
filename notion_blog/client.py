"""Thin wrapper around the Notion SDK with the helpers the converter needs."""

import os
import re
import mimetypes
from urllib.parse import urlparse

import requests
from notion_client import Client

_INTERNAL_API = "https://www.notion.so/api/v3"


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
            discussions = resp.json()["recordMap"].get("discussion", {})
        except (requests.RequestException, ValueError, KeyError):
            return {}

        anchors: dict[str, str] = {}
        for did, record in discussions.items():
            value = record.get("value", record)
            value = value.get("value", value)
            context = value.get("context")
            if not context:
                continue  # page-level comment: no in-text anchor
            text = "".join(
                seg[0] for seg in context if isinstance(seg, list) and seg
            ).strip()
            if text:
                anchors[did] = text
        return anchors

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
