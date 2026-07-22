# 프론트엔드 + 애드센스 승인 준비 구현 명세

> 팀장 확정 명세. 팀원3의 조사 문서 `_knowledge/adsense_approval_requirements.md`가 완료되면 그 요건을 근거로 구현한다. 대상: `blogs.json`의 블로그 5개(health/blog2~5).

## 0. 원칙
- 운영자 정보(운영자명·공개 이메일·개인정보 시행일 등)는 **`site_config.json`로 분리**해 플레이스홀더로 둔다. 사장이 나중에 값만 채우면 페이지에 자동 반영된다. 코드에 하드코딩하지 않는다.
- 발행 코어(`post_insurance.py`의 Blogger OAuth 인증)를 재활용한다. blogger scope 토큰 하나로 posts와 **pages 둘 다** 가능.
- 계정 1개 안의 블로그 5개는 같은 토큰으로 `blogId`만 바꿔 처리(발행기와 동일 구조).

## 1. 신규/수정 파일

| 파일 | 상태 | 역할 |
|------|------|------|
| `site_config.json` | 신규 | 운영자 공통 정보 플레이스홀더(운영자명, 공개 이메일, 개인정보 시행일 등). 사장이 나중에 채움 |
| `create_pages.py` | 신규 | blogs.json의 각 블로그에 애드센스 필수 페이지(개인정보처리방침·소개·연락처 등)를 Blogger pages API로 자동 생성 |
| `themes/base_theme.xml` | 신규 | 애드센스 친화 반응형 Blogger 테마 XML (적용은 사장이 관리자에서 수동 업로드) |
| `_knowledge/adsense_approval_requirements.md` | 팀원3 작성중 | 필수 페이지·문구·승인 요건의 근거 문서 |

## 2. `site_config.json` 스키마 (플레이스홀더)
```json
{
  "owner_name": "<<운영자명 — 나중에 채움>>",
  "contact_email": "<<공개 연락 이메일 — 나중에 채움>>",
  "privacy_effective_date": "<<개인정보처리방침 시행일 예: 2026-07-10 — 나중에 채움>>",
  "site_brand": "Salvia Information"
}
```
- 페이지 생성기는 이 값을 페이지 본문에 치환해 넣는다. 값이 플레이스홀더(`<<...>>`)이면 **경고를 출력**하되 생성은 진행(사장이 나중에 페이지를 수정하거나 값 채우고 재생성).

## 3. `create_pages.py` 명세
- 인자: 블로그 id (예: `python create_pages.py health`) 또는 `--all`로 blogs.json 전체.
- 각 블로그에 대해 **팀원3 조사가 확정한 필수 페이지 전부**를 생성한다(최소: 개인정보처리방침, 소개, 연락처. 조사가 면책조항 등 추가하면 포함).
- 페이지 내용:
  - **개인정보처리방침**: 조사 문서가 확정한 애드센스/쿠키/제3자 광고(Google, DoubleClick) 필수 문구를 포함. `site_config`의 시행일·이메일 치환.
  - **소개(About)**: 블로그 주제(blogs.json의 theme)에 맞춘 소개 + E-E-A-T 요소. `site_config` 브랜드/운영자 치환.
  - **연락처(Contact)**: `site_config`의 공개 이메일 안내.
- **중복 방지**: 이미 같은 제목의 페이지가 있으면 건너뛴다(pages().list로 확인). 재실행해도 중복 생성 안 함.
- 인증: `post_insurance.py`의 `get_blogger_service()`를 재활용(import 또는 동일 패턴). 발행 대상 blogId는 blogs.json의 url → `getByUrl`로 획득.
- 실제 페이지 생성 API: `service.pages().insert(blogId=..., body={"title":..., "content":...}).execute()`. (조사가 pages API 가능함을 확인한다는 전제. 불가로 밝혀지면 팀장에게 보고 후 대안.)

## 4. `themes/base_theme.xml` 명세
- 애드센스 승인에 유리한 **반응형** Blogger 테마 XML.
- 요건(조사의 프론트엔드 체크리스트 반영): 상단 네비게이션 메뉴(필수 페이지 링크 노출), 라벨/카테고리 표시, 모바일 최적화, 깔끔한 가독성(적정 폰트·여백), 광고 삽입 위치 확보(본문 상/중/하), 빠른 로딩(경량).
- 5개 블로그 공통 베이스. 주제별 포인트 컬러 정도만 다르게 할 수 있게 구성.
- **적용은 자동화 불가(조사로 확정)** → 사장이 Blogger 관리자 > 테마 > 백업/복원 > 업로드로 적용. README나 보고로 적용 절차 안내.

## 5. 완료 기준
1. `site_config.json`이 플레이스홀더로 생성됨.
2. `create_pages.py`가 조사가 정한 필수 페이지를 blogs.json 블로그에 생성하는 로직 구현. (토큰 없이도 import/문법 정상; 실제 생성은 발행 테스트 단계에서 사장 승인 하에.)
3. `themes/base_theme.xml`이 유효한 Blogger 테마 XML로 작성됨.
4. 운영자 정보는 전부 site_config 치환으로만 들어가고 하드코딩 없음.
