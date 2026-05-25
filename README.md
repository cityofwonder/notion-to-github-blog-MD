# notion-to-github-blog-md

[cityofwonder.github.io](https://github.com/cityofwonder/cityofwonder.github.io)
(Jekyll, YAT theme) 블로그로 노션 페이지를 옮기는 변환기.

노션 블록을 블로그의 커스텀 컴포넌트로 그대로 매핑해서, 손으로 쓴 기존
포스트와 같은 형식의 `_posts/*.md`를 만들어 준다.

## 매핑

| Notion | 블로그 출력 |
| --- | --- |
| Callout | `<div class="box-note/success/warning/danger">` (색상 기반) |
| Quote (인용) | `<div class="box-warning">` (노란 박스, 안의 텍스트 스타일 유지) |
| Toggle | `<details><summary>…<div class="toggle-content" markdown="1">` |
| 글자색 | `<span class="text-red/blue/green/orange/purple/pink/gray">` |
| 배경색(형광펜) | `<span class="highlight-yellow/green/blue/pink/orange/purple/red/gray">` |
| Bold / Italic / Strike | `**` / `*` / `~~` |
| Underline | `<span class="text-underline">` |
| Inline / Block equation | `$…$` / `$$…$$` (MathJax via jekyll-spaceship) |
| Table | GFM 표 |
| Code | 언어 지정 펜스 |
| Image | `assets/images/<date>/`에 다운로드 후 `<figure>`(캡션 있을 때) |
| Heading 1/2/3 | `##` / `###` / `####` (제목은 front matter) |
| 댓글 | 댓글 달린 블록 텍스트를 `<span class="notion-comment">`로 감싸 하이라이트, 호버 시 말풍선. 페이지 댓글은 하단 박스 |

### Front matter
페이지 속성에서 추출한다 (별칭은 대소문자 무시):
- **title**: title 타입 속성
- **date**: date 타입 속성, 없으면 `created_time`
- **categories**: `category/categories/카테고리/분류` (select·multi-select) → `["📂/값"]`
- **tags**: `tags/tag/태그` (multi-select)
- **subtitle**: `subtitle/부제/description/설명/요약` (rich text)
- **banner.image**: 페이지 cover

## 댓글의 한계 (Notion API 제약)
- **미해결(unresolved) 댓글만** 조회됨. resolve된 스레드는 못 가져옴.
- 위치는 **블록 단위**까지만. 블록 안의 정확한 글자 구간은 API가 노출하지 않음.
- integration에 **Read comment** 권한이 켜져 있어야 함.

## 사용법

```bash
pip install -r requirements.txt
cp .env.example .env   # NOTION_TOKEN 채우기

python notion_to_blog.py <노션-페이지-URL-또는-ID>
# 옵션:
#   --blog-dir DIR  블로그 레포 루트 (기본 ../cityofwonder.github.io).
#                   글 -> <DIR>/_posts, 이미지 -> <DIR>/assets/images/<date>.
#                   먼저 검토하려면 ./output 같은 스테이징 폴더를 넘기면 됨
#   --no-comments   댓글 제외
#   --slug TEXT     slug 직접 지정 (기본은 제목을 음역; 한글 제목은 로마자가 됨).
#                   영어로 캐주얼하게 옮기고 싶을 때 사용
#   --title TEXT    제목 직접 지정

# 예: 한글이 섞인 제목을 영어 slug로 (옆에 블로그 레포가 있다고 가정)
python notion_to_blog.py <URL> --slug "single function report 0943 crs result analysis"
# -> ../cityofwonder.github.io/_posts/2026-05-25-single-function-report-0943-crs-result-analysis.md
# -> ../cityofwonder.github.io/assets/images/2026-05-25/...
```

글과 이미지가 **블로그 레포에 바로** 쓰여서 별도 복사가 필요 없다.
디렉토리 구조는 다음을 가정한다:
```
study/git/
  notion-to-github-blog-md/     # 이 레포 (여기서 실행)
  cityofwonder.github.io/       # 블로그 레포 (--blog-dir 기본값)
```
실행 후 블로그 레포에서 검토하고 커밋:
```bash
cd ../cityofwonder.github.io
git add _posts assets
git commit -m "Add post migrated from Notion"
git push
```

1. https://www.notion.so/my-integrations 에서 **internal integration** 생성
2. 토큰을 `.env`의 `NOTION_TOKEN`에 저장
3. 옮길 페이지에서 `•••` → **Connections** → 만든 integration 추가
4. 스크립트 실행 → 블로그 레포의 `_posts/<date>-<slug>.md` 와 `assets/images/<date>/`에 바로 생성
5. 블로그 레포에서 검토 후 커밋·푸시

## 구조
```
notion_to_blog.py        # CLI
notion_blog/
  client.py              # Notion API 래퍼 (블록/속성/댓글/이미지)
  converter.py           # 블록 트리 → 마크다운 본문
  richtext.py            # rich_text → 인라인 마크다운/HTML
  frontmatter.py         # 속성 → front matter + 파일명
  mappings.py            # 색상/박스/헤딩 매핑 상수
```
