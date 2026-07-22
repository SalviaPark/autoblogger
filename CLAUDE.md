## 하네스: Gemini 기반 애드센스 대량 블로그 발행 시스템

**목표:** 무료 Gemini API로 주제별 블로그 5개(건강/재테크/IT/여행/생활정보, 향후 5~10개로 확장)를 운영해 애드센스 승인 후 수익화한다. 예전의 보험 단일 블로그·Opus 에이전트 파이프라인은 폐기하고, Gemini 직접 호출 기반 콘텐츠 생성 + GitHub Actions 자동 발행으로 전면 재구축했다.

**핵심 구조:**
- `generate_post.py` — 콘텐츠 생성. 발행 직전 실시간 트렌드(Gemini Google Search grounding)로 그 블로그 주제 카테고리의 인기검색어+연관검색어를 조회해 메인 테마를 잡고, 1인칭 경험담(E-E-A-T, 본문 중 한 단락에 집중)과 YMYL 원칙을 반영해 본문을 생성한다. 실시간 조회 실패 시 `_knowledge/*_keywords_2026.md` 고정 키워드로 폴백. 라벨은 `blogs.json`의 블로그별 고정 카테고리 목록에서만 선택(자유 생성 라벨·키워드 원문 라벨 금지). 일일 발행 쿼터(`posts_per_day`) 게이트 포함(초과 시 조기 종료).
- `publisher.py` — Blogger 인증, 이미지 삽입(Pixabay+imgBB), 발행, 발행 이력(`_knowledge`의 로그, 블로그별 `blog_id` 포함) 기록. 발행 대상 블로그는 `final.json`의 `blog_url` 기준.
- `create_pages.py` — 애드센스 필수 페이지 5종(개인정보처리방침·소개·연락처·면책조항·이용약관) 생성. `--all` 또는 블로그 id로 실행, 멱등적(이미 있는 페이지는 건너뜀).
- `blogs.json` — 블로그별 설정(id·URL·주제·`keywords_file`·`labels`·`categories`·`posts_per_day`).
- `site_config.json` — 운영자 정보(입력 완료).
- `_knowledge/` — 주제별 키워드 조사(`*_keywords_2026.md`), 애드센스 승인 요건(`adsense_approval_requirements.md`), 글쓰기 가이드(`adsense_writing_guide.md`).
- `themes/` — 블로그 5개 각각의 반응형 Blogger 테마 XML(주제색만 다름, 매칭표는 PROJECT_PLAN.md 참고).
- `.github/workflows/publish.yml` — 하루 3회(KST 08/16/24시) cron, `blogs.json`의 활성(`posts_per_day>0`) 블로그를 순회하며 발행.

**개발 워크플로우:** 이 저장소 관련 개발 작업은 전역 `salvia-project` 스킬(팀 조직 운영)로 진행한다 — 팀장이 방향을 잡고 차장(Opus, 설계까지만)·과장(Sonnet, 세부 방향 수립+구현)·대리·사원(Haiku, 실행/조사)을 고용해 배분·검수한다. `main`←`develop`←`feature/*` 브랜치 워크플로우를 쓰며, 병렬 feature 작업은 격리 worktree, `develop→main` 머지는 사장 승인 필요. 계획은 `PROJECT_PLAN.md`(미추적 파일, 유실 주의)로 관리한다.

단순 질문(예: "이 파이프라인이 왜 이렇게 짜여있어?")은 스킬 없이 직접 답변 가능.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-07-09 | 초기 구성: material-researcher, adsense-guide-researcher, writer, publish-engineer 에이전트 + 6개 스킬 + 오케스트레이터 2개(blog-knowledge-refresh, insurance-blog-pipeline) | 전체 | 애드센스 승인을 위한 콘텐츠 품질 전면 개편 |
| 2026-07-09 | topic-drafter + seo-optimizer + quality-gate(LLM) → writer 단일 에이전트로 통합, quality-gate는 structural_check.py 스크립트로 대체 | agents/writer.md, skills/insurance-draft-writing, skills/adsense-quality-scoring, skills/insurance-blog-pipeline | 발행 1건당 Opus 호출이 3~10회로 비용 과다 — 재설계로 1~2회로 축소 |
| 2026-07-09 | post_insurance.py: Gemini 단발 생성부(generate_post/generate_trending_post) 제거, `_workspace/{run_id}_final.json` 읽어 발행하는 구조로 변경. Blogger 인증/이미지/발행 로직은 그대로 유지 | post_insurance.py | 콘텐츠 생성을 에이전트 파이프라인으로 이관 |
| 2026-07-09 | GitHub Actions 워크플로우에 헤드리스 Claude Code 실행 단계 추가, cron 하루 10회 → 4회로 축소 | .github/workflows/post_insurance.yml | 헤드리스 실행 필요 + 품질 우선 정책(adsense-content-requirements.md 12절) |
| 2026-07-09 | quality-gate 에이전트 재도입(Sonnet 5 모델, 구조 검증 통과 후에만 호출). writer 자체 점검만으로는 원본성·유용성 같은 실질 품질을 독립적으로 검증하지 못한다는 우려 | agents/quality-gate.md, skills/adsense-quality-scoring, skills/insurance-blog-pipeline, agents/writer.md | 채점은 생성보다 가벼운 작업이라 저렴한 모델로도 충분 — Opus 생성 + Sonnet 채점으로 비용 대비 품질 균형 |
| 2026-07-09 | blog-knowledge-refresh Phase 0: 일반 구글 트렌딩 RSS 대신 건강/보험 카테고리 타겟 웹검색으로 트렌드 신호 확보 | skills/blog-knowledge-refresh | 실측 결과 일반 트렌딩(연예/뉴스 위주)은 건강/보험 블로그와 거의 관련 없음. 타겟 검색으로 "5세대 실손보험" 같은 시의성 높은 신규 주제와 기존 키워드의 최신 각도(예: 갱년기+호르몬요법 재평가)를 확보 가능함을 확인 |
| 2026-07-11 | 보험 단일 블로그 Opus 에이전트 파이프라인 폐기, 무료 Gemini API 기반 5개 블로그(건강/재테크/IT/여행/생활정보) 대량 발행 시스템으로 전면 재구축. `post_insurance.py`→`publisher.py` 리네임, `generate_post.py` 신설(Gemini 직접 호출), `create_pages.py`+`site_config.json`(애드센스 필수 페이지), 테마 5종, `blogs.json` | 전체 | 애드센스 승인 블로그를 다수 운영해 수익화하는 방향으로 프로젝트 목표 전환. 에이전트 파이프라인은 발행당 비용이 과다해 무료 Gemini로 대체 |
| 2026-07-11 | `generate_post.py`에 실시간 트렌드 키워드 시스템 추가 — Gemini Google Search grounding으로 발행 직전 그 블로그 주제의 실시간 인기검색어+연관검색어를 조회해 메인 테마 설정, 조회 실패 시 고정 키워드 파일로 폴백 | generate_post.py | 사전조사 고정 키워드보다 발행 시점의 실제 트렌드를 반영해 시의성 확보 |
| 2026-07-11 | 발행 스케줄링 재설계 — cron 하루 5회(한국 활동시간 집중, KST 08/12/16/20/24시) + `blogs.json` 기반 블로그 순회 + 일일 쿼터 게이트 추가, `publisher.py`의 `INSURANCE_BLOG_URL` 환경변수 최우선 사용 버그 수정(멀티블로그 발행이 전부 한 블로그로 쏠리던 문제) | publish.yml, generate_post.py, publisher.py | 5블로그 동시 운영 시 블로그당 하루 5편을 일정 간격으로 발행하기 위함 |
| 2026-07-11 | `build_prompt`에 1인칭 경험담(E-E-A-T) 지시 추가 — 본문 중 정확히 한 단락에 집중, YMYL 주제는 전문자격 사칭 금지(이용자 입장으로만 서술), 단락 위치는 매번 다르게 | generate_post.py, _knowledge/adsense_writing_guide.md | 구글이 명시한 콘텐츠 품질 신호("첫손 경험")를 반영해 애드센스 승인 가능성 제고 |
| 2026-07-11 | 라벨을 블로그별 고정 카테고리 목록(`blogs.json`의 `categories`)에서만 선택하도록 재설계, 모델이 목록 밖 라벨을 내면 걸러내는 방어 로직(`pick_categories`) 추가 | blogs.json, generate_post.py | 기존엔 키워드 원문+모델 자유생성 라벨이 섞여 매 글마다 라벨이 달라 Blogger 라벨 클라우드(홈 화면 카테고리 칩)가 무의미해지는 문제 발견 |
| 2026-07-11 | 애드센스 필수 페이지에 이용약관 추가(4종→5종), 5개 블로그 전체에 실제 발행 완료 | create_pages.py | 구글 한국 애드센스 가이드 명시 + YMYL 법적 보호 |
| 2026-07-11 | 테마 버그 3건 수정 — 상단 메뉴 홈 버튼 중복(PageList 위젯의 자동 홈 링크와 하드코딩된 홈 링크 중복이 원인), HTTPS 보안 연결 배지 위치(중앙→오른쪽 코너), 푸터 저작권 문구 보완(연도·"All rights reserved." 누락, 미리보기와 실제 XML 불일치) | themes/*.xml | 사장이 실제 업로드해 사용하며 발견 |
| 2026-07-13 | `fetch_live_trends`(grounding) 호출을 블로그당 하루 2회(오전/오후 구간)로 캐싱 — `_knowledge/trend_cache.json`에 블로그별 (날짜, 구간) 키로 트렌드 목록 저장, 같은 구간 재실행은 캐시 재사용. 단종된 `gemini-2.5-flash` 폴백 제거, 전체 실패 시 에러 로그를 모든 시도 취합으로 개선. `publish.yml` 커밋 스텝이 캐시 파일도 함께 커밋하도록 반영 | generate_post.py, .github/workflows/publish.yml | grounding은 본문 생성과 별도의 훨씬 좁은 무료 쿼터를 써서 발행마다 새로 호출하면 금방 429로 소진되는 문제 완화 |
| 2026-07-13 | `call_gemini` 파싱 직후 `sanitize_gemini_result` 후처리 추가 — title/content_html/search_description/image_query/labels에서 `\/`(백슬래시+슬래시)가 남아 있으면 `/`로 되돌림 | generate_post.py | salvia-information2에 실제 발행된 글("청년주택드림 청약통장")에서 `</p>` 등 닫는 태그가 전부 `<\/p>`로 깨져 태그 구조가 무너진 것을 확인. 표준 JSON 이스케이프 `\/`는 `json.loads`가 정상적으로 `/`로 풀어주므로 우리 쪽 파싱 코드 문제는 아니며, Gemini가 raw 응답에 `\\/`(백슬래시 두 개+슬래시, 과잉이스케이프)를 내보낸 경우에만 파싱 후에도 `\/`가 남는다는 것을 합성 재현으로 확정. 실제 API를 8회 재호출해서는 재현되지 않아(2회는 503, 6회는 정상 파싱) 빈도가 낮은 간헐적 모델 결함으로 판단 — 원인이 모델 쪽이므로 코드로 근본 차단은 불가능하고, 후처리 방어만 추가 |
| 2026-07-13 | 보험 단일 블로그 파이프라인 하네스 정리 완료 — `agents/`의 material-researcher, adsense-guide-researcher, writer, publish-engineer, quality-gate 5개 파일과 `skills/`의 blog-knowledge-refresh, insurance-blog-pipeline, blog-pipeline-maintenance, insurance-draft-writing, adsense-quality-scoring 5개 디렉터리 삭제. `.claude/settings.local.json`의 더 이상 존재하지 않는 post_insurance.py/post_insurance.yml 파일 참조(2줄) 제거 | agents/*, skills/*, .claude/settings.local.json | 발행 테스트 검증 완료 후 예정대로 정리. Gemini 기반 5블로그 시스템이 안정적으로 운영 중이므로 구형 Opus 에이전트 하네스는 더 이상 불필요 |
| 2026-07-21 | 발행 cron 하루 5회→3회 축소 | `.github/workflows/publish.yml` | 무료 Gemini API 일일 쿼터 소진으로 인한 연속 발행 실패 방지 |
