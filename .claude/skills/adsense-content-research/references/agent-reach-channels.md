# agent-reach 채널별 사용법

## 로그인 불필요 (자동 실행에서 사용 가능)

| 채널 | 용도 | 사용법 |
|------|------|--------|
| 전체 웹 시맨틱 검색 | 폭넓은 1차 조사, 키워드 관련 자료 후보 탐색 | MCP 도구 직접 호출 (무료, API 키 불필요) |
| 임의 웹페이지 읽기 | 후보 URL 본문을 광고/네비게이션 없이 정제해서 읽기 | `curl https://r.jina.ai/{원본URL}` |
| RSS/Atom | 특정 매체/기관의 최신 소식 추적 | RSS 피드 URL을 읽는 MCP 도구 |
| YouTube 자막 | 전문가 설명 영상에서 텍스트 정보 추출 | 영상 URL로 자막 추출 |
| GitHub | 코드/이슈 검색 (이 도메인에서는 거의 안 씀) | 저장소/이슈 검색 |

## 로그인 필요 (로컬 대화형 세션에서만, 사용자가 명시적으로 요청할 때만)

| 채널 | 명령 예시 | 주의 |
|------|----------|------|
| Twitter/X | `opencli twitter search -f yaml` | Chrome에 로그인 안 되어 있으면 실패 |
| Reddit | `opencli reddit search -f yaml` | 동일 |
| Facebook | `opencli facebook search -f yaml` | 동일 |
| Instagram | `opencli instagram search -f yaml` | 동일 |
| Bilibili | `opencli bilibili search -f yaml` | 한국 보험/건강 주제에는 관련성 낮음 |
| 샤오홍슈 | `opencli xiaohongshu search -f yaml` | 동일 |

이 채널들은 `mcp__agent-reach__get_status`에서 "✅ 설치됨"으로 나와도, 실행 환경에 브라우저 로그인 세션이 없으면 호출 시 로그인 요구 에러가 난다. 자동/헤드리스 실행 중이라면 이 그룹은 아예 시도하지 않는다. 실패 시 재시도하지 말고 즉시 로그인 불필요 채널로 대체한다.

## 실패 시 대체 순서

1. agent-reach 로그인 불필요 채널 시도
2. 실패하면 Claude Code 내장 `WebSearch`/`WebFetch`로 대체
3. 그래도 특정 정보를 못 찾으면 지식 파일에 "확인 필요"로 남기고 넘어간다 — 억지로 채우지 않는다
