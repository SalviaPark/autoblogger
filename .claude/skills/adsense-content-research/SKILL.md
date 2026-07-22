---
name: adsense-content-research
description: 보험/건강 블로그 주제의 기초 취재 자료를 조사하거나, 애드센스 승인 글쓰기 가이드를 갱신할 때 사용한다. agent-reach MCP 채널 선택 전략(로그인 불필요 채널 우선, 헤드리스/자동 실행 환경에서의 제약)과 조사 산출물 저장 규칙을 담고 있다. material-researcher, adsense-guide-researcher 에이전트가 사용한다. "자료 조사해줘", "지식베이스 갱신", "애드센스 가이드 업데이트" 같은 요청에 반드시 사용할 것.
---

# adsense-content-research

## 왜 채널을 가려 써야 하는가

agent-reach MCP의 채널은 두 그룹으로 나뉜다.

- **로그인 불필요 (자동 실행 환경에서도 동작)**: 전체 웹 시맨틱 검색, 임의 웹페이지 읽기(Jina Reader, `curl https://r.jina.ai/URL`), RSS/Atom, YouTube 자막, GitHub.
- **로컬 브라우저 로그인 필요 (OpenCLI 기반, 자동/헤드리스 환경에서 동작 불가)**: Twitter/X, Reddit, Facebook, Instagram, Bilibili, 샤오홍슈.

이 프로젝트의 지식 갱신은 Claude Code 자체 cron 스케줄(주 1회, 사람이 화면 앞에 없는 무인 실행)로 돌아간다. 따라서 **로그인 필요 채널을 기본 조사 경로에 넣지 않는다.** 사용자가 대화형 세션에서 직접 "트위터 반응도 찾아줘"처럼 명시적으로 요청한 경우에만 시도하고, 실패하면(로그인 안 됨) 조용히 건너뛰고 다른 채널로 대체한다.

먼저 `mcp__agent-reach__get_status`로 실제 사용 가능한 채널을 확인한 뒤 조사를 시작한다. 상태가 매번 바뀔 수 있으므로 이전 실행 결과를 가정하지 않는다.

## 조사 절차

1. `get_status`로 채널 확인.
2. 전체 웹 시맨틱 검색으로 폭넓게 후보 출처를 찾는다.
3. 유용해 보이는 URL은 Jina Reader(`curl https://r.jina.ai/URL`)로 본문을 읽는다 — 일반 WebFetch보다 광고/네비게이션이 제거된 깨끗한 텍스트를 얻을 수 있다.
4. 통계·정책·의료 정보처럼 최신성이 중요한 내용은 가능하면 공식 출처(정부 기관, 보험사, 의학회 등)를 우선한다.
5. 상충하는 정보는 버리지 말고 출처와 함께 병기한다 — 삭제는 판단 오류를 감춘다.

## 산출물 저장 규칙

- 기초자료: `_knowledge/topics/{keyword-slug}.md` (형식은 `material-researcher` 에이전트 정의 참고)
- 애드센스 글쓰기 가이드: `_knowledge/adsense_writing_guide.md` (형식은 `adsense-guide-researcher` 에이전트 정의 참고)
- 기존 파일이 있으면 덮어쓰지 말고 **증분 갱신**한다: 새로 확인된 내용만 추가/수정하고, 파일에 변경 이력(날짜 + 요지)을 남긴다.
- 조사가 끝나면 변경된 `_knowledge/` 파일을 git에 커밋한다 (`git add _knowledge/ && git commit -m "..."`). 이 저장소는 push 권한이 있는 로컬/자동 실행 환경이므로, 커밋 후 필요하면 push까지 수행해 다음 GitHub Actions 헤드리스 실행이 최신 지식베이스를 읽을 수 있게 한다.

## 참고

- 채널별 세부 사용법과 실패 시 대체 전략: `references/agent-reach-channels.md`
