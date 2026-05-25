#!/usr/bin/env python3
"""Convert a Notion page into a Jekyll post for cityofwonder.github.io.

Usage:
    python notion_to_blog.py <notion-page-url-or-id> [--output DIR] [--no-comments]

Output layout (under --output, default ./output):
    _posts/<date>-<slug>.md
    assets/images/<date>/<image files>

Copy those two trees into the blog repo to publish.
"""

import os
import re
import sys
import argparse

from dotenv import load_dotenv

from notion_blog.client import NotionSource
from notion_blog.converter import Converter
from notion_blog import frontmatter


def extract_page_id(value: str) -> str:
    """Pull a 32-char hex id out of a Notion URL or id and dash-format it."""
    m = re.search(r"([0-9a-fA-F]{32})", value.replace("-", ""))
    if not m:
        raise SystemExit(f"Could not find a Notion page id in: {value}")
    h = m.group(1).lower()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Notion -> Jekyll post converter")
    parser.add_argument("page", help="Notion page URL or id")
    parser.add_argument("--output", default="output", help="Output directory (default: output)")
    parser.add_argument("--no-comments", action="store_true", help="Skip Notion comments")
    parser.add_argument("--slug", help="Override the post slug, e.g. a casual English "
                                       "translation (default transliterates the title)")
    parser.add_argument("--title", help="Override the post title")
    args = parser.parse_args()

    page_id = extract_page_id(args.page)
    source = NotionSource()

    page = source.get_page(page_id)
    front, meta = frontmatter.build(page, slug_override=args.slug, title_override=args.title)
    date, slug = meta["date"], meta["slug"]

    asset_dir = os.path.join(args.output, "assets", "images", date)
    web_image_base = f"/assets/images/{date}"

    converter = Converter(
        source=source,
        asset_dir=asset_dir,
        web_image_base=web_image_base,
        slug=slug,
        with_comments=not args.no_comments,
    )
    body = converter.convert(page_id)

    posts_dir = os.path.join(args.output, "_posts")
    os.makedirs(posts_dir, exist_ok=True)
    post_path = os.path.join(posts_dir, f"{date}-{slug}.md")
    with open(post_path, "w", encoding="utf-8") as f:
        f.write(front + "\n" + body)

    print(f"✅ Wrote {post_path}")
    if os.path.isdir(asset_dir) and os.listdir(asset_dir):
        print(f"🖼  Images in {asset_dir}")
    print("→ Copy _posts/ and assets/ into the blog repo to publish.")


if __name__ == "__main__":
    main()
