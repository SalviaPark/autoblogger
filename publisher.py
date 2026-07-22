#!/usr/bin/env python3
import glob
import os
import random
import re
import sys
import time
import urllib.request
import urllib.error
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

try:
    PIXABAY_API_KEY = os.environ["PIXABAY_API_KEY"]
except KeyError:
    raise RuntimeError("PIXABAY_API_KEY 환경변수가 설정되지 않았습니다.") from None
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY", "")
BLOG_URL = os.environ.get("INSURANCE_BLOG_URL", "https://salvia-information.blogspot.com")
SCOPES = ["https://www.googleapis.com/auth/blogger"]
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "client_secrets.json"

# 최근에 실제 발행 글에 쓰인 Pixabay 이미지 id를 기억해두는 파일. 서로 다른(그러나 비슷한
# 주제의) image_query라도 Pixabay가 상위 관련도로 돌려주는 스톡사진 풀 자체가 좁아 겹치는
# 경우가 실제로 확인됐다(예: "stock market chart growth gold coins trading app"과
# "stock market portfolio growth chart"라는 서로 다른 검색어로 발행된 두 글에서, 3장 중
# 2장이 SHA256까지 완전히 동일한 사진으로 나옴 — imgBB URL만 다를 뿐 원본이 같았다).
# fetch_images()가 후보 풀을 고를 때 이 목록에 있는 id는 제외해 최근 재사용을 줄인다.
RECENT_IMAGES_FILE = "_knowledge/recent_pixabay_ids.json"
RECENT_IMAGES_MAX = 150  # 대략 최근 50개 글(글당 3장) 분량만 기억 — 너무 오래 쌓이면
# 특정 니치(예: 재테크 영문 스톡사진)의 전체 후보가 고갈돼 이미지 품질/관련도가 떨어질 수 있다.


def _load_recent_image_ids():
    if not os.path.exists(RECENT_IMAGES_FILE):
        return []
    try:
        with open(RECENT_IMAGES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []


def _save_recent_image_ids(ids):
    os.makedirs("_knowledge", exist_ok=True)
    capped = ids[-RECENT_IMAGES_MAX:]
    with open(RECENT_IMAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(capped, f, ensure_ascii=False)

# 콘텐츠는 더 이상 여기서 생성하지 않는다 — insurance-blog-pipeline 스킬(헤드리스 Claude Code)이
# _knowledge/topics/ 지식베이스를 근거로 작성한다. 아래 리스트는 그 지식베이스가 커버해야 할
# 주제 체크리스트로 blog-knowledge-refresh 스킬이 참고한다.
TOPICS_KO = [
    # 건강 관리 (메인)
    ("당뇨관리", "당뇨 초기 증상 놓치면 안 되는 이유 - 내가 진단받기까지의 과정"),
    ("당뇨관리", "당뇨 환자가 매일 먹어도 되는 음식 vs 절대 피해야 할 음식"),
    ("고혈압", "고혈압 약 평생 먹어야 할까? 의사한테 직접 물어봤습니다"),
    ("고혈압", "고혈압 낮추는 생활 습관 - 약 없이 혈압 떨어진 내 경험"),
    ("면역력", "면역력 높이는 법 - 1년에 감기 한 번도 안 걸리는 사람들의 공통점"),
    ("면역력", "면역력 떨어졌을 때 나타나는 신호 5가지 - 이거 해당되면 조심해야 해"),
    ("수면", "잠을 자도 피곤한 이유 - 수면의 질 높이는 방법 7가지"),
    ("수면", "불면증 해결한 방법 - 수면제 없이 3주 만에 고친 방법"),
    ("다이어트", "요요 없이 10kg 뺀 방법 - 극단적 식단 없이 6개월 걸렸다"),
    ("다이어트", "뱃살 빠지는 음식 vs 뱃살 찌는 음식 - 영양사한테 물어본 결과"),
    ("건강검진", "건강검진 결과 해석하는 법 - 수치가 뭘 의미하는지 몰랐다"),
    ("건강검진", "국가건강검진 무료로 받는 방법 - 대상인지 확인하는 법"),
    ("영양제", "영양제 먹는 순서가 중요한 이유 - 같이 먹으면 안 되는 조합"),
    ("영양제", "비타민D 부족 증상 - 이게 다 결핍 때문이었을 줄이야"),
    ("장건강", "장 건강이 면역력과 연결되는 이유 - 프로바이오틱스 효과 직접 실험"),
    ("갱년기", "갱년기 증상 완화하는 방법 - 호르몬 치료 말고 이렇게 해봤어요"),
    ("관절건강", "무릎 통증 원인과 집에서 할 수 있는 관리법"),
    ("눈건강", "스마트폰 많이 쓰는 사람 눈 건강 지키는 법 - 안구건조증 해결"),
    ("간건강", "간 수치 높을 때 나타나는 증상과 간 건강 회복하는 방법"),
    ("갑상선", "갑상선 기능 저하증 초기 증상 - 피곤한 게 다 이거 때문이었다"),
    ("두통", "만성 두통 원인 찾는 법 - 진통제 달고 살다가 드디어 해결됐다"),
    ("피부건강", "아토피·건선 관리법 - 피부과 다니면서 배운 것들 총정리"),
    ("정신건강", "번아웃 증상과 회복 방법 - 직접 겪어보고 나서 알게 된 것들"),
    ("정신건강", "불안장애 극복 방법 - 상담 받기 전에 혼자 해본 것들"),
    # 의료비·보험 (서브)
    ("병원비절약", "병원 가기 전에 알아야 할 의료비 절약 꿀팁 7가지"),
    ("실손보험청구", "병원 다녀왔는데 실손 청구 안 했다면? 지금 당장 해야 하는 이유"),
    ("건강보험환급", "건강보험 환급금 신청 안 하면 그냥 사라져요 - 신청 방법 정리"),
    ("본인부담상한제", "병원비 100만원 넘으면 돌려받는 제도 - 신청 안 한 분들 보세요"),
    ("의료비세액공제", "연말정산 의료비 세액공제로 얼마나 돌려받을 수 있을까?"),
    ("비급여청구", "비급여 항목도 실손보험으로 청구된다? 모르면 손해인 것들"),
    ("암보험", "암보험 가입 전 반드시 확인해야 할 것들 - 후회 없는 선택 가이드"),
    ("건강보험피부양자", "건강보험 피부양자 조건과 탈락 기준 - 2026년 기준 완벽 정리"),
]

def _upload_to_imgbb(img_bytes):
    """Pixabay에서 받은 이미지를 imgBB에 재호스팅한다. 실패하면 None을 반환하고
    호출자(fetch_images)가 Pixabay 원본 URL로 폴백하는데, Pixabay의 /get/ 동적
    URL은 영구 링크가 아니라 나중에 깨질 수 있다(실제로 발행된 글에서 확인됨).
    그래서 실패 원인을 반드시 stderr로 남겨 "조용한 폴백"이 되지 않게 한다."""
    if not IMGBB_API_KEY:
        print(
            "  [imgBB] IMGBB_API_KEY 환경변수가 설정되지 않아 업로드를 건너뜁니다"
            " — Pixabay 원본 URL로 폴백합니다(비영구 링크일 수 있음).",
            file=sys.stderr,
        )
        return None
    import base64, urllib.parse
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    data = urllib.parse.urlencode({"image": b64}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}",
        data=data,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            result = json.loads(res.read())
        link = result.get("data", {}).get("url", "")
        if link:
            return link
        print(
            f"  [imgBB] 업로드 응답에 URL이 없습니다(API 오류 가능) — Pixabay 원본으로"
            f" 폴백합니다. 응답: {result}",
            file=sys.stderr,
        )
        return None
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        print(
            f"  [imgBB] 업로드 실패(HTTP {e.code}) — Pixabay 원본으로 폴백합니다."
            f" 응답 본문: {body}",
            file=sys.stderr,
        )
        return None
    except Exception as e:
        print(
            f"  [imgBB] 업로드 실패({type(e).__name__}: {e}) — Pixabay 원본으로 폴백합니다.",
            file=sys.stderr,
        )
        return None


PIXABAY_QUERY_MAX_LEN = 100  # Pixabay API 공식 제한: q 파라미터는 100자를 넘을 수 없다.


def _urlopen_with_retry(request, timeout=10, retries=2, backoff=1.5):
    """일시적 오류(연결 재설정, 타임아웃, 429/5xx)에 최소한으로 재시도한다.

    Pixabay는 API 키 단위로 60초당 100회 요청 제한이 있고, 여러 발행 작업이 같은
    키를 동시에 쓰면(예: 5개 블로그 연속 발행 + 로컬 테스트가 겹치는 경우) 한도에
    걸려 커넥션이 리셋되거나 429가 날 수 있다. 400(잘못된 요청)처럼 재시도해도
    똑같이 실패할 오류는 즉시 올리고, 그 외에는 backoff초 간격으로 최대 retries회
    다시 시도한다."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code == 400:
                raise
            last_err = e
        except Exception as e:
            last_err = e
        if attempt < retries:
            time.sleep(backoff * (attempt + 1))
    raise last_err


def fetch_images(query, count=3, pool_size=8):
    """query(영문 이미지 검색어)로 Pixabay를 검색해 이미지를 count장 가져온다.

    Pixabay API는 관련도/인기 순으로 정렬된 결과를 돌려준다. 이전에는 상위 15개를
    완전 무작위(random.shuffle)로 섞어 관련도를 무시했는데, 이제는 상위 pool_size개
    (기본 8개, 관련도가 높은 구간)만 후보로 남기고 그 안에서만 무작위로 골라 —
    관련도는 확보하면서도 발행 때마다 똑같은 사진이 반복되지 않도록 약간의 변주를 준다.
    """
    if len(query) > PIXABAY_QUERY_MAX_LEN:
        print(
            f"  [경고] image_query가 {len(query)}자로 Pixabay 제한({PIXABAY_QUERY_MAX_LEN}자)을"
            f" 넘어 잘라냅니다(원본 모델 출력이 비정상적으로 길었을 수 있음): {query!r}",
            file=sys.stderr,
        )
        query = query[:PIXABAY_QUERY_MAX_LEN]

    encoded_query = urllib.request.quote(query)
    api_url = (
        f"https://pixabay.com/api/?key={PIXABAY_API_KEY}"
        f"&q={encoded_query}&image_type=photo&orientation=horizontal"
        f"&per_page=15&safesearch=true&lang=en"
    )
    try:
        with _urlopen_with_retry(api_url, timeout=10) as res:
            data = json.loads(res.read())
        hits = data.get("hits", [])

        # 최근 발행 글에 이미 쓴 이미지(id 기준)는 후보에서 우선 제외한다. 비슷한
        # 주제의 image_query끼리는 Pixabay 상위 관련도 결과가 겹치는 경우가 실제로
        # 있어(서로 다른 검색어인데도 같은 사진이 재등장), 그대로 두면 pool_size가
        # 꽉 차 있어도 최근 글과 같은 사진이 뽑힐 수 있다. 다만 완전히 걸러내면
        # 후보가 너무 적어질 수 있으니, 신선한 후보가 count장 이상 확보될 때만
        # 제외 목록을 적용하고 부족하면 재사용도 허용한다(품질 저하보다 이미지가
        # 아예 없는 게 더 나쁘다).
        recent_ids = set(_load_recent_image_ids())
        fresh_hits = [h for h in hits if str(h.get("id", "")) not in recent_ids]
        candidates = fresh_hits if len(fresh_hits) >= count else hits

        pool = candidates[:pool_size]
        random.shuffle(pool)
        result = []
        used_ids = []
        for h in pool:
            if len(result) >= count:
                break
            pixabay_url = h["webformatURL"]
            try:
                img_req = urllib.request.Request(
                    pixabay_url,
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://pixabay.com/"},
                )
                with _urlopen_with_retry(img_req, timeout=10) as img_res:
                    img_bytes = img_res.read()
                imgbb_url = _upload_to_imgbb(img_bytes)
                if imgbb_url:
                    result.append(imgbb_url)
                else:
                    print(
                        f"  [경고] imgBB 재호스팅 실패로 Pixabay 원본 URL을 그대로 씁니다"
                        f"(비영구 링크일 수 있어 나중에 깨질 위험 있음): {pixabay_url}",
                        file=sys.stderr,
                    )
                    result.append(pixabay_url)
                if h.get("id") is not None:
                    used_ids.append(str(h["id"]))
            except Exception as e:
                print(f"  이미지 처리 실패: {e}", file=sys.stderr)
                continue
        if used_ids:
            _save_recent_image_ids(_load_recent_image_ids() + used_ids)
        print(
            f"  이미지 수집: {len(result)}장 (검색어: {query}, 후보 풀: {len(pool)}개, "
            f"최근 재사용 제외 후 신선한 후보: {len(fresh_hits)}개)"
        )
        return result
    except Exception as e:
        print(f"  Pixabay 검색 실패: {e}", file=sys.stderr)
        return []


def insert_images(content, images, keyword=None):
    """content의 각 <h2> 섹션 사이에 이미지를 순서대로 끼워 넣는다.

    alt 텍스트는 예전엔 "1번 이미지"처럼 순번만 담아 SEO/접근성에 아무 정보도
    주지 못했다. 이제 글의 핵심 키워드(keyword)를 기반으로 alt를 채워, 이미지
    검색·스크린리더 양쪽에 실제 주제 정보가 전달되게 한다. keyword가 없으면
    (호출부가 안 넘긴 예외 상황) 순번만 있는 예전 문구로 안전하게 폴백한다."""
    if not images:
        return content
    alt_base = f"{keyword} 관련 이미지" if keyword else "관련 이미지"
    parts = content.split("</h2>")
    result = []
    img_idx = 0
    for i, part in enumerate(parts):
        result.append(part)
        if i < len(parts) - 1:
            result.append("</h2>")
            if img_idx < len(images):
                result.append(
                    f'<p><img src="{images[img_idx]}" '
                    f'style="max-width:100%;height:auto;border-radius:8px;margin:12px 0;" '
                    f'loading="lazy" alt="{alt_base} {img_idx+1}"/></p>'
                )
                img_idx += 1
    return "".join(result)


_H2_TAG_RE = re.compile(r"<h2(\s[^>]*)?>(.*?)</h2>", re.DOTALL)


def insert_toc(content):
    """content(발행 직전 본문 HTML)의 <h2> 소제목들을 모아 본문 맨 앞(첫 문단 직후)에
    목차(TOC)를 자동 삽입한다.

    Gemini가 생성한 원본 <h2>에는 id 속성이 없어 목차 링크가 갈 곳이 없으므로, 여기서
    각 <h2>에 id="toc-N" 앵커를 새로 부여하고(기존 id가 있어도 통일해서 덮어씀) 목차
    링크가 정확히 그 id를 가리키게 한다. <h2>가 하나도 없으면(비정상 입력) 원본을
    그대로 반환한다.

    5개 블로그가 동일 템플릿으로 찍히는 문제(scaled content abuse 리스크) 완화 차원에서
    도입된 구조 요소 중 하나 — 목차 자체는 독자 편의 기능이라 매 글마다 항목 개수/텍스트가
    달라져 다양성에도 자연스럽게 기여한다."""
    matches = list(_H2_TAG_RE.finditer(content))
    if not matches:
        return content

    toc_items = []

    def _assign_id(m):
        idx = len(toc_items) + 1
        attrs = m.group(1) or ""
        # 원본에 id가 있어도 목차 매칭을 항상 보장하기 위해 우리가 부여하는 id로 통일한다.
        attrs = re.sub(r'\sid="[^"]*"', "", attrs)
        heading_html = m.group(2)
        heading_text = re.sub(r"<[^>]+>", "", heading_html).strip()
        anchor_id = f"toc-{idx}"
        toc_items.append((anchor_id, heading_text))
        return f'<h2{attrs} id="{anchor_id}">{heading_html}</h2>'

    new_content = _H2_TAG_RE.sub(_assign_id, content)

    if not toc_items:
        return content

    toc_links = "".join(
        f'<li><a href="#{anchor_id}">{text}</a></li>' for anchor_id, text in toc_items
    )
    toc_html = f'<div class="toc"><b>목차</b><ul>{toc_links}</ul></div>'

    # 본문 맨 앞 첫 문단(</p>) 뒤에 삽입해 도입부 직후 자연스러운 위치에 오게 한다.
    # 첫 </p>를 못 찾으면(비정상 구조, 예: 본문이 <h2>로 바로 시작) 본문 맨 앞에 붙인다.
    first_p_end = new_content.find("</p>")
    if first_p_end == -1:
        return toc_html + new_content
    insert_at = first_p_end + len("</p>")
    return new_content[:insert_at] + toc_html + new_content[insert_at:]


def get_blogger_service():
    creds = None

    token_json = os.environ.get("INSURANCE_BLOGGER_TOKEN_JSON")
    if token_json:
        with open(TOKEN_FILE, "w") as f:
            f.write(token_json)

    client_secrets_json = os.environ.get("BLOGGER_CLIENT_SECRETS_JSON")
    if client_secrets_json:
        with open(CREDENTIALS_FILE, "w") as f:
            f.write(client_secrets_json)

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # run_local_server()는 브라우저 리다이렉트 콜백을 기다리며 타임아웃이
            # 없다. GitHub Actions(CI)에는 브라우저가 없어 콜백이 영원히 안 와
            # 무한 대기에 빠진다(2026-07-14 blog5 발행이 약 2시간 hang된 사고
            # 원인). CI에서는 토큰이 없거나 갱신 불가능한 시점에 즉시 명확한
            # 에러로 실패시켜 무한 대기 대신 몇 분 안에 문제가 드러나게 한다.
            # 로컬 디버깅 환경(GITHUB_ACTIONS 미설정)에서는 최초 인증에
            # run_local_server()가 정상적으로 필요하므로 그대로 허용한다.
            if os.environ.get("GITHUB_ACTIONS") == "true":
                raise RuntimeError(
                    "Blogger 인증 토큰이 만료됐거나 없습니다. "
                    "INSURANCE_BLOGGER_TOKEN_JSON 시크릿을 갱신하세요 — "
                    "CI 환경에서는 브라우저 인증이 불가능합니다."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("blogger", "v3", credentials=creds)


def get_blog_id(service, url=None):
    blog = service.blogs().getByUrl(url=url or BLOG_URL).execute()
    return blog["id"]


def load_final_post(run_id=None):
    """insurance-blog-pipeline 스킬(헤드리스 Claude Code)이 만든 승인 완료 글을 읽는다.
    run_id가 지정되면 해당 실행분만, 없으면 _workspace/의 가장 최근 *_final.json을 쓴다.
    파일이 없으면 이번 실행은 발행할 게 없다는 뜻이다(품질 기준 미달 또는 파이프라인 미실행)."""
    if run_id:
        path = f"_workspace/{run_id}_final.json"
        if not os.path.exists(path):
            return None
    else:
        candidates = sorted(glob.glob("_workspace/*_final.json"))
        if not candidates:
            return None
        path = candidates[-1]

    with open(path, encoding="utf-8") as f:
        return json.load(f)


def append_published_log(blog_id, keyword, title, url, labels=None):
    from datetime import datetime
    os.makedirs("_knowledge", exist_ok=True)
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "blog_id": blog_id,
        "keyword": keyword,
        "title": title,
        "url": url,
        "labels": labels or [],
    }
    with open("_knowledge/published_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


PUBLISHED_LOG_FILE = "_knowledge/published_log.jsonl"


def _load_published_log():
    """published_log.jsonl을 읽어 항목 리스트를 돌려준다. 라벨 도입 이전에 기록된
    옛날 항목은 "labels" 키 자체가 없을 수 있으므로, 여기서 항상 리스트로
    보정해 이후 로직(pick_related_posts)이 KeyError 없이 안전하게 다룰 수 있게 한다."""
    if not os.path.exists(PUBLISHED_LOG_FILE):
        return []
    entries = []
    with open(PUBLISHED_LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry["labels"] = entry.get("labels") or []
            entries.append(entry)
    return entries


def pick_related_posts(blog_id, current_labels, exclude_url=None, count=3):
    """같은 블로그(blog_id)의 과거 발행 글 중 "함께 보면 좋은 글" 섹션에 쓸
    후보를 최대 count개 고른다.

    우선순위:
      1) current_labels와 겹치는 라벨이 많은 순
      2) 겹치는 라벨 수가 같으면 최신(date) 순
    라벨이 아예 기록되지 않은 옛날 글(labels가 빈 리스트)은 겹치는 라벨이 0개인
    후보로 취급되어 자동으로 우선순위 뒤로 밀리되, 관련 라벨 글이 count개 미만이면
    최신순으로 채워 빈 자리를 메운다. 과거 발행 글 자체가 없으면 빈 리스트를
    돌려주고, 이 경우 호출자가 관련 글 섹션을 생략해야 한다."""
    current_label_set = set(current_labels or [])

    entries = [
        e for e in _load_published_log()
        if e.get("blog_id") == blog_id and e.get("url") != exclude_url
    ]
    if not entries:
        return []

    def overlap_count(entry):
        return len(current_label_set & set(entry.get("labels") or []))

    # date(YYYY-MM-DD) 문자열은 사전식 정렬이 곧 시간순 정렬이라 최신순 정렬에
    # 그대로 쓸 수 있다. 같은 날짜 안에서는 로그에 적힌 순서(발행 순서)를 유지하기
    # 위해 원래 인덱스를 보조 키로 사용한다.
    indexed = list(enumerate(entries))
    indexed.sort(key=lambda pair: (overlap_count(pair[1]), pair[1].get("date", ""), pair[0]), reverse=True)
    ranked = [e for _, e in indexed]

    picked = ranked[:count]
    return [{"title": e.get("title", ""), "url": e.get("url", "")} for e in picked if e.get("url")]


# generate_post.py의 build_prompt()가 테마별로 강제하는 면책 문구 시작 부분(오타 없이
# 그대로 복사). 건강(theme=="건강")과 재테크(theme=="재테크")만 고정 문구가 있고,
# IT/여행/생활정보 등 "기타" 테마는 고정 면책 문구 자체가 없어 매칭되는 마커가 없다 —
# 그 경우 관련 글 섹션은 그냥 본문 맨 끝에 붙는다(의도된 동작).
DISCLAIMER_MARKERS = [
    "<p>본 글은 일반적인",              # 건강: "본 글은 일반적인 건강 정보로 진단·치료를 대신하지 않으며..."
    "<p>본 글은 정보 제공을 목적으로",  # 재테크: "본 글은 정보 제공을 목적으로 하며 투자 권유가 아니고..."
]


def insert_related_posts(content, related_posts):
    """content(최종 본문 HTML) 끝에 과거 글로 가는 "함께 보면 좋은 글" 섹션을 넣는다.

    의료/투자 면책 문구가 본문 마지막 문장이어야 하므로, DISCLAIMER_MARKERS 중 실제로
    본문에 있는 마커를 찾아 그 문단 바로 앞에 삽입한다. 어떤 마커와도 매칭되지 않으면
    (고정 면책 문구가 없는 테마이거나 문구가 바뀐 경우) 본문 맨 끝에 덧붙인다."""
    if not related_posts:
        return content

    items = "".join(
        f'<li><a href="{p["url"]}">{p["title"]}</a></li>' for p in related_posts
    )
    section = f"<h2>함께 보면 좋은 글</h2><ul>{items}</ul>"

    positions = [content.rfind(marker) for marker in DISCLAIMER_MARKERS]
    positions = [p for p in positions if p != -1]
    if not positions:
        return content + section
    idx = min(positions)
    return content[:idx] + section + content[idx:]


def post_to_blogger(service, blog_id, title, content, labels=None, search_description=None):
    body = {"kind": "blogger#post", "title": title, "content": content}
    if labels:
        body["labels"] = labels
    # 주의: Blogger API v3 Posts 리소스 스키마에는 "searchDescription" 필드가 없다
    # (공식 discovery document 기준 확인: titleLink, selfLink, location, readerComments,
    # title, replies, status, trashed, blog, content, images, updated, url, id, kind,
    # published, customMetaData[deprecated], author, labels, etag 뿐).
    # 즉 아래 줄은 API가 알 수 없는 키라서 에러 없이 조용히 무시되고, 검색 설명은
    # 절대 저장되지 않는다(실제 발행 글 GET 결과로 확인함). insert/patch 어느 쪽으로도
    # 공식적으로 지원되는 방법이 없으므로 재작성/재발행으로는 해결되지 않는다 —
    # 이 필드에 의존하지 말 것. (2026-07-12 조사, 과장1)
    if search_description:
        body["searchDescription"] = search_description
    result = service.posts().insert(blogId=blog_id, body=body).execute()
    return result["url"]


def main():
    lang = sys.argv[1] if len(sys.argv) > 1 else "ko"
    run_id = os.environ.get("GITHUB_RUN_ID")

    post = load_final_post(run_id)
    if post is None:
        print("발행 대기 중인 승인된 글이 없습니다 (품질 기준 미달 또는 파이프라인 미실행). 이번 실행은 건너뜁니다.")
        return

    keyword = post["keyword"]
    title = post["title"]
    content = post["content_html"]
    labels = post.get("labels", [])
    search_description = post.get("search_description") or None

    # 발행 대상 블로그 URL: final.json의 blog_url → 기본값
    target_url = post.get("blog_url") or BLOG_URL

    print(f"[{lang.upper()}] 발행 대상: {title} (키워드: {keyword}) → {target_url}")

    # 예전에는 본문을 <div style="...color:#222;">로 감싸 폰트/글자색을 강제 고정했다.
    # 지금 테마(themes/*.xml)는 body와 .article p에서 이미 font-family:var(--font)
    # (Pretendard 등)와 color:var(--ink)를 지정하고, --ink는 라이트/다크 모드에 따라
    # 자동 전환된다. 여기서 인라인 color:#222를 고정하면 그 전환을 덮어써 다크모드에서
    # 어두운 배경에 어두운 글자가 겹쳐 안 보이는 문제가 생긴다. 테마가 이미 폰트/색상을
    # 전부 커버하므로 래퍼 div 자체가 불필요해 제거한다 — 본문 글자색이 테마의
    # 라이트/다크 전환을 그대로 따라가게 한다.

    image_query = (post.get("image_query") or "").strip()
    if not image_query:
        print(
            f"  경고: final.json에 image_query가 없어 키워드('{keyword}')를 이미지 검색어로 대신 사용합니다."
        )
        image_query = keyword
    elif len(image_query) > PIXABAY_QUERY_MAX_LEN * 1.5:
        # Gemini가 가끔 image_query에 정상적인 검색어 대신 안내문/반복 잡음이 섞인
        # 수백~수천 자짜리 텍스트를 내보내는 경우가 있다(모델 결함). 이런 값은
        # Pixabay 제한(100자)에 맞춰 앞부분만 잘라내도 여전히 문장 중간이 잘린
        # 의미 없는 조각이라 검색 결과가 0건으로 나온다 — 애초에 정상적인 이미지
        # 검색어(영문 몇 단어)라면 이 정도로 길 수 없으므로, 자르지 않고 통째로
        # 버리고 키워드로 대체한다.
        print(
            f"  경고: image_query가 {len(image_query)}자로 비정상적으로 길어(모델 결함 의심) "
            f"버리고 키워드('{keyword}')를 이미지 검색어로 대신 사용합니다."
        )
        image_query = keyword

    content = insert_toc(content)
    print("목차(TOC) 삽입 완료")

    print("Pixabay에서 이미지 검색 중...")
    images = fetch_images(image_query, count=3)
    if not images and image_query != keyword:
        print(f"  경고: '{image_query}' 검색 결과 0건 — 키워드('{keyword}')로 재검색합니다.")
        images = fetch_images(keyword, count=3)
    content = insert_images(content, images, keyword=keyword)
    print(f"이미지 {len(images)}장 삽입 완료")

    related_posts = pick_related_posts(post["blog_id"], labels, exclude_url=None, count=3)
    if related_posts:
        content = insert_related_posts(content, related_posts)
        print(f"관련 글 {len(related_posts)}개 삽입 완료")
    else:
        print("관련 글 후보 없음(해당 블로그 첫 발행 등) — 관련 글 섹션 생략")

    print("Blogger 인증 중...")
    service = get_blogger_service()
    blog_id = get_blog_id(service, target_url)

    print("글 발행 중...")
    url = post_to_blogger(service, blog_id, title, content, labels, search_description)
    print(f"발행 완료: {url}")

    append_published_log(post["blog_id"], keyword, title, url, labels)


if __name__ == "__main__":
    main()
