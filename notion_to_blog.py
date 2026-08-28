#!/usr/bin/env python3
"""Convert a Notion page into a Jekyll post for cityofwonder.github.io.

Front matter comes from the page's database properties (filename, subtitle,
categories, tags, banner), so a fully-filled page needs no flags.

Usage:
    python notion_to_blog.py <notion-page-url-or-id> [--blog-dir DIR] [--no-comments]

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
    parser.add_argument("--blog-dir", default="../cityofwonder.github.io",
                        help="Blog repo root. Post -> <dir>/_posts, images -> "
                             "<dir>/assets/images/<date> (default: ../cityofwonder.github.io). "
                             "Pass a staging dir like ./output to review before publishing.")
    parser.add_argument("--no-comments", action="store_true", help="Skip Notion comments")
    parser.add_argument("--slug", help="Override the post slug, e.g. a casual English "
                                       "translation (default transliterates the title)")
    parser.add_argument("--title", help="Override the post title")
    args = parser.parse_args()

    page_id = extract_page_id(args.page)
    source = NotionSource()

    page = source.get_page(page_id)
    meta = frontmatter.collect(page, slug_override=args.slug, title_override=args.title)
    date, slug = meta["date"], meta["slug"]

    blog_dir = args.blog_dir
    # Images are written into the blog repo; the markdown references the path
    # the blog serves them from (/assets/images/<date>/...).
    asset_dir = os.path.join(blog_dir, "assets", "images", date)
    web_image_base = f"/assets/images/{date}"

    # A Notion-hosted banner is behind a URL that expires within the hour, so
    # it has to land in the repo. An external one stays a link.
    banner_image = meta["banner_url"] or ""
    if banner_image and meta["banner_hosted"]:
        banner_file = source.download_image(banner_image, asset_dir, f"{slug}-banner")
        banner_image = f"{web_image_base}/{banner_file}"
    front = frontmatter.render(meta, banner_image)

    converter = Converter(
        source=source,
        asset_dir=asset_dir,
        web_image_base=web_image_base,
        slug=slug,
        with_comments=not args.no_comments,
    )
    body = converter.convert(page_id)

    posts_dir = os.path.join(blog_dir, "_posts")
    os.makedirs(posts_dir, exist_ok=True)
    post_path = os.path.join(posts_dir, f"{date}-{slug}.md")
    with open(post_path, "w", encoding="utf-8") as f:
        f.write(front + "\n" + body)

    source_note = "filename 속성" if meta["from_filename_prop"] else "created_time + 제목"
    print(f"✅ Wrote {post_path}  ({source_note} 기준)")
    if os.path.isdir(asset_dir) and os.listdir(asset_dir):
        print(f"🖼  Images -> {asset_dir}")
    print(f"→ Review, then commit in {blog_dir} (git add _posts assets).")


if __name__ == "__main__":
    main()
