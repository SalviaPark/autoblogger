#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gemini로 건강/보험 블로그 글 1편을 생성해 _workspace/{run_id}_final.json으로 저장한다.

사용법: python3 generate_post.py [blog_id]
  blog_id 생략 시 blogs.json의 첫 블로그를 사용.

발행은 publisher.py가 이 final.json을 읽어서 수행한다(인증·이미지·발행 로직은 그쪽 담당).
"""
import json
import os
import random
import re
import sys
import time
from datetime import datetime

from google import genai
from google.genai import types

# google-genai SDK는 http_options.timeout을 명시하지 않으면 None(=무제한 대기)으로
# 처리한다(SDK 내부 HttpOptions.timeout 기본값이 None이고, None이면 httpx 요청에
# timeout=None이 그대로 전달되어 서버가 응답을 안 주면 영원히 대기한다). 2026-07-15
# blog3 발행이 실제로 이렇게 1시간 넘게 멈췄다 — 로그상 "연관검색어: ..." 출력 직후
# call_gemini()의 첫 generate_content() 호출에 들어간 채로 재시도/에러 로그가 단
# 한 줄도 없이 취소될 때까지 침묵했다(예외가 안 났다는 뜻 = 응답 자체가 안 옴).
# 모든 genai.Client() 생성에 명시적 타임아웃을 걸어, 응답이 없으면 예외를 던져
# 기존 재시도 로직(키/모델 전환)이 정상적으로 넘어가게 한다.
GEMINI_TIMEOUT_MS = 120_000
GEMINI_HTTP_OPTIONS = types.HttpOptions(timeout=GEMINI_TIMEOUT_MS)


def gemini_keys():
    """GEMINI_API_KEY, GEMINI_API_KEY_2(있으면)를 키 리스트로 모은다.
    Gemini 무료 quota는 프로젝트(키) 단위라 여러 키로 폴백/로테이션한다.
    둘 다 없으면 명확한 에러로 즉시 종료한다."""
    keys = []
    for name in ("GEMINI_API_KEY", "GEMINI_API_KEY_2"):
        v = os.environ.get(name)
        if v and v not in keys:
            keys.append(v)
    if not keys:
        raise RuntimeError(
            "GEMINI_API_KEY 환경변수가 설정되지 않았습니다. "
            "GEMINI_API_KEY 또는 GEMINI_API_KEY_2 중 최소 하나를 설정하세요."
        )
    return keys


def gemini_paid_key():
    """GEMINI_SUB_API_KEY(결제된 유료 키, 있으면 반환). 무료 키(GEMINI_API_KEY,
    GEMINI_API_KEY_2)가 전부 소진됐을 때만 최후 수단으로 쓴다 — 절대 무료 키보다
    먼저 시도하지 않는다."""
    return os.environ.get("GEMINI_SUB_API_KEY") or None


BLOGS_FILE = "blogs.json"
PUBLISHED_LOG = "_knowledge/published_log.jsonl"
WORKSPACE_DIR = "_workspace"
TREND_CACHE_FILE = "_knowledge/trend_cache.json"
KEY_ROTATION_FILE = "_knowledge/key_rotation.json"


def next_key_rotation():
    """블로그마다 generate_post.py가 별도 프로세스로 실행되기 때문에 전역변수만으로는
    라운드로빈이 매 실행마다 0으로 리셋되어 사실상 항상 키#1부터 쓰게 된다. 카운터를
    파일에 저장해 여러 프로세스 실행을 넘나들며 키가 실제로 번갈아 쓰이게 한다."""
    counter = 0
    if os.path.exists(KEY_ROTATION_FILE):
        try:
            with open(KEY_ROTATION_FILE, encoding="utf-8") as f:
                counter = json.load(f).get("counter", 0)
        except (json.JSONDecodeError, OSError):
            counter = 0
    os.makedirs(os.path.dirname(KEY_ROTATION_FILE), exist_ok=True)
    with open(KEY_ROTATION_FILE, "w", encoding="utf-8") as f:
        json.dump({"counter": counter + 1}, f)
    return counter


def labeled_gemini_keys():
    """무료 키를 로테이션 순서로 배열하고, 유료 키(있으면)를 로테이션 대상에 넣지 않고
    항상 맨 뒤에 최후수단으로 고정 추가한다. call_gemini/fetch_live_trends/
    fetch_related_keywords_for가 공통으로 쓴다."""
    keys = gemini_keys()
    start = next_key_rotation() % len(keys)
    ordered_keys = keys[start:] + keys[:start]
    labeled = [(k, f"key#{i + 1}") for i, k in enumerate(ordered_keys)]
    paid_key = gemini_paid_key()
    if paid_key:
        labeled.append((paid_key, "key#유료(최후수단)"))
    return labeled


def load_blog_config(blog_id=None):
    with open(BLOGS_FILE, encoding="utf-8") as f:
        blogs = json.load(f)["blogs"]
    if not blogs:
        raise SystemExit("blogs.json에 블로그가 없습니다.")
    if blog_id is None:
        return blogs[0]
    for b in blogs:
        if b["id"] == blog_id:
            return b
    raise SystemExit(f"blogs.json에 blog_id '{blog_id}'가 없습니다.")


def parse_keywords(keywords_file):
    """마크다운 표에서 (키워드, 추천 제목 각도 리스트)를 순서대로 뽑는다."""
    with open(keywords_file, encoding="utf-8") as f:
        lines = f.readlines()

    header = None
    kw_idx = None
    angle_idx = None
    keywords = []
    for line in lines:
        s = line.strip()
        if not s.startswith("|"):
            # 표가 끝났으면(이미 시작한 뒤 비표 라인) 중단
            if header is not None:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        # 헤더 탐지
        if header is None:
            if "키워드" in cells and any("제목" in c for c in cells):
                header = cells
                kw_idx = cells.index("키워드")
                angle_idx = next(i for i, c in enumerate(cells) if "제목" in c)
            continue
        # 구분선(---) 스킵
        if set("".join(cells).replace("-", "").replace(":", "")) == set():
            continue
        if len(cells) <= max(kw_idx, angle_idx):
            continue
        keyword = cells[kw_idx]
        if not keyword or keyword == "키워드":
            continue
        raw_angles = cells[angle_idx]
        angles = [a.strip().strip('"').strip() for a in raw_angles.split('",')]
        angles = [a.strip('"').strip() for a in angles if a.strip('"').strip()]
        keywords.append({"keyword": keyword, "angles": angles})
    if not keywords:
        raise SystemExit(f"{keywords_file}에서 키워드 표를 파싱하지 못했습니다.")
    return keywords


def load_log(blog_id):
    """published_log.jsonl을 읽어 이 블로그가 쓴 항목을 최신순 정보로 반환.
    로그 항목에 blog_id가 없으면(기존 포맷) 전부 이 블로그 것으로 간주(현재 블로그 1개)."""
    entries = []
    if not os.path.exists(PUBLISHED_LOG):
        return entries
    with open(PUBLISHED_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("blog_id") not in (None, blog_id):
                continue
            entries.append(e)
    return entries


def _pick_unused_or_oldest(items, log_entries):
    """아직 안 쓴 키워드 우선. 전부 썼으면 가장 오래전에 쓴 키워드 선택.
    items의 각 원소는 "keyword" 키를 가진 dict여야 한다.
    반환: (선택 원소 dict, 이 키워드로 이미 쓴 제목 리스트)."""
    written_titles_by_kw = {}
    last_date_by_kw = {}
    for e in log_entries:
        kw = e.get("keyword", "")
        written_titles_by_kw.setdefault(kw, []).append(e.get("title", ""))
        last_date_by_kw[kw] = e.get("date", "")

    unwritten = [k for k in items if k["keyword"] not in written_titles_by_kw]
    if unwritten:
        chosen = random.choice(unwritten)
    else:
        # 전부 썼으면 가장 오래전에 쓴 키워드(마지막 발행일이 가장 이른 것)
        chosen = min(
            items,
            key=lambda k: last_date_by_kw.get(k["keyword"], ""),
        )
    existing_titles = written_titles_by_kw.get(chosen["keyword"], [])
    return chosen, existing_titles


def select_keyword(keywords, log_entries):
    """고정 키워드 목록(_knowledge/*_keywords_2026.md, 폴백 경로)에서
    아직 안 쓴 키워드 우선, 다 썼으면 가장 오래된 것을 고른다.
    반환: (선택 키워드 dict, 이 키워드로 이미 쓴 제목 리스트)."""
    return _pick_unused_or_oldest(keywords, log_entries)


def select_live_keyword(trends, log_entries):
    """fetch_live_trends()가 반환한 실시간 트렌드 목록에서
    아직 안 쓴 메인키워드 우선, 다 썼으면 가장 오래된 것을 고른다.
    반환: (메인키워드 str, 연관검색어 리스트, 이 키워드로 이미 쓴 제목 리스트)."""
    chosen, existing_titles = _pick_unused_or_oldest(trends, log_entries)
    return chosen["keyword"], chosen.get("related", []), existing_titles


CONCLUSION_PATTERNS = [
    "3문장 요약 + 행동 유도 한 줄로 마무리하라. 판매성·과장 금지.",
    (
        "핵심 체크리스트 3개를 <ul><li> 형식(각 항목 한 문장, 실행 가능한 내용)으로 정리한 뒤 "
        "마무리 한 줄을 덧붙여라. 판매성·과장 금지."
    ),
    (
        "독자가 실제로 궁금해할 질문 2개를 뽑아 <b>Q.</b> 질문 / <b>A.</b> 답변 형식의 미니 "
        "Q&A로 짧게 정리한 뒤 마무리 한 줄을 덧붙여라. 판매성·과장 금지."
    ),
]


def build_prompt(theme, keyword, angles, related_keywords, existing_titles, all_recent_titles, categories):
    """related_keywords가 있으면(실시간 트렌드 경로) 그것을 테마 지시로 우선 사용하고,
    없으면(폴백 경로) 기존 고정 추천 제목 각도(angles)를 사용한다.

    categories: 이 블로그의 고정 카테고리 목록(blogs.json의 "categories"). 라벨을 매 글마다
    새로 짓게 하면(키워드 원문·자유 생성 라벨) Blogger 라벨 클라우드가 무의미해지므로,
    이 목록 중에서만 1~2개를 고르도록 프롬프트로 강제한다.

    반환: (prompt: str, structure: dict). structure는 이번 호출에서 랜덤으로 정한 글 구조
    (h2_count/intro_paragraphs/conclusion_pattern_idx)를 담아 structural_check()가 실제
    생성 결과를 이 목표치와 비교할 수 있게 한다.

    5개 블로그가 동일 테마·동일 프롬프트 골격(도입 3문단, H2 5~6개, 결론+CTA 고정)으로
    발행되면 구글의 "scaled content abuse" 정책에 표면적으로 걸릴 소지가 있어(2026-07-17
    조사), 매 글마다 실제 코드가 무작위 숫자/패턴을 뽑아 프롬프트에 박아넣는다 — 모델에게
    "범위 중 아무거나 골라"라고 맡기면 실제로는 잘 안 흩어지므로, 우리 쪽에서 값을 정한다."""
    h2_count = random.randint(4, 7)
    intro_paragraphs = random.randint(2, 4)
    conclusion_idx = random.randrange(len(CONCLUSION_PATTERNS))
    conclusion_instruction = CONCLUSION_PATTERNS[conclusion_idx]
    structure = {
        "h2_count": h2_count,
        "intro_paragraphs": intro_paragraphs,
        "conclusion_pattern_idx": conclusion_idx,
    }

    angle_hint = ""
    if related_keywords:
        angle_hint = (
            "이번 글의 연관검색어(실시간 인기 검색 기준): " + ", ".join(related_keywords) + "\n"
            "메인키워드와 위 연관검색어들을 자연스럽게 한 글에 담을 수 있는 메인 테마를 먼저 잡고, "
            "그 테마를 중심으로 본문을 전개하라. 연관검색어를 억지로 나열하지 말고 "
            "독자가 실제로 궁금해할 흐름 안에 자연스럽게 녹여라."
        )
    elif angles:
        angle_hint = "추천 글 제목 각도(참고용, 이 중 하나를 골라 발전시키거나 새 각도를 잡아라):\n- " + "\n- ".join(angles)

    dup_block = ""
    avoid_titles = list(dict.fromkeys(existing_titles + all_recent_titles))
    avoid_titles = [t for t in avoid_titles if t]
    if avoid_titles:
        dup_block = (
            "\n[중복 회피 — 매우 중요]\n"
            "다음 제목들은 이미 발행했다. 주제·소제목·구성이 겹치지 않게 반드시 새로운 각도로 써라:\n- "
            + "\n- ".join(avoid_titles)
        )

    category_block = ""
    if categories:
        category_block = (
            "\n[라벨 — 반드시 아래 목록 중에서만 선택]\n"
            "이 블로그의 고정 카테고리 목록: " + ", ".join(categories) + "\n"
            "이번 글 내용과 가장 관련 있는 카테고리를 위 목록에서 정확히 1~2개만 골라 labels에 "
            "표기 그대로(철자·띄어쓰기 그대로) 넣어라. 목록에 없는 라벨을 새로 만들거나, "
            "키워드 원문이나 제목을 그대로 라벨로 쓰지 마라."
        )

    if related_keywords:
        title_block = (
            f"1. 제목(title): 핵심 키워드 \"{keyword}\"를 앞쪽에 두어라. 그다음 아래 연관검색어 중 "
            "'행동직전' 성격(구매·신청·선택·비교·추천·가격·순위·방법처럼 '이제 뭘 어떻게 할지' 찾는 "
            "검색)에 해당하는 표현을 실제로 골라—절대 지어내지 말고 반드시 아래 목록 중에서만—제목에 "
            "자연스럽게 녹여라. 연관검색어: " + ", ".join(related_keywords) + ". "
            "행동직전 성격이 뚜렷한 게 없으면 정보성 연관검색어를 대신 살려서 담아라. "
            "구체적 숫자·연도도 붙여 SEO 제목으로 쓰고, 대괄호는 쓰지 마라. "
            "특정 문장 틀('~효능 제대로 알고 먹는 법, 2026년 ... 선택 기준' 같은 고정 패턴)을 "
            "그대로 반복하지 말고, 이번 연관검색어의 실제 표현에 맞춰 문장 구조 자체를 매번 새로 짜라."
        )
    else:
        title_block = (
            f"1. 제목(title): 핵심 키워드 \"{keyword}\"를 앞쪽에 두고, 정보성 요소('이게 뭔지' — "
            "효능·원인·개념)와 행동직전 요소('실제로 뭘 할지' — 선택 기준·추천·방법)를 둘 다 자연스럽게 "
            "녹여라. 구체적 숫자·연도도 붙여 SEO 제목으로 쓰고, 대괄호는 쓰지 마라. "
            "특정 문장 틀을 고정해서 반복하지 말고 매번 다른 문장 구조로 써라."
        )

    if theme == "건강":
        ymyl_block = (
            "[YMYL·애드센스 원칙 — 필수]\n"
            "- 의학적 단정·치료 효과 주장 금지. \"낫는다/예방된다\"가 아니라 \"~로 알려져 있다\", "
            "\"연구에 따르면\" 톤으로 써라.\n"
            "- 수치·기준은 \"참고 범위이며 확진은 의료기관 검사가 필요하다\"고 안내한다.\n"
            "- 글 말미에 의료 면책 문구를 <p> 한 줄로 반드시 넣어라: \"본 글은 일반적인 건강 정보로 "
            "진단·치료를 대신하지 않으며, 증상이 지속되면 전문의 상담을 권합니다.\"\n"
            "- 처방약(위고비 등)·호르몬요법·정신건강은 '보도된 사실'만 중립 전달하고, 복용·구매를 "
            "권유하지 마라. 정신건강은 '진단'이 아닌 '자가 체크' 톤으로."
        )
    elif theme == "재테크":
        ymyl_block = (
            "[YMYL·애드센스 원칙 — 필수]\n"
            "- 특정 상품·종목의 수익을 단정하거나 보장하지 마라. \"~할 수 있다\", \"~로 알려져 있다\" "
            "톤으로 쓰고 \"무조건 오른다/원금 보장\" 같은 단정적 표현은 쓰지 마라.\n"
            "- 금리·한도·세율 등 수치는 \"시점에 따라 달라질 수 있으니 반드시 해당 기관 공식 정보로 "
            "재확인하라\"고 안내한다.\n"
            "- 글 말미에 투자 면책 문구를 <p> 한 줄로 반드시 넣어라: \"본 글은 정보 제공을 목적으로 "
            "하며 투자 권유가 아니고, 투자 결정과 그 책임은 투자자 본인에게 있습니다.\""
        )
    else:
        ymyl_block = (
            "[정보 신뢰성 원칙 — 필수]\n"
            "- 과장·확정적 단정(\"무조건/100%/역대급\") 대신 \"~로 알려져 있다\", \"~인 경우가 많다\" "
            "톤으로 써라.\n"
            "- 정책·요금·조건처럼 바뀔 수 있는 수치는 \"시점에 따라 달라질 수 있으니 해당 기관 공식 "
            "정보로 재확인하라\"고 안내한다."
        )

    if theme == "건강":
        trusted_orgs = "질병관리청(KDCA), 식품의약품안전처(식약처), 국민건강보험공단 등 보건당국"
    elif theme == "재테크":
        trusted_orgs = "금융감독원, 국세청, 한국은행 등 금융당국"
    elif theme == "IT":
        trusted_orgs = "과학기술정보통신부, 한국인터넷진흥원(KISA), 개인정보보호위원회 등 관련 기관"
    elif theme == "여행":
        trusted_orgs = "한국관광공사, 문화체육관광부, 외교부 해외안전여행 등 관련 기관"
    else:
        trusted_orgs = "공정거래위원회, 한국소비자원 등 관련 공공기관"

    external_link_block = (
        "\n[외부링크 — 신뢰도 신호] 본문 어딘가 자연스러운 문장 안에서 이 글 주제와 관련된 "
        f"신뢰할 수 있는 공공기관·원자료(예: {trusted_orgs})를 1개 정도 인용하라 "
        "(예: \"~에 대한 자세한 기준은 질병관리청에서 확인할 수 있다\"). 그 기관의 정확한 공식 "
        "홈페이지 URL을 알고 있는 경우에만 "
        "<a href=\"URL\" target=\"_blank\" rel=\"noopener noreferrer\">기관명</a> 형태로 링크를 걸어라. "
        "**정확한 URL을 모르면 절대 URL을 추측하거나 지어내지 마라** — 이 경우 링크 없이 기관 이름만 "
        "텍스트로 언급하라. 존재하지 않거나 부정확한 URL을 넣는 것보다 링크를 아예 안 거는 편이 낫다."
    )

    image_query_block = (
        "\n[이미지 검색어(image_query) — 필수]\n"
        f"이 글의 핵심 키워드 \"{keyword}\"와 주제에 맞는 영문 이미지 검색어(image_query)를 만들어라. "
        "Pixabay 같은 스톡사진 사이트에서 이 검색어로 찾았을 때 실제로 주제와 어울리는 사진이 나올 만큼 "
        "구체적이고 시각적인 영문 키워드 조합으로, 2~4단어 정도로 써라. 한글 키워드를 그대로 직역하지 말고, "
        "사진으로 표현 가능한 구체적 대상/장면을 떠올려 영어로 표현하라 "
        "(예: 건강 주제면 'diabetes blood sugar food', 재테크 주제면 'stock market chart growth', "
        "IT 주제면 'smartphone app interface', 여행 주제면 'airport travel suitcase'). "
        "한국 독자 대상 블로그인데 스톡사진 사이트는 서구권 인물 사진이 많아 위화감을 줄 수 있으니, "
        "사람 얼굴/인물이 부각되는 구도보다 사물·음식·제품·차트·풍경처럼 인물이 없거나 눈에 덜 띄는 "
        "소재를 우선하라(예: 'person taking supplement'보다 'milk thistle supplement pills'처럼 "
        "제품/사물 중심 쿼리를 우선). 운동·라이프스타일처럼 글의 주제상 인물이 꼭 필요한 경우에만 "
        "검색어에 'asian'을 넣어 서양인 위주 결과가 나오지 않게 하라(예: 'asian woman exercising home'). "
        "다른 언어나 따옴표 없이 순수 영문 키워드 문자열만 담아라."
    )

    if related_keywords:
        search_description_block = (
            "\n[검색 설명(search_description) — 필수]\n"
            "구글 검색 결과에서 제목 아래 노출되는 요약문(메타 디스크립션)이다. "
            f"핵심 키워드 \"{keyword}\"와 연관검색어(" + ", ".join(related_keywords) + ")를 "
            "억지 나열 없이 자연스러운 문장 흐름 속에 최대한 다 살려 담아라. "
            "정보성 요소('이게 뭔지' — 효능·원인·개념)와 행동직전 요소('실제로 뭘 할지' — "
            "선택 기준·추천·방법)가 한 문장 또는 이어지는 두 문장 안에 함께 느껴지도록 조합해라. "
            "클릭을 유도하는 문장으로 쓰고, 공백 포함 80~160자 사이로 맞춰라(너무 짧거나 길지 않게)."
        )
    else:
        search_description_block = (
            "\n[검색 설명(search_description) — 필수]\n"
            "구글 검색 결과에서 제목 아래 노출되는 요약문(메타 디스크립션)이다. "
            f"핵심 키워드 \"{keyword}\"를 자연스럽게 포함하되, 정보성 요소('이게 뭔지' — 효능·원인·개념)와 "
            "행동직전 요소('실제로 뭘 할지' — 선택 기준·방법·체크포인트)가 함께 느껴지는 문장으로 써라. "
            "클릭을 유도하는 문장(또는 이어지는 두 문장)으로 쓰고, 공백 포함 80~160자 사이로 맞춰라(너무 짧거나 길지 않게)."
        )

    prompt = f"""너는 신문기사처럼 독자에게 정보를 정확하고 친절하게 전달하는 한국어 {theme}정보 기자/에디터다. 핵심을 먼저 던지고 세부로 내려가는 전개로, 직접 겪은 경험과 자료·수치 같은 근거를 바탕으로 정보를 풀어낸다. 금융·의료 초보자도 이해하도록 친근한 구어체와 구체적 숫자를 섞되, 과장 없이 신뢰감 있게 쓴다.

이번 글의 핵심 키워드: "{keyword}"
{angle_hint}

[글 구조 — 반드시 준수]
{title_block}
2. 도입부: {intro_paragraphs}문단 내외, 각 3~4문장. 숫자·공감으로 시작(예: "검진 결과지에서 이 수치 보고 덜컥 하신 적 있죠?"). 이 글이 뭘 알려주는지 예고.
3. 본문 소제목: <h2> 태그로 정확히 {h2_count}개, "1. ...", "2. ..." 번호를 매긴다. 전개 순서는 정보성(개념·원인·수치 설명)에서 시작해 후반부로 갈수록 행동직전(선택 기준·비교·추천 방법)으로 이어지게 배치하라 — 독자가 "이게 뭔지" 이해한 다음 "그래서 뭘 어떻게 하면 되는지"까지 알 수 있도록. 각 섹션은 5~7개 항목의 <ul><li> 불릿 또는 <table> 비교표를 포함하고, 설명을 충실히 채운다. 소제목은 반드시 <h2>로 (다른 헤딩 태그 금지).
4. 결론+CTA: {conclusion_instruction}

[강조] 핵심 숫자·용어(수치, 기준값, 성분명)는 <b>로 볼드 처리해 가시성을 높여라.

[분량] 본문 2,800~3,500자(한글 기준). 이 범위를 지켜라. 단 같은 말 반복이나 물타기로 분량을 늘리지 말고, 구체적 수치·예시·체크리스트·비교표 같은 실질 정보로 각 섹션을 충실히 채워 분량을 확보하라.

[키워드 반복 — SEO] 핵심 키워드 "{keyword}"를 본문 전체에 걸쳐 자연스럽게 3~4회 이상 반복 사용하라(제목·소제목은 카운트하지 않고 본문 <p> 문장 안에서만 센다). 억지로 욱여넣지 말고 문맥에 맞게, 매번 조금씩 다른 문장 안에서 자연스럽게 등장시켜라.

[어체 — 친근한 구어체] 레퍼런스처럼 독자에게 말을 거는 친근한 구어체와 공감 표현을 살려라(예: "~해보신 적 있으시죠?", "저도 그랬어요", "이 수치 보고 덜컥 하신 분 많으실 거예요"). 딱딱한 설명문이 아니라 옆에서 알려주는 말투로 쓰되, 건강은 YMYL(민감 주제)이므로 "역대급/무조건 낫는다/지금 즉시" 같은 과장·의학적 단정·긴급성 조장은 절대 쓰지 마라. 친근하되 신뢰감 있게.

[경험담 — 신뢰 신호(E-E-A-T), 필수] 본문 중 정확히 한 곳(하나의 독립된 단락)에 이번 글의 핵심 키워드 "{keyword}"와 직접 관련된 1인칭 경험담을 몰아서 써라. 여러 문단에 나눠 흩뿌리지 말고 한 단락에 집중하라. "저도 얼마 전에 ~한 적이 있었는데요", "재작년에 이런 일을 겪었어요" 처럼 시점을 밝히며 시작해서, 그때 상황과 느낌을 구체적으로 묘사하라("저도 경험이 있어요" 같은 뻔한 한 줄로 끝내지 마라 — 언제, 무슨 상황이었는지, 어떤 기분이었는지가 드러나야 한다). 단, 의사·약사·보험설계사·세무사 등 전문 자격을 가진 것처럼 쓰지 말고 어디까지나 환자/가입자/이용자 같은 일반 독자 입장에서 겪은 경험으로만 서술하라. 이 단락의 위치(도입부/본문 중간/결론)는 매번 다르게 잡아 똑같은 공식처럼 반복되지 않게 하고, 글 흐름상 자연스러운 곳에만 넣어라 — 억지로 끼워 맞추지 마라.

{ymyl_block}
{external_link_block}
{dup_block}

[연도 — 매우 중요] 오늘은 2026년이다. 반드시 2026년 현재 시점으로 작성하고, 2024/2025 등 과거 연도를 '최신'인 것처럼 쓰지 마라. 연도를 표기해야 하면 2026년을 쓰라.

[이미지] 본문에 <img> 태그를 절대 넣지 마라(발행 단계에서 자동 삽입한다).
{search_description_block}
{image_query_block}

[출력] content_html은 <p>, <h2>, <ul>/<li>, <table>, <b>, <a> 태그만 사용한다. <a> 태그는 위 [외부링크] 지시에 따라 실제로 아는 URL에만 쓰고, 반드시 target="_blank" rel="noopener noreferrer" 속성을 포함하라. <html>/<body> 래퍼 없이 본문 조각만 담아라. search_description과 image_query는 태그 없는 순수 텍스트로 채워라.
{category_block}"""
    return prompt, structure


RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    required=["title", "content_html", "labels", "search_description", "image_query"],
    properties={
        "title": types.Schema(type=types.Type.STRING),
        "content_html": types.Schema(type=types.Type.STRING),
        "labels": types.Schema(
            type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
        ),
        "search_description": types.Schema(type=types.Type.STRING),
        "image_query": types.Schema(type=types.Type.STRING),
    },
)


def trend_period(now):
    """실시간 트렌드 캐시를 오전/오후 두 구간으로 나누는 기준.
    cron은 UTC 기준 하루 5회(KST 08/12/16/20/24시 = UTC 23/3/7/11/15시) 실행된다.
    이 중 KST 08·12시(UTC 23·03시)를 '오전' 구간, KST 16·20·24시(UTC 07·11·15시)를
    '오후' 구간으로 묶는다 — UTC 06시 이전(21~05시대)은 morning, 그 외(06~20시대)는
    afternoon으로 판정하면 위 다섯 시각이 의도한 대로 두 구간에 갈린다."""
    hour = now.hour
    return "morning" if (hour < 6 or hour >= 21) else "afternoon"


def load_trend_cache():
    if not os.path.exists(TREND_CACHE_FILE):
        return {}
    try:
        with open(TREND_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_trend_cache(cache):
    os.makedirs(os.path.dirname(TREND_CACHE_FILE), exist_ok=True)
    with open(TREND_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_trends(blog_id, theme, today, period):
    """오늘 날짜+구간(오전/오후)으로 캐시된 트렌드가 있으면 그대로 재사용하고,
    없으면(첫 호출이거나 구간이 바뀌었으면) grounding을 호출해 새로 받아온 뒤 캐시에 저장한다.
    캐시 파일은 git에 커밋되어 다음 GitHub Actions 실행(새 서버)에서도 읽을 수 있어야 한다."""
    cache = load_trend_cache()
    cached = cache.get(blog_id)
    if cached and cached.get("date") == today and cached.get("period") == period:
        trends = cached.get("trends") or []
        if trends:
            print(
                f"  [캐시] {today} {period} 구간 트렌드 캐시 재사용 ({len(trends)}건) — grounding 호출 생략",
                file=sys.stderr,
            )
            return trends

    trends = fetch_live_trends(theme)
    cache[blog_id] = {"date": today, "period": period, "trends": trends}
    save_trend_cache(cache)
    return trends


def fetch_live_trends(theme):
    """Gemini의 Google Search grounding으로 대한민국 {theme} 카테고리 실시간 인기 검색어와
    각 연관검색어를 조회한다.

    grounding 툴(google_search)은 response_schema(JSON 강제 스키마)와 동시 사용이 불가능하므로
    스키마 없이 텍스트로 받아 코드펜스(```json)를 벗기고 json.loads로 파싱한다.
    call_gemini와 동일하게 키 로테이션을 적용해 한 키가 429여도 다음 키로 넘어가게 한다.
    조회/파싱에 실패하거나 결과가 비어 있으면 예외를 던져 호출부가 폴백하도록 한다.

    반환: [{"keyword": str, "related": [str, ...]}, ...]
    """
    prompt = (
        f"지금 대한민국에서 '{theme}' 카테고리의 실시간 인기 검색어 상위 10개를 알려줘. "
        "각 검색어마다 연관검색어 3개를 실제로 검색해서 찾아 붙여줘. 연관검색어는 두 성격을 "
        "반드시 섞어라: "
        "(1) 정보성 연관검색어 — 개념·원인·수치처럼 '이게 뭔지 알고 싶다'는 검색 "
        "(예: '효능', '원인', '정상 수치'), "
        "(2) 행동직전 연관검색어 — 구매·신청·선택·비교처럼 '이제 실제로 뭘 어떻게 할지' "
        "확인하려는 검색 (예: '추천', '가입방법', '순위', '비교', '가격'). "
        "3개 중 최소 1개는 반드시 행동직전 성격이어야 한다. "
        "단, 절대 추측이나 창작으로 채우지 마라 — 행동직전 연관검색어도 예외 없이 네가 "
        "실제로 검색을 수행해서 확인된 것만 담아라. 실제 검색으로 행동직전 성격의 연관검색어가 "
        "확인되지 않으면 억지로 지어내지 말고 정보성 연관검색어로 대신 채워라. "
        "반드시 순수 JSON 배열로만 답하고 다른 말은 하지 마. "
        '형식: [{"keyword":"...","related":["...","...","..."]}]'
    )
    tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[tool])

    # gemini-2.5-flash-lite는 2026-07-13 실측(무료 키 2개 모두)에서 404
    # "This model models/gemini-2.5-flash-lite is no longer available to new
    # users"로 확인되어 제거 — grounding 경로는 gemini-flash-latest 하나만 사용한다.
    models = ["gemini-flash-latest"]
    errors = []
    last_error = None
    for key, key_label in labeled_gemini_keys():
        for model in models:
            client = genai.Client(api_key=key, http_options=GEMINI_HTTP_OPTIONS)
            try:
                response = client.models.generate_content(
                    model=model, contents=prompt, config=config
                )
                text = re.sub(r"```(?:json)?", "", response.text).strip()
                trends = json.loads(text)
                if not isinstance(trends, list) or not trends:
                    raise ValueError("빈 결과이거나 배열이 아님")
                cleaned = []
                for t in trends:
                    kw = (t.get("keyword") or "").strip()
                    if not kw:
                        continue
                    related = [r.strip() for r in (t.get("related") or []) if r and r.strip()]
                    cleaned.append({"keyword": kw, "related": related})
                if not cleaned:
                    raise ValueError("파싱 후 유효한 키워드가 없음")
                print(
                    f"  [{key_label}/{model}] 실시간 트렌드 조회 성공 ({len(cleaned)}건)",
                    file=sys.stderr,
                )
                return cleaned
            except Exception as e:
                last_error = e
                errors.append(f"[{key_label}/{model}] {e.__class__.__name__}: {e}")
                print(
                    f"  [{key_label}/{model}] 실시간 트렌드 조회 실패 ({e.__class__.__name__}: {e})",
                    file=sys.stderr,
                )
    error_summary = " | ".join(errors) if errors else "알 수 없는 오류"
    raise RuntimeError(f"실시간 트렌드 조회 전체 실패({len(errors)}건 시도): {error_summary}") from last_error


def fetch_related_keywords_for(keyword):
    """트렌드 목록이 아니라 고정 키워드 목록(_knowledge/*_keywords_2026.md)에서 고른 키워드
    하나에 대해, fetch_live_trends와 동일한 원칙(추측·창작 절대 금지, 실제 검색 결과만)으로
    연관검색어(정보성+행동직전 혼합) 3개를 조회한다. 이렇게 고정 키워드도 실검색 기반
    연관검색어를 붙여서, 트렌드 경로와 동일하게 제목에 실제 행동직전 표현을 반영할 수 있게 한다.

    조회/파싱에 실패하면 예외를 던진다 — 호출부가 related_keywords 없이 진행하도록 처리."""
    prompt = (
        f"지금 대한민국에서 '{keyword}'를 검색하는 사람들의 연관검색어 3개를 실제로 검색해서 "
        "찾아줘. 연관검색어는 두 성격을 반드시 섞어라: "
        "(1) 정보성 연관검색어 — 개념·원인·수치처럼 '이게 뭔지 알고 싶다'는 검색 "
        "(예: '효능', '원인', '정상 수치'), "
        "(2) 행동직전 연관검색어 — 구매·신청·선택·비교처럼 '이제 실제로 뭘 어떻게 할지' "
        "확인하려는 검색 (예: '추천', '가입방법', '순위', '비교', '가격'). "
        "3개 중 최소 1개는 반드시 행동직전 성격이어야 한다. "
        "단, 절대 추측이나 창작으로 채우지 마라 — 행동직전 연관검색어도 예외 없이 네가 "
        "실제로 검색을 수행해서 확인된 것만 담아라. 실제 검색으로 행동직전 성격의 연관검색어가 "
        "확인되지 않으면 억지로 지어내지 말고 정보성 연관검색어로 대신 채워라. "
        "반드시 순수 JSON 배열로만 답하고 다른 말은 하지 마. "
        '형식: ["...", "...", "..."]'
    )
    tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[tool])

    # gemini-2.5-flash-lite는 2026-07-13 실측(무료 키 2개 모두)에서 404
    # "This model models/gemini-2.5-flash-lite is no longer available to new
    # users"로 확인되어 제거 — grounding 경로는 gemini-flash-latest 하나만 사용한다.
    models = ["gemini-flash-latest"]
    errors = []
    last_error = None
    for key, key_label in labeled_gemini_keys():
        for model in models:
            client = genai.Client(api_key=key, http_options=GEMINI_HTTP_OPTIONS)
            try:
                response = client.models.generate_content(
                    model=model, contents=prompt, config=config
                )
                text = re.sub(r"```(?:json)?", "", response.text).strip()
                related = json.loads(text)
                if not isinstance(related, list) or not related:
                    raise ValueError("빈 결과이거나 배열이 아님")
                cleaned = [r.strip() for r in related if isinstance(r, str) and r.strip()]
                if not cleaned:
                    raise ValueError("파싱 후 유효한 연관검색어가 없음")
                print(
                    f"  [{key_label}/{model}] 키워드 연관검색어 조회 성공 ({len(cleaned)}건)",
                    file=sys.stderr,
                )
                return cleaned
            except Exception as e:
                last_error = e
                errors.append(f"[{key_label}/{model}] {e.__class__.__name__}: {e}")
                print(
                    f"  [{key_label}/{model}] 키워드 연관검색어 조회 실패 ({e.__class__.__name__}: {e})",
                    file=sys.stderr,
                )
    error_summary = " | ".join(errors) if errors else "알 수 없는 오류"
    raise RuntimeError(f"키워드 연관검색어 조회 전체 실패({len(errors)}건 시도): {error_summary}") from last_error


def sanitize_gemini_result(result):
    """Gemini 구조화 출력(JSON)이 가끔 '/' 를 과잉이스케이프(raw 응답에 '\\\\/', 즉 백슬래시
    두 개 + 슬래시)해서 내보내는 문제를 후처리로 되돌린다.

    표준 JSON에서 '\\/' (백슬래시 하나 + 슬래시)는 '/'의 합법적인 이스케이프라 json.loads가
    알아서 '/'로 풀어준다. 문제는 모델이 이스케이프 문자 자체를 한 번 더 이스케이프해서
    raw 텍스트에 '\\\\/' 를 내보내는 경우인데, 이때는 json.loads를 거쳐도 결과 파이썬
    문자열에 '\\/' (백슬래시 하나 + 슬래시)가 글자 그대로 남는다.
    실제 사례: content_html의 '</p>'가 '<\\/p>'로 그대로 박혀 발행되어 브라우저가 닫는
    태그로 인식하지 못하고 태그 구조가 깨진 채 노출됐다(2026-07 salvia-information2,
    '청년주택드림 청약통장' 글).

    정상적인 한국어 본문에는 백슬래시가 등장할 일이 없으므로, json.loads 이후 문자열에
    남아있는 '\\/' 는 전부 이 버그의 흔적으로 보고 '/'로 되돌려도 안전하다."""
    text_fields = ("title", "content_html", "search_description", "image_query")
    for key in text_fields:
        value = result.get(key)
        if isinstance(value, str):
            result[key] = value.replace("\\/", "/")
    labels = result.get("labels")
    if isinstance(labels, list):
        result["labels"] = [
            l.replace("\\/", "/") if isinstance(l, str) else l for l in labels
        ]
    return result


def _is_daily_quota_exhausted(e):
    """무료 티어 '일일' 한도 초과(GenerateRequestsPerDayPerProjectPerModel-FreeTier)인지 판별.
    이 경우 몇 초~몇십 초 대기 후 재시도해도 절대 풀리지 않으므로(하루 단위 리셋),
    재시도는 시간 낭비이자 불필요한 추가 호출이라 즉시 다음 키로 넘어가야 한다."""
    return "PerDayPerProjectPerModel" in str(e)


def call_gemini(prompt):
    """gemini-flash-latest 단일 모델에 키 폴백을 얹는다.
    gemini-2.5-flash는 무료 키 기준 완전히 단종(404) 확인되어 제거했다(fetch_live_trends와 동일).
    라운드로빈으로 시작 키를 고르고, 그 키가 quota 초과/오류로 실패하면 다음 키로 폴백한다.
    키가 하나뿐이면 기존과 동일하게 동작한다.
    단일 모델만 남은 만큼, 키 하나당 재시도 횟수를 3회→4회로 늘려 순간적인 429/503에
    대한 복원력을 약간 더 확보한다. 단, 일일 한도 초과는 재시도해도 풀리지 않으므로
    즉시 다음 키로 폴백한다(_is_daily_quota_exhausted)."""
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=RESPONSE_SCHEMA,
    )
    labeled_keys = labeled_gemini_keys()

    # gemini-2.5-flash-lite는 2026-07-13 실측(무료 키 2개 모두)에서 404
    # "This model models/gemini-2.5-flash-lite is no longer available to new
    # users"로 확인되어 제거 — 본문 생성도 gemini-flash-latest 하나만 사용한다.
    models = ["gemini-flash-latest"]
    # (2026-07-17 쿼터 공정성 검토) retries는 그대로 4 유지 — 일일 한도 초과
    # (_is_daily_quota_exhausted, blog4/5가 겪는 실제 문제)는 재시도 없이 즉시
    # 다음 키로 넘어가므로 이 값을 줄여도 일일 쿼터 낭비는 전혀 줄지 않는다.
    # 반면 503(일시 서버 과부하)은 대기 후 재시도하면 실제로 복구되는 경우가
    # 많아서, 줄이면 쿼터 절감 효과 없이 정상 복구될 시도까지 포기하는
    # 손해만 커진다 — 그대로 둔다.
    retries = 4
    errors = []
    last_error = None
    for key_i, (key, key_label) in enumerate(labeled_keys):
        client = genai.Client(api_key=key, http_options=GEMINI_HTTP_OPTIONS)
        for model in models:
            for attempt in range(retries):
                try:
                    response = client.models.generate_content(
                        model=model, contents=prompt, config=config
                    )
                    text = re.sub(r"```(?:json)?", "", response.text).strip()
                    return sanitize_gemini_result(json.loads(text))
                except Exception as e:
                    last_error = e
                    errors.append(f"[{key_label}/{model}] {e.__class__.__name__}: {e}")
                    if _is_daily_quota_exhausted(e):
                        print(
                            f"  [{key_label}/{model}] 일일 한도 초과 — 재시도 없이 다음 키로 전환 "
                            f"({e.__class__.__name__})",
                            file=sys.stderr,
                        )
                        break
                    if attempt < retries - 1:
                        wait = 60 if "503" in str(e) or "UNAVAILABLE" in str(e) else 10
                        print(
                            f"  [{key_label}/{model}] Gemini 오류 ({e.__class__.__name__}: {e}), "
                            f"{wait}초 후 재시도... ({attempt+1}/{retries})",
                            file=sys.stderr,
                        )
                        time.sleep(wait)
                    else:
                        print(
                            f"  [{key_label}/{model}] {retries}회 실패, 다음 모델로 전환 "
                            f"(마지막 오류: {e.__class__.__name__}: {e})",
                            file=sys.stderr,
                        )
        if len(labeled_keys) > 1 and key_i < len(labeled_keys) - 1:
            print(f"  [{key_label}] 모든 모델 실패, 다음 키로 폴백", file=sys.stderr)
    error_summary = " | ".join(errors) if errors else "알 수 없는 오류"
    raise RuntimeError(f"본문 생성 전체 실패({len(errors)}건 시도): {error_summary}") from last_error


def _significant_tokens(title, stopwords=frozenset()):
    """제목/소제목에서 숫자·특수문자를 제거하고 2글자 이상 토큰만 남긴 뒤,
    stopwords(블로그 장르 상투어)에 해당하는 토큰은 제외한다. stopwords 없이
    호출하면 기존과 동일하게 동작한다."""
    cleaned = re.sub(r"[0-9]+", " ", title)
    cleaned = re.sub(r"[^\w가-힣 ]", " ", cleaned)
    return {t for t in cleaned.split() if len(t) >= 2 and t not in stopwords}


def is_duplicate(title, content_html, existing_titles, stopwords=frozenset(), keyword=None):
    """생성 제목/소제목이 기존 제목과 핵심어 다수(>=2) 겹치면 중복으로 본다.

    stopwords로 "효능/부작용/추천" 같은 블로그 장르 공통 상투어를 먼저 걸러낸 뒤
    비교한다 — 상투어만 겹치고 실제 주제어(성분명 등)는 하나도 안 겹치는데 중복
    판정되는 오탐(실측: 무관 성분 10개 45쌍 100% 오탐)을 막기 위함이다. 상투어를
    걸러내면 겹침이 희소해지므로 임계값도 3->2로 낮췄다.

    keyword(현재 시도 중인 키워드)가 주어지면 보조 가드를 추가로 적용한다: 겹친
    토큰 안에 keyword의 핵심어가 없고 keyword 문자열 자체가 old 제목에 포함되지도
    않으면, 상투어 걸러내기 이후에도 우연히 남은 겹침으로 보고 중복 판정에서 제외한다."""
    h2_texts = re.findall(r"<h2[^>]*>(.*?)</h2>", content_html, re.DOTALL)
    gen_tokens = _significant_tokens(title, stopwords)
    for h in h2_texts:
        gen_tokens |= _significant_tokens(re.sub(r"<[^>]+>", "", h), stopwords)
    keyword_tokens = _significant_tokens(keyword, stopwords) if keyword else set()
    for old in existing_titles:
        overlap = gen_tokens & _significant_tokens(old, stopwords)
        if len(overlap) < 2:
            continue
        if keyword_tokens and not (keyword_tokens & overlap) and keyword not in old:
            continue
        return True, old
    return False, None


def pick_categories(model_labels, categories):
    """모델이 제안한 라벨 중 blogs.json의 고정 카테고리 목록에 정확히 일치하는 것만 남긴다
    (순서 유지, 중복 제거, 최대 2개). categories가 비어 있으면(블로그에 미설정) 빈 리스트를
    반환해 예전처럼 자유 라벨을 라벨에 섞는 일이 없도록 한다."""
    if not categories:
        return []
    picked = [l for l in model_labels if l in categories]
    return list(dict.fromkeys(picked))[:2]


def visible_length(content_html):
    text = re.sub(r"<[^>]+>", "", content_html)
    text = re.sub(r"\s+", "", text)
    return len(text)


THEME_DISCLAIMER_MARKERS = {
    "건강": "본 글은 일반적인",
    "재테크": "본 글은 정보 제공을 목적으로",
}


def structural_check(result, keyword, structure=None, theme=None):
    """call_gemini()가 반환한 result를 순수 파이썬 로직으로만(추가 API 호출 없이) 검증한다.

    실패하면 (False, 사유 문자열), 통과하면 (True, "")를 반환한다. main()에서
    call_gemini() 성공 직후, is_duplicate() 체크와 같은 자리에서 호출되어 실패 시
    기존 키워드 재시도(escalation) 루프로 자연스럽게 편입된다 — 구조 검증 실패도
    중복과 마찬가지로 "이번 결과는 못 쓴다"는 신호이므로 다음 키워드로 넘어간다."""
    title = (result.get("title") or "").strip()
    content_html = result.get("content_html") or ""

    if len(title) < 5:
        return False, f"제목이 비정상적으로 짧거나 비어 있음({len(title)}자): {title!r}"

    length = visible_length(content_html)
    if length < 2000:
        return False, f"본문 가시 글자수 부족({length}자, 지시 범위 2,800~3,500자 대비 최소 2,000자 미달)"
    if length > 4500:
        return False, f"본문 가시 글자수 초과({length}자, 지시 범위 2,800~3,500자 대비 최대 4,500자 초과)"

    h2_count = len(re.findall(r"<h2[^>]*>", content_html))
    if h2_count < 3:
        return False, f"<h2> 개수 부족({h2_count}개, 최소 3개 필요)"
    target_h2 = (structure or {}).get("h2_count")
    if target_h2 and abs(h2_count - target_h2) > 3:
        return False, f"<h2> 개수({h2_count}개)가 이번에 지시한 목표({target_h2}개)와 크게 어긋남"

    if "<img" in content_html.lower():
        return False, "본문에 <img> 태그가 포함됨(이미지는 발행 단계에서 삽입해야 함)"

    disclaimer_marker = THEME_DISCLAIMER_MARKERS.get(theme)
    if disclaimer_marker and disclaimer_marker not in content_html:
        return False, f"테마 '{theme}'의 필수 YMYL 면책 문구가 본문에 없음"

    return True, ""


def choose_keyword(live_trends, fixed_keywords, log_entries, exclude=frozenset()):
    """우선순위(live-미사용 > fixed-미사용 > live-재사용 > fixed-재사용)로 키워드 하나를
    고른다. exclude에 있는 키워드는 이번 실행에서 이미 시도했다가 중복으로 실패한
    것들이라 후보에서 제외한다 — main()이 한 키워드로 계속 중복이 나면 다른 키워드로
    바꿔서 재시도할 수 있게 해준다.

    반환: {"keyword", "related_keywords", "angles", "existing_titles", "source"} 또는,
    exclude 때문에 더 고를 후보가 없으면 None."""
    written_keywords = {e.get("keyword", "") for e in log_entries}
    live_pool = [t for t in live_trends if t["keyword"] not in exclude]
    fixed_pool = [k for k in fixed_keywords if k["keyword"] not in exclude]

    unused_trends = [t for t in live_pool if t["keyword"] not in written_keywords]
    if unused_trends:
        keyword, related_keywords, existing_titles = select_live_keyword(unused_trends, log_entries)
        return {
            "keyword": keyword, "related_keywords": related_keywords, "angles": [],
            "existing_titles": existing_titles, "source": "live",
        }

    unused_fixed = [k for k in fixed_pool if k["keyword"] not in written_keywords]
    if unused_fixed:
        chosen, existing_titles = select_keyword(unused_fixed, log_entries)
        related_keywords = []
        # 고정 키워드도 트렌드 경로와 동일하게 실검색 기반 연관검색어를 붙여서,
        # 제목에 실제 행동직전 표현을 반영할 수 있게 한다(추측·창작 금지 원칙 유지).
        try:
            related_keywords = fetch_related_keywords_for(chosen["keyword"])
            print(f"연관검색어(고정 키워드 실검색): {', '.join(related_keywords)}", file=sys.stderr)
        except Exception as e:
            print(
                f"  키워드 연관검색어 조회 실패({e.__class__.__name__}: {e}) — 연관검색어 없이 진행",
                file=sys.stderr,
            )
        return {
            "keyword": chosen["keyword"], "related_keywords": related_keywords,
            "angles": chosen["angles"], "existing_titles": existing_titles,
            "source": "fallback-fixed",
        }

    if live_pool:
        keyword, related_keywords, existing_titles = select_live_keyword(live_pool, log_entries)
        return {
            "keyword": keyword, "related_keywords": related_keywords, "angles": [],
            "existing_titles": existing_titles, "source": "live-재사용",
        }

    if fixed_pool:
        chosen, existing_titles = select_keyword(fixed_pool, log_entries)
        return {
            "keyword": chosen["keyword"], "related_keywords": [], "angles": chosen["angles"],
            "existing_titles": existing_titles, "source": "fallback-fixed-재사용",
        }

    return None


def main():
    blog_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    blog = load_blog_config(blog_id_arg)

    log_entries = load_log(blog["id"])

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    period = trend_period(now)
    today_count = sum(1 for e in log_entries if e.get("date") == today)
    if today_count >= blog.get("posts_per_day", 0):
        print(
            f"오늘({today}) 블로그 '{blog['id']}'는 이미 {today_count}편 발행해 "
            f"일일 한도({blog.get('posts_per_day', 0)}편)에 도달했습니다 — 이번 실행은 건너뜁니다.",
            file=sys.stderr,
        )
        return

    all_recent_titles = [e.get("title", "") for e in log_entries][-20:]
    # 프롬프트에 "피해야 할 제목"으로 힌트를 주는 all_recent_titles와 달리, 실제 중복
    # 여부를 최종 판정하는 안전망(is_duplicate)은 블로그 전체 발행 이력과 비교해야
    # 한다 — 최근 20건으로만 제한하면 블로그가 20건을 넘어선 뒤로는 오래된 글과의
    # 중복을 놓친다.
    all_titles_for_dup_check = [e.get("title", "") for e in log_entries if e.get("title")]

    live_trends = []
    try:
        live_trends = get_trends(blog["id"], blog["theme"], today, period)
    except Exception as e:
        print(
            f"[트렌드 조회 실패]({e.__class__.__name__}: {e})",
            file=sys.stderr,
        )
    fixed_keywords = parse_keywords(blog["keywords_file"])

    categories = blog.get("categories", [])
    blog_stopwords = frozenset(blog.get("stopwords", []))

    # 같은 키워드로 재생성해도 구조가 비슷하게 나오는 경우가 많아(실측 확인)
    # 재생성 대신 이미 안 쓴 걸로 확인된 다음 키워드로 바로 전환한다 — 매번
    # 전체 프롬프트를 다시 보내는 호출을 아끼면서 성공률도 더 높다.
    # 4->2: choose_keyword()가 안 쓴 키워드를 최우선으로 고르므로 첫 시도에서
    # 중복/구조검증에 걸릴 확률 자체가 낮고, 이번 실행이 실패해도 하루 5회 cron이
    # 몇 시간 뒤 재시도하므로 장기적 손해가 크지 않다. 반면 escalation 1회당 최악
    # 3키×4회 재시도=12콜까지 소비할 수 있어(무료 키가 먼저 소진되는 blog4/5에
    # 특히 치명적), 시도 횟수를 줄이는 쪽이 쿼터 공정성 문제에 가장 직접적으로
    # 효과가 있다고 판단해 2로 낮춘다(사장이 제안한 1차 값).
    max_keyword_attempts = 2
    tried_keywords = set()
    result = None
    keyword = None
    for keyword_attempt in range(max_keyword_attempts):
        sel = choose_keyword(live_trends, fixed_keywords, log_entries, exclude=tried_keywords)
        if sel is None:
            print(f"[{blog['id']}] 더 시도할 키워드 후보가 없습니다 — 이번 실행은 건너뜁니다.", file=sys.stderr)
            return
        tried_keywords.add(sel["keyword"])
        keyword = sel["keyword"]
        related_keywords = sel["related_keywords"]
        angles = sel["angles"]
        existing_titles = sel["existing_titles"]
        print(
            f"[경로: {sel['source']}] 선택 키워드: {keyword} (기존 발행 {len(existing_titles)}건, "
            f"키워드 시도 {keyword_attempt + 1}/{max_keyword_attempts})",
            file=sys.stderr,
        )
        if related_keywords:
            print(f"연관검색어: {', '.join(related_keywords)}", file=sys.stderr)

        prompt, structure = build_prompt(
            blog["theme"], keyword, angles, related_keywords, existing_titles, all_recent_titles, categories
        )
        print(
            f"  [글 구조] H2 {structure['h2_count']}개 / 도입부 {structure['intro_paragraphs']}문단 / "
            f"결론 패턴#{structure['conclusion_pattern_idx'] + 1}",
            file=sys.stderr,
        )

        try:
            candidate = call_gemini(prompt)
        except Exception as e:
            print(f"[{blog['id']}] 본문 생성 실패: {e}", file=sys.stderr)
            sys.exit(1)

        struct_ok, struct_reason = structural_check(candidate, keyword, structure, blog["theme"])
        if not struct_ok:
            print(
                f"[{blog['id']}] '{keyword}' 키워드 결과가 구조 검증 실패({struct_reason}) "
                "— 다른 키워드로 전환합니다.",
                file=sys.stderr,
            )
            continue

        dup_check_titles = existing_titles + all_titles_for_dup_check
        dup, clash = is_duplicate(
            candidate["title"], candidate["content_html"], dup_check_titles,
            stopwords=blog_stopwords, keyword=keyword,
        )
        if not dup:
            result = candidate
            break
        print(
            f"[{blog['id']}] '{keyword}' 키워드가 '{clash}'와 중복 — 다른 키워드로 전환합니다.",
            file=sys.stderr,
        )

    if result is None:
        # 블로그 안에서 절대 중복 발행이 나오면 안 되므로, 키워드를 바꿔가며 시도해도
        # 다 실패하면 발행을 강행하지 않고 이번 실행을 건너뛴다(다음 발행 주기에
        # 새 트렌드/키워드로 다시 시도하게 된다).
        print(
            f"[{blog['id']}] 키워드 {max_keyword_attempts}개를 바꿔가며 시도해도 중복 회피 실패 "
            "— 이번 실행은 발행하지 않고 건너뜁니다.",
            file=sys.stderr,
        )
        return

    # 라벨: 블로그 기본 라벨(최상위 고정 태그) + 고정 카테고리 목록 중 모델이 고른 1~2개.
    # 키워드 원문이나 모델이 자유롭게 지어낸 라벨은 더 이상 섞지 않는다 — 매 글마다 달라지는
    # 라벨은 Blogger 라벨 클라우드에서 관련 글을 묶어주지 못해 사실상 무의미하기 때문이다.
    model_labels = result.get("labels", []) or []
    picked_categories = pick_categories(model_labels, categories)
    if categories and not picked_categories:
        print(
            f"경고: 모델이 고정 카테고리 목록에서 라벨을 고르지 못함(모델 출력: {model_labels}) "
            "— 블로그 기본 라벨만 사용합니다.",
            file=sys.stderr,
        )
    labels = list(dict.fromkeys(blog["labels"] + picked_categories))

    run_id = os.environ.get("GITHUB_RUN_ID") or datetime.now().strftime("%Y%m%d%H%M%S")

    image_query = (result.get("image_query") or "").strip()
    if not image_query:
        print(
            f"경고: 모델이 image_query를 생성하지 않아 키워드('{keyword}')를 이미지 검색어로 대신 사용합니다.",
            file=sys.stderr,
        )
        image_query = keyword

    final = {
        "blog_id": blog["id"],
        "blog_url": blog["url"],
        "keyword": keyword,
        "title": result["title"],
        "content_html": result["content_html"],
        "labels": labels,
        "search_description": result.get("search_description", ""),
        "image_query": image_query,
    }

    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    out_path = os.path.join(WORKSPACE_DIR, f"{run_id}_final.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print(f"저장 완료: {out_path}")
    print(f"제목: {final['title']}")
    print(f"이미지 검색어: {final['image_query']}")
    print(f"본문 가시 글자수(대략): {visible_length(final['content_html'])}자", file=sys.stderr)


if __name__ == "__main__":
    main()
