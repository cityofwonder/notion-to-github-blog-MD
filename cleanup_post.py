#!/usr/bin/env python3
"""Remove a converted post and the assets that only it uses.

Re-running the converter after renaming a post, or dropping a draft that was
already pulled over, leaves the markdown behind and its images stranded in
assets/images/<date>/. Deleting them by hand is where you accidentally take out
a banner another post is still pointing at.

Usage:
    python cleanup_post.py <post.md> [--blog-dir DIR] [--yes]

Dry run by default: it prints what it would remove and changes nothing. Pass
--yes to actually delete. Anything referenced from another file in the blog is
kept and reported instead.

    python cleanup_post.py 2026-06-04-TIL-MCP.md            # 확인만
    python cleanup_post.py 2026-06-04-TIL-MCP.md --yes      # 실제 삭제
"""

import argparse
import os
import re
import subprocess
import sys

# Directories that never hold a real reference (build output, vendored gems).
SKIP_DIRS = {".git", "_site", ".jekyll-cache", "node_modules", ".bundle",
             "vendor", ".venv", "venv", "__pycache__"}

# Only text files can reference an asset.
TEXT_EXT = {".md", ".markdown", ".html", ".htm", ".yml", ".yaml", ".scss",
            ".sass", ".css", ".js", ".json", ".txt", ".xml"}

# `/assets/...` shows up quoted (front matter, HTML attributes), inside
# markdown parentheses, or bare. Filenames may contain spaces, so the quoted
# and parenthesised forms are matched first and the bare form stops at a space.
ASSET_PATTERNS = [
    re.compile(r'"(/assets/[^"\n]+)"'),
    re.compile(r"'(/assets/[^'\n]+)'"),
    re.compile(r"\((/assets/[^)\n]+)\)"),
    re.compile(r"(/assets/[^\s\"'()<>\\\n]+)"),
]


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def resolve_post(blog_dir, name):
    """Accept a bare filename, a _posts-relative name, or a full path."""
    candidates = [
        os.path.join(blog_dir, "_posts", os.path.basename(name)),
        os.path.join(blog_dir, name),
        name,
    ]
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    raise SystemExit(
        f"'{name}' 을 찾을 수 없습니다. {os.path.join(blog_dir, '_posts')} 를 확인하세요."
    )


def extract_assets(text):
    found = set()
    for pattern in ASSET_PATTERNS:
        for match in pattern.findall(text):
            found.add(match.strip().rstrip(".,;"))
    # A quoted match and the bare match can disagree on where a path with a
    # space ends; keep the longest reading of each prefix.
    longest = []
    for path in sorted(found, key=len, reverse=True):
        if not any(other.startswith(path) for other in longest):
            longest.append(path)
    return sorted(longest)


def iter_text_files(blog_dir):
    for root, dirs, files in os.walk(blog_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if os.path.splitext(name)[1].lower() in TEXT_EXT:
                yield os.path.join(root, name)


def other_referrers(blog_dir, asset, exclude):
    """Files other than `exclude` that mention this asset path."""
    hits = []
    for path in iter_text_files(blog_dir):
        if os.path.abspath(path) == exclude:
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                if asset in f.read():
                    hits.append(os.path.relpath(path, blog_dir))
        except OSError:
            continue
    return hits


def is_tracked(blog_dir, path):
    rel = os.path.relpath(path, blog_dir).replace(os.sep, "/")
    return run(["git", "ls-files", "--error-unmatch", rel], blog_dir).returncode == 0


def delete(blog_dir, path):
    """git rm a tracked file, git clean an untracked one. Returns the command."""
    rel = os.path.relpath(path, blog_dir).replace(os.sep, "/")
    if is_tracked(blog_dir, path):
        cmd = ["git", "rm", "-f", "--", rel]
    else:
        cmd = ["git", "clean", "-f", "--", rel]
    result = run(cmd, blog_dir)
    if result.returncode != 0:
        raise SystemExit(f"실패: {' '.join(cmd)}\n{result.stderr.strip()}")
    return " ".join(cmd)


def main():
    parser = argparse.ArgumentParser(
        description="Delete a post and the assets only it references")
    parser.add_argument("post", help="_posts 안의 md 파일명 (경로도 가능)")
    parser.add_argument("--blog-dir", default="../cityofwonder.github.io",
                        help="블로그 레포 루트 (기본: ../cityofwonder.github.io)")
    parser.add_argument("--yes", action="store_true",
                        help="실제로 삭제 (없으면 확인만 하고 종료)")
    args = parser.parse_args()

    blog_dir = os.path.abspath(args.blog_dir)
    if not os.path.isdir(os.path.join(blog_dir, "_posts")):
        raise SystemExit(f"블로그 레포가 아닙니다: {blog_dir}")

    post = resolve_post(blog_dir, args.post)
    with open(post, encoding="utf-8") as f:
        assets = extract_assets(f.read())

    print(f"글      : {os.path.relpath(post, blog_dir)}")
    print(f"참조 에셋: {len(assets)}개")

    removable, shared, missing = [], [], []
    for asset in assets:
        target = os.path.join(blog_dir, asset.lstrip("/").replace("/", os.sep))
        if not os.path.exists(target):
            missing.append(asset)
            continue
        referrers = other_referrers(blog_dir, asset, post)
        if referrers:
            shared.append((asset, referrers))
        else:
            removable.append((asset, target))

    for asset, target in removable:
        print(f"  [삭제] {asset}")
    for asset, referrers in shared:
        print(f"  [보존] {asset}")
        for ref in referrers:
            print(f"           ← {ref} 에서도 참조")
    for asset in missing:
        print(f"  [없음] {asset}  (파일이 이미 없음)")

    # Files sitting in the same folders that this post never referenced. Left
    # alone -- they may belong to another post, or be leftovers worth a look.
    folders = {os.path.dirname(t) for _, t in removable}
    referenced = {t for _, t in removable}
    referenced |= {os.path.join(blog_dir, a.lstrip("/").replace("/", os.sep))
                   for a, _ in shared}
    strangers = []
    for folder in sorted(folders):
        for name in sorted(os.listdir(folder)):
            full = os.path.join(folder, name)
            if os.path.isfile(full) and full not in referenced:
                strangers.append(os.path.relpath(full, blog_dir))
    for rel in strangers[:8]:
        print(f"  [무시] {rel}  (이 글이 참조하지 않음)")
    if len(strangers) > 8:
        print(f"  [무시] ... 같은 폴더에 {len(strangers) - 8}개 더 (건드리지 않음)")

    if not args.yes:
        print(f"\n확인만 했습니다. 글 1개 + 에셋 {len(removable)}개가 삭제 대상입니다.")
        print("실제로 지우려면 --yes 를 붙이세요.")
        return

    print()
    for _, target in removable:
        print("  $ " + delete(blog_dir, target))
    print("  $ " + delete(blog_dir, post))

    # Drop asset folders that this left empty.
    for folder in sorted(folders, key=len, reverse=True):
        try:
            if os.path.isdir(folder) and not os.listdir(folder):
                os.rmdir(folder)
                print(f"  빈 폴더 삭제: {os.path.relpath(folder, blog_dir)}")
        except OSError:
            pass

    print(f"\n완료: 글 1개 + 에셋 {len(removable)}개 삭제, {len(shared)}개 보존.")


if __name__ == "__main__":
    main()
