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
| 글자색 | `<span class="text-red/blue/green/orange/purple/pink/gray/yellow/brown">` (노션 9색 전부) |
| 배경색(형광펜) | `<span class="highlight-yellow/green/blue/pink/orange/purple/red/gray/brown">` (노션 9색 전부) |
| Bold / Italic / Strike | `<strong>` / `<em>` / `<del>` (마크다운 `**`는 앞뒤 공백·별표에 깨져서 태그 사용) |
| Underline | `<span class="text-underline">` |
| Inline / Block equation | `$…$` / `$$…$$` (MathJax via jekyll-spaceship) |
| Table | GFM 표 |
| Code | 언어 지정 펜스 |
| Image | `assets/images/<date>/`에 다운로드 후 `<figure>`(캡션 있을 때). 캡션은 서식·링크 유지, `alt`는 평문 |
| Heading 1/2/3 | `##` / `###` / `####` (제목은 front matter) |
| 페이지/사용자 멘션 | `<span class="text-gray">` 라벨만 (워크스페이스 링크는 제거) |
| 댓글 | 댓글이 달린 **정확한 구간**을 `<span class="notion-comment">`로 감싸 하이라이트, 호버 시 말풍선. 페이지 댓글은 하단 박스 |

### Front matter
항상 같은 형식으로 고정 출력한다:
```yaml
---
layout: post
title: "..."
subtitle: ""
categories: ["📂/"]
tags: ["..."]
banner:
  image: "..."
  opacity: 0.5
  background: "rgba(0, 0, 0, 0.7)"
---
```
- **title**: title 타입 속성 (`--title`로 덮어쓰기 가능)
- **date**: date 타입 속성, 없으면 `created_time` (파일명 prefix)
- **subtitle**: 항상 빈 값 — 필요하면 직접 입력
- **categories**: 항상 `["📂/"]` 플레이스홀더 — 직접 세팅
- **tags**: `tags/tag/태그` multi-select에서 추출 (없으면 `[]`)
- **banner.image**: 페이지 cover, 없으면 빈 값

## 댓글의 한계 (Notion API 제약)
- **미해결(unresolved) 댓글만** 조회됨. resolve된 스레드는 못 가져옴.
- integration에 **Read comment** 권한이 켜져 있어야 함.
- 공식 API는 댓글 위치를 **블록 단위**까지만 알려준다. 정확한 글자 구간은
  노션 웹 클라이언트가 쓰는 내부 엔드포인트(`api/v3/loadPageChunk`)에서
  가져오는데, **페이지에 공개 공유 링크가 켜져 있을 때만** 인증 없이 읽힌다.
  - 공유가 꺼져 있거나 앵커가 서식 경계에 걸쳐 있으면 → 예전처럼 블록 전체를
    하이라이트하는 방식으로 자동 폴백한다 (한 블록 안에서 전부 아니면 전무).
  - 내부 엔드포인트는 비공식이라 언젠가 바뀔 수 있다. 바뀌면 폴백만 남고
    변환은 계속 동작한다.

## HTML 출력 규칙
- 강조는 `**`가 아니라 `<strong>`/`<em>`/`<del>` 태그로 낸다. 노션 세그먼트는
  `"굵은 텍스트 "` 처럼 끝에 공백이 붙거나 각주용 `*`가 섞이는 일이 잦은데,
  마크다운 구분자 규칙상 그런 경우 강조가 조용히 무시된다.
- 렌더된 텍스트를 담는 **블록** HTML에는 `markdown="1"`, **인라인** 전용
  HTML에는 `markdown="span"`을 붙인다. 안 붙이면 `[링크](url)`이 그대로 나온다.
  - `<div class="box-*">`, `<div class="toggle-content">` → `markdown="1"`
  - `<summary>`, `<figcaption>` → `markdown="span"`
  - `<figure>`에는 **붙이지 않는다.** 블로그가 `figure > img`로 이미지를
    스타일링하는데, `markdown="1"`을 주면 kramdown이 `<img>`를 `<p>`로 감싸
    그 선택자가 안 먹고 캡션 위에 문단 여백까지 생긴다.
- 본문 텍스트(`plain_text`)는 HTML 이스케이프한다. `a < b`나 `<TAG>`가
  태그로 먹히지 않게 하기 위함. 수식과 코드 스팬은 예외(각각 MathJax와
  kramdown이 알아서 처리).

## 링크 처리
페이지/사용자 멘션과 `notion.so`·`app.notion.com` 링크는 **링크를 떼고 텍스트만**
남긴다. 비공개 워크스페이스 URL이 공개 블로그에 그대로 나가는 걸 막기 위함이다.
공개된 `*.notion.site` 링크는 그대로 유지한다.

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
