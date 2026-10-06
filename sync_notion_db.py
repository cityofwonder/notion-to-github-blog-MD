#!/usr/bin/env python3
"""Sync a whole Notion database into the blog's _posts.

    python sync_notion_db.py <database-url-or-id> [--blog-dir DIR] [--yes]

Dry run by default: it queries the database, works out what it would do to each
row, prints the plan and stops. Pass --yes to actually convert and write.

Rules
-----
제목 없음          건너뜀.
`layout` 에 post   보통의 `_posts/<date>-<slug>.md`.
`layout` 비어 있음 `_posts/draft_<date>-<slug>.md` — Jekyll 이 무시하는 이름이라
                   발행되지 않는다. 나중에 Notion 에서 layout 을 post 로 바꾸면
                   다음 싱크에서 draft_ 가 떨어진다.

Rows are matched to files by the `notion_id` the converter writes into front
matter, never by filename -- so renaming a page in Notion moves the existing
file instead of leaving a duplicate behind. A row whose `notion_synced` still
matches Notion's `last_edited_time` is skipped without fetching its blocks,
which is what makes a re-sync quick.
"""

import argparse
import os
import re
import subprocess
import sys

from dotenv import load_dotenv

from notion_blog.client import NotionSource
from notion_blog.converter import Converter
from notion_blog import frontmatter

# The sibling blog repo, resolved against THIS FILE rather than the shell's
# working directory -- running the script from one level up used to point at a
# path that does not exist.
DEFAULT_BLOG_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "cityofwonder.github.io"))


# Anchor on the END of a hex run so a trailing hex letter in the slug
# ("...kpwnot*e*-<id>") is not glued onto the front, shifting the whole id.
ID_RE = re.compile(r"([0-9a-fA-F]{32})(?![0-9a-fA-F])")
FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)

# Written back to Notion once a row has a file on disk. Must match an existing
# option on the 상태 select exactly, or Notion creates a duplicate option.
COMMITTED_STATUS = "커밋완료"


def dashed(hex32):
    h = hex32.lower()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def extract_db_id(value):
    """The database id is the 32-hex run at the end of the path (before `?v=`)."""
    head = value.split("?")[0].replace("-", "")
    matches = ID_RE.findall(head)
    if not matches:
        raise SystemExit(f"데이터베이스 id 를 찾을 수 없습니다: {value}")
    return dashed(matches[-1])


def read_front_matter(path):
    """`notion_id` / `notion_synced` out of a post, without a YAML dependency."""
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(4096)
    except OSError:
        return {}
    match = FRONT_MATTER_RE.match(head)
    if not match:
        return {}
    fields = {}
    for line in match.group(1).splitlines():
        hit = re.match(r"^(notion_id|notion_synced|status)\s*:\s*(.*)$", line)
        if hit:
            fields[hit.group(1)] = hit.group(2).strip().strip('"').strip("'")
    return fields


def index_existing(posts_dir):
    """notion_id -> path, for every post this tool already owns."""
    index = {}
    if not os.path.isdir(posts_dir):
        return index
    for name in os.listdir(posts_dir):
        if not name.endswith((".md", ".markdown")):
            continue
        path = os.path.join(posts_dir, name)
        notion_id = read_front_matter(path).get("notion_id")
        if notion_id:
            index[notion_id] = path
    return index


def query_rows(source, database_id):
    """Every page in the database, across API generations.

    Notion-Version 2025-09-03 moved querying off the database and onto its
    *data sources* (a database can have more than one), so `databases.query`
    no longer exists in the current SDK. Older versions only have the database
    endpoint, so try the new shape first and fall back.
    """
    client = source.client
    data_source_ids = []

    retrieve = getattr(client.databases, "retrieve", None)
    if retrieve and hasattr(client, "data_sources"):
        try:
            info = retrieve(database_id=database_id)
            data_source_ids = [ds["id"] for ds in info.get("data_sources", [])]
        except Exception as exc:  # not a database id, or not shared yet
            if "Could not find" in str(exc) or "object_not_found" in str(exc):
                raise SystemExit(
                    f"데이터베이스를 찾을 수 없습니다: {database_id}\n"
                    "Notion 에서 DB 페이지 ••• -> Connections 로 integration 을 "
                    "추가했는지 확인하세요."
                ) from exc
            data_source_ids = []

    def paged(fn, **kwargs):
        out, cursor = [], None
        while True:
            resp = fn(start_cursor=cursor, page_size=100, **kwargs)
            out.extend(resp["results"])
            if not resp.get("has_more"):
                return out
            cursor = resp.get("next_cursor")

    if data_source_ids:
        rows = []
        for ds_id in data_source_ids:
            rows.extend(paged(client.data_sources.query, data_source_id=ds_id))
        return rows

    if hasattr(client, "data_sources"):
        # The URL may already point at a data source rather than a database.
        return paged(client.data_sources.query, data_source_id=database_id)

    return paged(client.databases.query, database_id=database_id)


def run_git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def move_file(blog_dir, src, dst):
    """git mv when tracked so history follows the rename."""
    rel_src = os.path.relpath(src, blog_dir).replace(os.sep, "/")
    rel_dst = os.path.relpath(dst, blog_dir).replace(os.sep, "/")
    tracked = run_git(["ls-files", "--error-unmatch", rel_src], blog_dir).returncode == 0
    if tracked and run_git(["mv", "-f", rel_src, rel_dst], blog_dir).returncode == 0:
        return
    os.replace(src, dst)


def plan_row(page, index, posts_dir):
    """What should happen to one database row. No network, no writes."""
    meta = frontmatter.collect(page)
    if not meta["title"].strip():
        return {"action": "skip-untitled", "meta": meta, "page": page}

    prefix = "" if meta["is_post"] else "draft_"
    filename = f"{prefix}{meta['date']}-{meta['slug']}.md"
    target = os.path.join(posts_dir, filename)

    existing = index.get(meta["notion_id"])
    if existing is None:
        return {"action": "create", "meta": meta, "target": target, "page": page}

    synced = read_front_matter(existing).get("notion_synced", "")
    renamed = os.path.abspath(existing) != os.path.abspath(target)
    if synced and synced == meta["last_edited"] and not renamed:
        return {"action": "skip-unchanged", "meta": meta, "target": existing,
                "page": page}
    return {"action": "rename" if renamed else "update", "meta": meta,
            "target": target, "existing": existing, "page": page}


def status_property(page):
    """Name of the page's 상태 select property, or None."""
    for name, value in (page.get("properties") or {}).items():
        if name.strip().lower() in frontmatter.STATUS_ALIASES \
                and value.get("type") == "select":
            return name
    return None


def mark_committed(source, page):
    """Set 상태 to 커밋완료. Returns the property name, or None if unavailable."""
    prop = status_property(page)
    if not prop:
        return None
    source.client.pages.update(
        page_id=page["id"],
        properties={prop: {"select": {"name": COMMITTED_STATUS}}},
    )
    return prop


def find_orphans(index, live_ids):
    """Posts carrying a notion_id the database no longer returns.

    Covers a row deleted outright and one moved to the trash -- Notion's query
    skips archived pages, so both simply stop coming back.
    """
    return sorted((nid, path) for nid, path in index.items() if nid not in live_ids)


def prune_orphan(blog_dir, path):
    """Delete an orphaned post plus the assets nothing else references."""
    from cleanup_post import extract_assets, other_referrers, delete as delete_path

    with open(path, encoding="utf-8") as f:
        assets = extract_assets(f.read())
    removed = []
    for asset in assets:
        target = os.path.join(blog_dir, asset.lstrip("/").replace("/", os.sep))
        if not os.path.exists(target):
            continue
        if other_referrers(blog_dir, asset, os.path.abspath(path)):
            continue
        delete_path(blog_dir, target)
        removed.append(asset)
    delete_path(blog_dir, path)
    return removed


def write_post(source, meta, target, blog_dir, with_comments):
    """Convert one page and write it, returning the asset dir used."""
    date, slug = meta["date"], meta["slug"]
    asset_dir = os.path.join(blog_dir, "assets", "images", date)
    web_image_base = f"/assets/images/{date}"

    banner_image = meta["banner_url"] or ""
    if banner_image and meta["banner_hosted"]:
        banner_file = source.download_image(banner_image, asset_dir, f"{slug}-banner")
        banner_image = f"{web_image_base}/{banner_file}"

    converter = Converter(source=source, asset_dir=asset_dir,
                          web_image_base=web_image_base, slug=slug,
                          with_comments=with_comments)
    body = converter.convert(meta["notion_id"])

    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(frontmatter.render(meta, banner_image) + "\n" + body)
    return asset_dir


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Notion database -> _posts sync")
    parser.add_argument("database", help="데이터베이스 URL 또는 id")
    parser.add_argument("--blog-dir", default=DEFAULT_BLOG_DIR,
                        help="블로그 레포 루트 (기본: 이 스크립트 옆의 cityofwonder.github.io)")
    parser.add_argument("--yes", action="store_true",
                        help="실제로 변환/기록 (없으면 계획만 출력)")
    parser.add_argument("--force", action="store_true",
                        help="변경 없는 행도 다시 변환")
    parser.add_argument("--limit", type=int, help="앞의 N개 행만 처리 (시험용)")
    parser.add_argument("--no-comments", action="store_true", help="댓글 제외")
    parser.add_argument("--prune", action="store_true",
                        help="DB 에서 사라진 행의 글/전용 에셋 삭제")
    parser.add_argument("--update-status", action="store_true",
                        help=f"파일이 생긴 행 중 상태가 비어 있으면 Notion 을 "
                             f"{COMMITTED_STATUS} 로 설정")
    parser.add_argument("--status-only", action="store_true",
                        help="변환은 건너뛰고 상태 업데이트만 수행")
    args = parser.parse_args()
    if args.status_only:
        args.update_status = True

    blog_dir = os.path.abspath(args.blog_dir)
    posts_dir = os.path.join(blog_dir, "_posts")
    if not os.path.isdir(posts_dir):
        raise SystemExit(f"블로그 레포가 아닙니다: {blog_dir}")

    database_id = extract_db_id(args.database)
    source = NotionSource()

    rows = query_rows(source, database_id)
    if args.limit:
        rows = rows[:args.limit]

    index = index_existing(posts_dir)
    print(f"DB {database_id}  행 {len(rows)}개  |  이미 싱크된 글 {len(index)}개")
    print(f"대상 {posts_dir}\n")

    plans = [plan_row(page, index, posts_dir) for page in rows]
    if args.force:
        for plan in plans:
            if plan["action"] == "skip-unchanged":
                plan["action"] = "update"

    label = {"create": "[생성]", "update": "[갱신]", "rename": "[이름변경]",
             "skip-unchanged": "[변경없음]", "skip-untitled": "[건너뜀]"}
    for plan in plans:
        meta = plan["meta"]
        title = (meta["title"] or "(제목 없음)")[:42]
        name = os.path.basename(plan.get("target", "")) if plan.get("target") else "-"
        note = ""
        if plan["action"] == "rename":
            note = f"  ← {os.path.basename(plan['existing'])}"
        if plan["action"] == "skip-untitled":
            name = "-"
        draft = "" if meta.get("is_post") else "  (draft_)"
        print(f"  {label[plan['action']]:<10} {title:<44} {name}{draft}{note}")

    # Rows the database no longer returns (deleted, or moved to the trash).
    # Meaningless under --limit, which only looks at a slice of the database.
    orphans = []
    if not args.limit:
        orphans = find_orphans(index, {p["meta"]["notion_id"] for p in plans})
        for _, path in orphans:
            print(f"  [DB에 없음]  {'':<44} {os.path.basename(path)}")

    # Rows that now have a file and whose 상태 is still empty.
    to_commit = [p for p in plans
                 if p["action"] in ("create", "update", "rename", "skip-unchanged")
                 and not p["meta"].get("status")]
    if args.update_status:
        for plan in to_commit:
            print(f"  [상태변경]  {plan['meta']['title'][:42]:<44} "
                  f"→ {COMMITTED_STATUS}")

    counts = {}
    for plan in plans:
        counts[plan["action"]] = counts.get(plan["action"], 0) + 1
    summary = "  ".join(f"{label[k]} {v}" for k, v in sorted(counts.items()))
    if orphans:
        summary += f"  [DB에 없음] {len(orphans)}"
    print(f"\n{summary}")

    todo = [] if args.status_only else [
        p for p in plans if p["action"] in ("create", "update", "rename")]
    if not args.yes:
        print(f"\n계획만 출력했습니다. {len(todo)}건 쓰기"
              + (f", 상태 {len(to_commit)}건 변경" if args.update_status else "")
              + (f", 고아 글 {len(orphans)}건 삭제" if args.prune and orphans else "")
              + " 대상입니다.")
        if orphans and not args.prune:
            print("DB 에서 사라진 글도 지우려면 --prune 을 붙이세요.")
        print("실제로 반영하려면 --yes 를 붙이세요.")
        return

    print()
    for plan in todo:
        meta = plan["meta"]
        if plan["action"] == "rename":
            move_file(blog_dir, plan["existing"], plan["target"])
            print(f"  이동: {os.path.basename(plan['existing'])} "
                  f"→ {os.path.basename(plan['target'])}")
        write_post(source, meta, plan["target"], blog_dir,
                   with_comments=not args.no_comments)
        print(f"  {label[plan['action']]} {os.path.relpath(plan['target'], blog_dir)}")

    if args.prune:
        for _, path in orphans:
            removed = prune_orphan(blog_dir, path)
            print(f"  [삭제] {os.path.relpath(path, blog_dir)}"
                  f"  (에셋 {len(removed)}개 포함)")

    committed = 0
    if args.update_status:
        for plan in to_commit:
            try:
                if mark_committed(source, plan["page"]):
                    committed += 1
                    print(f"  [상태] {plan['meta']['title'][:42]} → {COMMITTED_STATUS}")
            except Exception as exc:
                print(f"  [상태 실패] {plan['meta']['title'][:42]}: {exc}")

    print(f"\n완료: {len(todo)}건 반영, "
          f"{counts.get('skip-unchanged', 0)}건 변경 없음, "
          f"{counts.get('skip-untitled', 0)}건 제목 없어 건너뜀"
          + (f", 고아 {len(orphans)}건 삭제" if args.prune and orphans else "")
          + (f", 상태 {committed}건 {COMMITTED_STATUS}" if args.update_status else "")
          + ".")
    renamed = [p for p in todo if p["action"] == "rename"]
    if renamed:
        print("\n이름이 바뀐 글의 예전 이미지가 남아 있을 수 있습니다:")
        for plan in renamed:
            print(f"  python cleanup_post.py {os.path.basename(plan['existing'])}")


if __name__ == "__main__":
    main()
