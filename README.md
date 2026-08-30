# notion-to-github-blog-md

[cityofwonder.github.io](https://github.com/cityofwonder/cityofwonder.github.io)
(Jekyll, YAT theme) 블로그로 노션 페이지를 옮기는 변환기.

노션 블록을 블로그의 커스텀 컴포넌트로 그대로 매핑해서, 손으로 쓴 기존
포스트와 같은 형식의 `_posts/*.md`를 만들어 준다.

## 매핑

| Notion | 블로그 출력 |
| --- | --- |
| Callout | `<div class="box-note/success/warning/danger">` (색상 기반) |
| Quote (인용) | `<blockquote class="notion-quote">`. 노션 블록에 배경색이 있으면 `quote-<색>`, 글자색이면 `text-<색>` 을 덧붙인다. 색이 없으면 노션처럼 왼쪽 바만 |
| Toggle | `<details><summary markdown="span">…<div class="toggle-content" markdown="1">`. 제목 없는 토글은 `더보기`. 노션 블록 배경색이 있으면 `class="toggle-<색>"` 을 달아 **열렸을 때만** 그 색 패널이 뜬다 |
| 글자색 | `<span class="text-red/blue/green/orange/purple/pink/gray/yellow/brown">` (노션 9색 전부) |
| 배경색(형광펜) | `<span class="highlight-yellow/green/blue/pink/orange/purple/red/gray/brown">` (노션 9색 전부) |
| Bold / Italic / Strike | `<strong>` / `<em>` / `<del>` (마크다운 `**`는 앞뒤 공백·별표에 깨져서 태그 사용) |
| Underline | `<span class="text-underline">` |
| Inline / Block equation | `$…$` / `$$…$$` (MathJax via jekyll-spaceship). 인라인 수식도 형광펜/글자색 span 을 두른다 |
| Table | GFM 표 |
| Code | 언어 지정 펜스 |
| Image | `assets/images/<date>/<slug>-<블록ID8>.<ext>` 로 다운로드 후 `<figure>`(캡션 있을 때). 캡션은 서식·링크 유지, `alt`는 평문 |
| Heading 1/2/3 | `##` / `###` / `####` (제목은 front matter) |
| Embed / Bookmark | youtube·vimeo·dailymotion·spotify·soundcloud 는 맨 URL로 두어 jekyll-spaceship 이 임베드. **tenor** 는 페이지를 열어 og:image 의 직접 GIF 주소를 뽑아 삽입하며, **캡션이 있으면 이미지와 같은 `<figure>`** 로 감싼다. 나머지는 맨 URL |
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
전부 **노션 DB 속성에서 읽는다.** 속성을 채워두면 옵션 없이 그냥 돌리면 된다.

| front matter | 읽는 속성 | 폴백 |
| --- | --- | --- |
| 파일명 날짜 + slug | `filename` (`2026-08-20-p5-MLA-USENIX2026.md`) | date 타입 속성 → `created_time`, slug는 제목 음역 |
| `title` | title 타입 속성 | `--title` 로 덮어쓰기 |
| `subtitle` | `subtitle` | 빈 값 |
| `categories` | `categories` multi-select 값을 **선택 순서대로 이어붙임** (`📂/` + `paper-review/` + `fingerprint/` → `["📂/paper-review/fingerprint/"]`) | `["📂/"]` |
| `tags` | `tags` / `tag` / `태그` multi-select | `[]` |
| `banner.image` | `banner` 파일 속성. **노션 호스팅 파일이면** `assets/images/<date>/<slug>-banner.<ext>` 로 다운로드, **외부 URL이면 링크 그대로** | 페이지 cover → 빈 값 |

`filename`의 slug는 **그대로** 쓴다 (대소문자 포함). `--slug`를 주면 그게 이긴다.

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

## 재변환 시 안정성
- 이미지 파일명은 **이미지 블록 ID 앞 8자**를 쓴다 (`p5-mla-41699c64.png`).
  등장 순서 카운터를 쓰면 노션에서 사진을 추가/삭제/순서변경할 때마다 전체가
  밀려서, 재변환이 엉뚱한 파일을 덮어쓰고 고아 파일을 남긴다. 블록 ID는 셋 다
  견딘다.
- 다만 `.md`는 **경고 없이 덮어쓴다.** 생성된 글을 손으로 고쳤다면 재변환 전에
  백업하거나, `--blog-dir ./output` 으로 받아서 diff를 떠라.

## 중첩 블록
노션은 **문단·헤딩 아래에도** 블록을 중첩할 수 있다. 이 자식들은 마크다운에서
들여쓰면 코드블록이 되어버리므로 **형제로 펼쳐서** 출력한다. 리스트 항목의
자식은 기존대로 들여쓴 하위 리스트가 된다.

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

## 간격
연속된 리스트 항목은 **한 줄 개행으로 붙인다.** 사이에 빈 줄을 넣으면 kramdown 이
loose list 로 만들어 항목마다 `<p>` 를 씌우고 문단 마진을 붙여서, 손으로 쓴 글보다
훨씬 성기게 보인다. 리스트가 아닌 블록 사이에는 그대로 빈 줄을 넣는다.

## 색상 두 겹
노션은 한 span 에 **글자색과 형광펜을 동시에** 넣을 수 있는데, 공식 API 의
`annotations.color` 는 값이 하나뿐이라 둘 중 하나가 사라진다. 내부 레코드에는
둘 다 남아 있어서 `get_color_overrides()` 가 세그먼트 인덱스 기준으로 채워
넣는다 (댓글 앵커와 같은 엔드포인트, 같은 폴백 규칙).

## 외부 미디어
- 노션이 호스팅하는 파일(이미지·배너)은 서명된 S3 링크라 한 시간이면 만료된다 →
  **반드시 다운로드**한다.
- 외부 URL(unsplash 배너, tenor GIF 등)은 만료되지 않으므로 **링크로 둔다.**
- tenor 링크는 jekyll-spaceship 이 임베드할 줄 모르므로, 페이지를 한 번 열어
  `og:image` 의 직접 GIF 주소를 뽑아낸다. 실패하면 원래 링크를 그대로 남긴다.
  대상 호스트는 `converter.py` 의 `_OG_EMBED_HOSTS` 에 있다.

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
#   --slug TEXT     slug 직접 지정. 기본은 filename 속성, 없으면 제목 음역
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

## 글 되돌리기 (cleanup_post.py)

옮긴 글을 무르거나 파일명을 바꿔 다시 뽑을 때, md 만 지우면 이미지가 남고
폴더째 지우면 다른 글이 쓰던 배너까지 날아간다. 이 스크립트는 **그 글이
참조하는 에셋이 블로그의 다른 파일에서도 쓰이는지 확인한 뒤**, 아무도 안 쓰는
것만 md 와 함께 지운다.

```bash
python cleanup_post.py 2026-06-04-TIL-MCP.md            # 확인만 (기본)
python cleanup_post.py 2026-06-04-TIL-MCP.md --yes      # 실제 삭제
python cleanup_post.py <파일명> --blog-dir ./output      # 스테이징 폴더 대상
```

```
글      : _posts/2026-06-04-TIL-MCP.md
참조 에셋: 3개
  [삭제] /assets/images/2026-06-04/TIL-MCP-001bd65d.png
  [삭제] /assets/images/2026-06-04/TIL-MCP-e8b15a7c.png
  [보존] /assets/images/2026-06-04/TIL-MCP-banner.png
           ← _posts/2026-06-05-other-post.md 에서도 참조
```

- **드라이런이 기본.** `--yes` 없이는 아무것도 건드리지 않는다.
- 참조 탐색 범위는 `_site` / `.jekyll-cache` / `.git` 을 제외한 블로그 전체
  (md, html, yml, scss, js, json …). front matter 의 `banner.image`,
  마크다운 `![]()`, HTML `src=""` 모두 잡는다. 공백 있는 파일명도 처리한다.
- 삭제는 추적 여부에 따라 `git rm -f` 또는 `git clean -f` 를 쓰고, 실행한
  명령을 그대로 출력한다.
- 같은 폴더에 있지만 그 글이 참조하지 않는 파일은 **건드리지 않고** 목록만
  보여준다 (다른 글 것이거나 예전 변환의 잔재일 수 있으므로).
- 비게 된 `assets/images/<date>/` 폴더는 같이 정리한다.

## 구조
```
notion_to_blog.py        # CLI
cleanup_post.py          # 글 + 전용 에셋 삭제 (참조 확인 후)
notion_blog/
  client.py              # Notion API 래퍼 (블록/속성/댓글/이미지)
  converter.py           # 블록 트리 → 마크다운 본문
  richtext.py            # rich_text → 인라인 마크다운/HTML
  frontmatter.py         # 속성 → front matter + 파일명
  mappings.py            # 색상/박스/헤딩 매핑 상수
```
