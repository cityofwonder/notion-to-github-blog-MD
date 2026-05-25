# notion-to-github-blog-md

[cityofwonder.github.io](https://github.com/cityofwonder/cityofwonder.github.io)
(Jekyll, YAT theme) 블로그로 노션 페이지를 옮기는 변환기.

노션 블록을 블로그의 커스텀 컴포넌트로 그대로 매핑해서, 손으로 쓴 기존
포스트와 같은 형식의 `_posts/*.md`를 만들어 준다.

## 매핑

| Notion | 블로그 출력 |
| --- | --- |
| Callout | `<div class="box-note/success/warning/danger">` (색상 기반) |
| Toggle | `<details><summary>…<div class="toggle-content" markdown="1">` |
| 글자색 | `<span class="text-red/blue/green/orange/purple/pink/gray">` |
| 배경색(형광펜) | `<span class="highlight-yellow/green/blue/pink/orange/purple">` |
| Bold / Italic / Strike | `**` / `*` / `~~` |
| Underline | `<span class="text-underline">` |
| Inline / Block equation | `$…$` / `$$…$$` (MathJax via jekyll-spaceship) |
| Table | GFM 표 |
| Code | 언어 지정 펜스 |
| Image | `assets/images/<date>/`에 다운로드 후 `<figure>`(캡션 있을 때) |
| Heading 1/2/3 | `##` / `###` / `####` (제목은 front matter) |
| 댓글 | 블록 끝 각주 `[^c1]` + 하단 정의 / 페이지 댓글은 박스로 |

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
# 옵션: --output DIR (기본 ./output), --no-comments
```

1. https://www.notion.so/my-integrations 에서 **internal integration** 생성
2. 토큰을 `.env`의 `NOTION_TOKEN`에 저장
3. 옮길 페이지에서 `•••` → **Connections** → 만든 integration 추가
4. 스크립트 실행 → `output/_posts/<date>-<slug>.md` 와 `output/assets/images/<date>/` 생성
5. 두 트리를 블로그 레포에 복사해서 게시

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
