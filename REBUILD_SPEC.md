# 재구축 구현 명세서 (Gemini 기반 애드센스 대량 발행)

> 팀장 확정 명세. 구현 팀원은 이 문서대로 짠다. 애매하면 추측 말고 팀장에게 보고.

## 0. 큰 그림

기존 "Opus 에이전트+스킬" 파이프라인을 폐기하고, **무료 Gemini API로 주제별 블로그 글을 대량 생성 → 기존 Blogger 발행 코어로 발행**한다.

- 블로그 1개 = 주제 1개. 첫 블로그 = **건강**(기존 블로그 재사용).
- 멀티 블로그는 **구글 계정 1개 + 블로그 여러 개**. 토큰 1벌, Gemini 키 1개 공유. `blogs.json`에 블로그만 추가하면 복제.
- 발행 글끼리 **내용 중복 금지**(애드센스 승인 핵심).

## 1. 파일 구조 (이번 구현 범위)

| 파일 | 상태 | 역할 |
|------|------|------|
| `blogs.json` | **신규** | 블로그별 설정(id/url/theme/keywords_file/labels) |
| `generate_post.py` | **신규** | Gemini로 글 1편 생성 → `_workspace/{run_id}_final.json` |
| `post_insurance.py` | **소폭 수정** | final.json의 blog_url로 발행 대상 분기. 이미지·인증·발행 로직은 그대로 |
| `.github/workflows/post_insurance.yml` | **개편** | 헤드리스 Claude Code 삭제 → generate_post.py 실행. 블로그당 하루 5편 |
| `_knowledge/health_keywords_2026.md` | 완료 | 건강 키워드 풀(파싱 대상) |
| 구 insurance 에이전트/스킬 | **정리 대상(다음 단계)** | 검증 후 별도 삭제 |
| `post.py`, `post.yml`, `fix_images.py` 등 다른 블로그 발행기 | **유지·건드리지 말 것** | insurance 외 다른 블로그용. 삭제·수정 금지(Gemini 패턴 참고만 허용) |

**이번 구현에서는 아무 파일도 삭제하지 않는다.** 구 insurance 에이전트/스킬/`adsense-content-requirements.md`는 새 시스템 검증 후 별도 정리 단계에서 처리한다. `post.py`·`post.yml`·`fix_images.py` 등 **insurance 외 다른 블로그 발행기는 정리 단계에서도 삭제하지 않는다**(karpathy: 외과적 변경).

## 2. `blogs.json` 스키마

```json
{
  "blogs": [
    {
      "id": "health",
      "url": "https://salvia-information.blogspot.com",
      "theme": "건강",
      "keywords_file": "_knowledge/health_keywords_2026.md",
      "labels": ["건강", "건강정보"],
      "posts_per_day": 5
    }
  ]
}
```
- `url`은 실제 발행 대상. 지금은 기존 블로그(팀장이 최종 URL 확정 전까지 `INSURANCE_BLOG_URL` env 우선). **url을 하드코딩하지 말고 env override를 허용**할 것.
- 멀티 블로그는 이 배열에 객체 추가로 끝나야 한다.

## 3. `generate_post.py` 명세

### 입력
- 인자: 블로그 id (예: `python generate_post.py health`). 생략 시 blogs.json 첫 블로그.
- `GEMINI_API_KEY` env (없으면 코드 폴백 키). 모델: `gemini-2.5-flash` → 실패 시 `gemini-2.0-flash` 폴백(post.py와 동일 패턴).

### 처리
1. blogs.json에서 해당 블로그 설정 로드.
2. `keywords_file`(마크다운 표) 파싱 → 키워드 목록 + 각 키워드의 "추천 글 제목 각도".
3. `_knowledge/published_log.jsonl` 로드 → 이 블로그가 **이미 쓴 키워드/제목** 수집.
4. **키워드 선택**: 아직 안 쓴 키워드 우선. 전부 썼으면 가장 오래전에 쓴 키워드를 고르되 **각도(제목)를 로그와 다르게** 강제.
5. Gemini 호출(§4 프롬프트). **구조화 출력(response JSON) 사용 권장** — `{title, content_html, labels}` 스키마로 받으면 파싱이 안전.
6. **중복 검증**: 생성된 제목·소제목(h2 텍스트)이 로그의 기존 제목과 과도하게 겹치면(핵심어 다수 일치) 1회 재생성. 그래도 겹치면 그 사실을 stderr로 남기고 저장은 하되 경고.
7. `_workspace/{run_id}_final.json` 저장. `run_id`는 `GITHUB_RUN_ID` env, 없으면 타임스탬프.

### 출력 JSON 스키마 (`_workspace/{run_id}_final.json`)
post_insurance.py가 읽는 형식과 **정확히 일치**해야 한다:
```json
{
  "blog_id": "health",
  "blog_url": "https://salvia-information.blogspot.com",
  "keyword": "콜레스테롤",
  "title": "콜레스테롤 낮추는 음식 10가지, 2026년 바뀐 기준까지 정리",
  "content_html": "<p>...</p><h2>...</h2>...",
  "labels": ["건강", "건강정보", "콜레스테롤"]
}
```
- `keyword`는 이미지 검색 매핑용. post_insurance.py의 `KO_IMAGE_QUERY`에 없는 키워드면 기본 검색어로 폴백되니, **가능하면 KO_IMAGE_QUERY 키와 맞추거나** 없으면 그대로 둔다(발행은 됨).

## 4. Gemini 프롬프트 템플릿 (건강 — 레퍼런스 구조 재현)

레퍼런스(https://dailyinfo-money.blogspot.com/2026/06/2026.html) 벤치마크 구조. 프롬프트에 아래를 지시:

**역할·톤:** "너는 실제 경험과 자료를 곁들여 쉽게 풀어 쓰는 한국어 건강정보 블로거다. 금융·의료 초보자도 이해하도록 친근한 구어체와 구체적 숫자를 섞되, 과장 없이 신뢰감 있게 쓴다."

**글 구조(반드시 준수):**
1. **제목(title)**: 핵심 키워드를 앞에 두고, 구체적 숫자/연도/액션워드를 붙인 SEO 제목. 대괄호 없이. 예: "콜레스테롤 낮추는 음식 10가지, 2026년 바뀐 기준까지 정리".
2. **도입부**: 3문단 내외, 각 3~4문장. 숫자·공감으로 시작("검진 결과지에서 이 수치 보고 덜컥 하신 적 있죠?"). 이 글이 뭘 알려주는지 예고.
3. **본문 소제목**: `<h2>` 태그로 **4~5개**, 번호 매김("1. ...", "2. ..."). 각 섹션은 5~7개 항목의 `<ul><li>` 불릿 또는 `<table>` 비교표를 포함. **소제목은 반드시 `<h2>`** (이미지 자동 삽입이 `</h2>` 기준, §5 참조).
4. **결론+CTA**: 3문장 요약 + 행동 유도 한 줄. 판매성·과장 금지.

**강조:** 핵심 숫자·용어(수치, 기준값, 성분명)는 `<b>`로 볼드. 레퍼런스처럼 숫자 가시성을 높인다.

**분량:** 본문 2,200~2,500자(한글 기준).

**YMYL·애드센스 원칙(필수, `_knowledge/health_keywords_2026.md` 종합 코멘트 반영):**
- 의학적 단정·치료 효과 주장 금지. "낫는다/예방된다"가 아니라 "~로 알려져 있다", "연구에 따르면" 톤.
- 수치·기준은 "참고 범위이며 확진은 의료기관 검사가 필요"하다고 안내.
- **의료 면책 문구**를 말미에 `<p>` 한 줄로: "본 글은 일반적인 건강 정보로 진단·치료를 대신하지 않으며, 증상이 지속되면 전문의 상담을 권합니다."
- 처방약(위고비 등)·호르몬요법·정신건강은 '보도된 사실'만 중립 전달, 복용·구매 권유 금지, 정신건강은 '진단' 아닌 '자가 체크' 톤.

**중복 회피(프롬프트에 주입):** "다음 제목들은 이미 발행했으니 주제·소제목·구성이 겹치지 않게 새로운 각도로 써라: {기존 제목 목록}."

**이미지 지시:** 본문에 `<img>` 태그를 넣지 마라(발행 단계에서 자동 삽입).

**출력:** `{title, content_html, labels}` JSON. content_html은 `<p>`, `<h2>`, `<ul>/<li>`, `<table>`, `<b>`만 사용. `<html>/<body>` 래퍼 없이 본문 조각만.

## 5. 이미지 삽입 정합성 (중요)

`post_insurance.py`의 `insert_images()`는 `content.split("</h2>")`로 각 `<h2>` 뒤에 이미지를 넣는다. 따라서 **생성기는 소제목을 반드시 `<h2>`로** 출력해야 이미지가 자연스럽게 배치된다. H2 4~5개 → 앞 3개 뒤에 이미지 3장(현재 `count=3` 유지). 생성기가 h1/h3만 쓰면 이미지가 안 들어가니 주의.

## 6. `post_insurance.py` 수정 (최소·외과적)

- `main()`에서 final.json에 `blog_url`이 있으면 그 URL로 발행 대상 블로그를 정한다(현재는 `BLOG_URL` env 고정). `get_blog_id(service, url)`가 url을 받도록 하거나, `BLOG_URL`을 final.json 값으로 덮어쓴다.
- `INSURANCE_BLOG_URL` env가 있으면 그게 최우선(테스트·오버라이드용).
- **그 외 인증·이미지 수집/삽입·발행·로그 로직은 절대 건드리지 않는다.**

## 7. 워크플로우 개편 (`post_insurance.yml`)

- "Claude Code CLI 설치" + "헤드리스 파이프라인" 두 스텝 **삭제**. `ANTHROPIC_API_KEY` 불필요.
- 새 스텝: `python generate_post.py health` (env: `GEMINI_API_KEY`).
- 발행 스텝 유지: `python post_insurance.py` (env: 기존 Pixabay/imgBB/Blogger/BLOG_URL).
- **블로그당 하루 5편**: 초기엔 한 워크플로우 실행에서 생성→발행을 5회 반복(루프)하거나, cron 5회. 단순함을 위해 **생성→발행을 5회 도는 루프 스텝** 권장(각 회차 run_id 구분). 매 회차 중복 회피가 적용되므로 5편이 서로 다른 키워드/각도가 된다.
- 발행 이력 커밋 스텝 유지.

## 8. 완료 기준 (구현 팀원 자체 검증)

1. `python generate_post.py health` 실행 → `_workspace/{run_id}_final.json`이 §3 스키마대로, §4 구조(제목 SEO / h2 소제목 4~5 / 볼드 숫자 / 2200~2500자 / 의료 면책 / img 태그 없음)로 실제 생성된다. (실제 Gemini 호출로 1편 뽑아 눈으로 확인.)
2. 같은 키워드가 이미 로그에 있으면 각도가 달라진다(중복 회피 동작 확인).
3. `post_insurance.py`가 final.json의 blog_url로 발행 대상을 잡는다(발행 API 실제 호출은 토큰 필요하니, blog_url 분기 로직까지만 코드로 확인).
4. 워크플로우 YAML이 헤드리스 Claude 없이 generate→publish로 구성된다.
