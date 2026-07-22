#!/usr/bin/env python3
import os
import random
import sys
import urllib.request
import json
from google import genai
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

try:
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
except KeyError:
    raise RuntimeError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.") from None
try:
    PIXABAY_API_KEY = os.environ["PIXABAY_API_KEY"]
except KeyError:
    raise RuntimeError("PIXABAY_API_KEY 환경변수가 설정되지 않았습니다.") from None
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY", "")
BLOG_URL = "https://salviaproject.blogspot.com"
SCOPES = ["https://www.googleapis.com/auth/blogger"]
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "client_secrets.json"

TOPICS_KO = [
    # 기존 주제
    ("배경제거", "포토샵 없이 배경 지우는 법, 나도 해봤는데 진짜 쉽더라"),
    ("누끼따기", "쇼핑몰 시작하면서 누끼따기 배운 썰 - 돈 아끼는 법"),
    ("증명사진", "집에서 이력서 증명사진 만들기 - 사진관 3만원 아끼는 법"),
    ("유튜브썸네일", "유튜브 썸네일 클릭률 올리는 법 - 배경제거가 핵심이었다"),
    ("상품사진", "스마트스토어 상품사진 흰배경으로 바꾸는 법 (무료)"),
    ("이미지편집", "이미지 용량 줄이는 법 - 블로그 로딩 느릴 때 이렇게 해봐"),
    ("투명PNG", "투명 배경 PNG 만드는 법 - 디자인 초보도 5분이면 OK"),
    ("누끼따기", "인스타 피드 감성사진 만드는 법 - 배경제거로 완성하는 합성"),
    ("이미지리사이즈", "카카오톡 프로필 사진 예쁘게 자르는 법 + 용량 줄이기"),
    ("배경제거", "AI 배경제거 써봤는데 진짜 포토샵 필요 없겠더라"),
    ("상품사진", "쿠팡 입점하면서 상품사진 직접 찍고 편집한 후기"),
    ("증명사진", "공무원 시험 원서 증명사진 규격 맞추는 법 완벽 정리"),
    # 배경제거·누끼 확장
    ("배경제거", "배경제거 AI 비교해봤는데 무료인데 이 정도면 충분하더라"),
    ("누끼따기", "의류 쇼핑몰 누끼따기 직접 해보니 이런 점이 불편했다"),
    ("투명배경", "PPT에 투명 배경 이미지 넣는 법 - 발표 자료 퀄리티 올리기"),
    ("배경제거", "여권사진 집에서 만들기 가능할까? 직접 해본 솔직 후기"),
    ("누끼따기", "음식 사진 배경제거 해봤더니 메뉴판 퀄리티가 달라졌다"),
    ("이미지편집", "무료 이미지 편집 사이트 비교 - 결국 이거 하나로 정착했다"),
    ("배경제거", "블로그 썸네일 배경제거로 클릭률 높이는 법"),
    ("PNG변환", "JPG를 PNG로 바꾸는 법 - 투명 배경 만들 때 꼭 필요한 이유"),
    # 배경색 채우기 관련
    ("배경색채우기", "배경제거 후 흰배경 만드는 법 - 클릭 한번으로 끝났다"),
    ("증명사진배경", "증명사진 흰배경·파란배경 집에서 바꾸는 법 (미리보기까지 됨)"),
    ("상품사진흰배경", "쇼핑몰 흰배경 상품사진 만드는 법 - 배경제거+색채우기 콤보"),
    # 타겟별 주제
    ("유튜버", "유튜브 채널 아트 만드는 법 - 배경제거로 프로처럼"),
    ("셀러", "에이블리·지그재그 상품사진 규격 맞추는 법 총정리"),
    ("직장인", "회사 프로필 사진 배경 바꾸는 법 - 링크드인·사원증용"),
    ("학생", "대학 원서 증명사진 집에서 만든 후기 - 규격·배경색 주의사항"),
    ("인플루언서", "인스타 릴스 썸네일 만드는 법 - 팔로워 늘리는 디자인 팁"),
    ("소상공인", "카페 메뉴판 사진 직접 찍고 편집한 법 - 외주 안 줘도 돼"),
    ("유튜버", "유튜브 쇼츠 썸네일 만드는 법 - 클릭되는 디자인 공식"),
    ("블로거", "네이버 블로그 썸네일 만드는 법 - 조회수 올리는 크기와 디자인"),
    ("셀러", "오픈마켓 상품 대표이미지 규격 완벽 정리 - 쿠팡·11번가·G마켓"),
    ("직장인", "PPT 발표자료 이미지 편집 꿀팁 - 포토샵 없이 5분 만에"),
]

TOPICS_EN = [
    # 기존 주제
    ("background removal", "I tried 5 free background removers - here's what actually worked"),
    ("product photo", "How I made pro-looking product photos without Photoshop (for free)"),
    ("YouTube thumbnail", "Why removing backgrounds boosted my YouTube CTR by 40%"),
    ("transparent PNG", "How to make a transparent PNG in under 5 minutes - no software needed"),
    ("image resize", "My images were slowing down my blog - here's how I fixed it for free"),
    ("ID photo", "How to change your ID photo background at home without a studio"),
    ("background removal", "Stop paying for Photoshop - these free tools do the same thing"),
    ("thumbnail design", "How to make eye-catching thumbnails with free background removal"),
    ("online store", "How I prepped 50 product photos in one afternoon (without Photoshop)"),
    ("image editing", "Free image editing tools that actually work in 2026"),
    # 배경제거·편집 확장
    ("background removal", "Honest review: AI background removers I actually use in 2026"),
    ("transparent background", "How to add a transparent background to any image for free"),
    ("image editing", "The only free image editor I use now - and why I cancelled Photoshop"),
    ("background removal", "How to make passport photos at home (and what to watch out for)"),
    ("PNG conversion", "Why you need PNG instead of JPG for transparent backgrounds"),
    ("photo editing", "I edited 100 product photos in one day using only free tools"),
    ("background removal", "Before and after: how background removal changed my Etsy shop"),
    ("image resize", "Why your website loads slow and how to fix it with free image tools"),
    # 배경색 채우기 관련
    ("background color fill", "How to add a white background after removing it — one click, no Photoshop"),
    ("ID photo background", "Change ID photo background to white or blue in seconds — with live preview"),
    ("product photo white background", "White background product photos in 3 steps — remove + fill, done"),
    # 타겟별 주제
    ("YouTuber", "How I design YouTube thumbnails that actually get clicked (free tools only)"),
    ("online seller", "Amazon seller's guide to product photos without a studio or Photoshop"),
    ("student", "How to make a professional LinkedIn photo at home for free"),
    ("blogger", "Blog images that rank: size, format, and editing tips for 2026"),
    ("small business", "DIY product photography for small businesses - no budget needed"),
    ("Instagram", "How to make Instagram-worthy photos with free background removal"),
    ("freelancer", "Free design tools every freelancer should know in 2026"),
    ("Etsy seller", "How I scaled my Etsy shop with better product photos (zero cost)"),
    ("content creator", "Content creator toolkit: free image editing that saves hours"),
    ("teacher", "How to make clean presentation images without Photoshop"),
]

FORMATS_KO = [
    "개인 경험담 형식 (내가 직접 써봤더니~ 스타일, 반말 구어체)",
    "꿀팁 리스트 형식 (1. 2. 3. 번호 목록, 실용적인 팁 위주)",
    "Q&A 형식 (자주 묻는 질문 3~4개에 답하는 형식)",
    "비교 후기 형식 (유료 vs 무료, 전 vs 후 비교)",
    "초보자 가이드 형식 (단계별 설명, 쉬운 말로)",
]

FORMATS_EN = [
    "personal experience/review style (casual, first person, honest pros and cons)",
    "practical tips listicle (numbered list, actionable advice)",
    "beginner's guide style (step-by-step, simple language)",
    "comparison style (free vs paid, before vs after)",
    "problem-solution style (start with a relatable problem, then solve it)",
]


KO_IMAGE_QUERY = {
    "배경제거": "background removal photo editing",
    "누끼따기": "product photo editing cutout",
    "증명사진": "portrait id photo studio",
    "유튜브썸네일": "youtube thumbnail design",
    "상품사진": "product photography white background",
    "이미지편집": "photo editing computer design",
    "투명PNG": "transparent background graphic design",
    "이미지리사이즈": "image resize photo editing",
    "배경색채우기": "color background design fill",
    "투명배경": "transparent background design",
    "PNG변환": "image format conversion design",
    "증명사진배경": "photo background color change",
    "상품사진흰배경": "product photo white background ecommerce",
    "유튜버": "youtube content creator studio",
    "셀러": "ecommerce seller online shop",
    "직장인": "office professional business",
    "학생": "student studying laptop",
    "인플루언서": "social media influencer smartphone",
    "소상공인": "small business owner shop",
    "블로거": "blogger writing laptop coffee",
}


def _upload_to_imgbb(img_bytes):
    if not IMGBB_API_KEY:
        print("  IMGBB_API_KEY 미설정, 업로드 건너뜀")
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
        print(f"  imgBB 응답 이상: {result}")
        return None
    except Exception as e:
        print(f"  imgBB 업로드 실패: {e}")
        return None


def fetch_images(keyword, lang="ko", count=3):
    if lang == "ko":
        query = KO_IMAGE_QUERY.get(keyword, f"{keyword} design")
    else:
        query = keyword
    query = urllib.request.quote(query)
    api_url = (
        f"https://pixabay.com/api/?key={PIXABAY_API_KEY}"
        f"&q={query}&image_type=photo&orientation=horizontal"
        f"&per_page=15&safesearch=true&lang=en"
    )
    try:
        with urllib.request.urlopen(api_url, timeout=10) as res:
            data = json.loads(res.read())
        hits = data.get("hits", [])
        random.shuffle(hits)
        result = []
        for h in hits:
            if len(result) >= count:
                break
            pixabay_url = h["webformatURL"]
            try:
                img_req = urllib.request.Request(
                    pixabay_url,
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://pixabay.com/"},
                )
                with urllib.request.urlopen(img_req, timeout=10) as img_res:
                    img_bytes = img_res.read()
                    content_type = img_res.headers.get("Content-Type", "image/jpeg").split(";")[0]
                imgbb_url = _upload_to_imgbb(img_bytes)
                result.append(imgbb_url if imgbb_url else pixabay_url)
            except Exception as e:
                print(f"  이미지 처리 실패: {e}")
                continue
        print(f"  이미지 수집: {len(result)}장 (키워드: {query})")
        return result
    except Exception as e:
        print(f"  Pixabay 검색 실패: {e}")
        return []


def insert_images(content, images):
    if not images:
        return content
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
                    f'loading="lazy" alt="{img_idx+1}번 이미지"/></p>'
                )
                img_idx += 1
    return "".join(result)


def get_blogger_service():
    creds = None

    # GitHub Actions 환경: 환경변수에서 토큰 읽기
    token_json = os.environ.get("BLOGGER_TOKEN_JSON")
    if token_json:
        with open(TOKEN_FILE, "w") as f:
            f.write(token_json)

    # 환경변수에서 client_secrets 읽기
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
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("blogger", "v3", credentials=creds)


def get_blog_id(service):
    blog = service.blogs().getByUrl(url=BLOG_URL).execute()
    return blog["id"]


def generate_posts(ko_keyword, ko_topic, ko_fmt, en_keyword, en_topic, en_fmt):
    client = genai.Client(api_key=GEMINI_API_KEY)

    ko_length = random.randint(1200, 1800)
    en_length = random.randint(900, 1500)

    prompt = f"""두 개의 블로그 글을 아래 지시에 따라 각각 작성해줘. 반드시 아래 응답 형식을 정확히 따를 것.

=== 글1: 한국어 ===
이미지 편집을 독학으로 배운 프리랜서 디자이너처럼 써줘.
포토샵 없이 무료 툴로 작업하는 경험을 친구한테 카카오톡으로 공유하는 느낌으로.

주제 키워드: {ko_keyword}
글 방향: {ko_topic}
글 형식: {ko_fmt}
분량: {ko_length}자 내외 (반드시 지킬 것)

❌ 절대 쓰지 말 것:
- "~에 대해 알아보겠습니다", "결론적으로", "이러한 이유로"
- 모든 문단이 균일하게 반복되는 구조
- "오늘은 ~에 대해 알아봤습니다" 식 마무리

✅ 이렇게 써:
- "솔직히 기대 안 했는데", "근데 이거 처음 써봤을 때 진짜 놀랐어" 같은 구어체
- 문장 길이 들쭉날쭉하게
- 구체적 수치·시간 (예: "3분 만에", "용량이 2.4MB에서 310KB로")
- 전문 지식 포함: 이미지 포맷(PNG/JPEG/WebP) 차이, DPI·해상도 개념, 색공간, 압축 원리 등 실용적인 기술 정보를 자연스럽게 녹여줘
- <a href="https://clipcut.org">ClipCut</a>을 실제로 써본 도구처럼 1~2번 자연스럽게 언급
  (ClipCut: 브라우저에서 무료 배경제거·이미지편집, 설치·회원가입 불필요, 배경 색 채우기 원클릭)

필수 구조:
1. 제목 바로 아래 핵심 답변 2~3문장 먼저 제시
2. h2 소제목 5개 이상 (독자 궁금증 유발하는 문장형으로)
3. 이모지 3~5개
4. 글 중간 FAQ 2~3개:
<div style="margin:28px 0 8px;">
<p style="margin-bottom:6px;"><strong>Q. 질문?</strong></p>
<p style="margin-bottom:24px;">답변</p>
</div>
5. 후킹 문구 3~4개:
<div style="background:#fff8e1;border-left:4px solid #ffb300;padding:14px 18px;margin:24px 0;border-radius:0 8px 8px 0;">
<strong>💡 글 맥락에 맞는 강조 문구</strong>
</div>
6. 모든 <p>에 style="margin-bottom:14px"
7. h2, p, ul, li, strong, div만 사용 (h1·이미지 태그 금지)

=== 글2: English ===
Write like a self-taught freelance designer who actually uses free browser tools daily — not an AI, not a generic tutorial.
Tone: like sharing a tip with a friend. Casual, direct, specific about what worked.

Keyword: {en_keyword}
Topic angle: {en_topic}
Format: {en_fmt}
Length: around {en_length} words (strictly follow this)

❌ Never do this:
- "In this article, we will explore..." / "It is important to note..."
- "In conclusion..." / "I hope you found this helpful!"
- Every section the exact same length

✅ Do this:
- Start with a real moment or problem ("My client needed a white background product shot in 10 minutes...")
- Mix short punchy sentences with longer ones
- Real specifics: "file dropped from 4MB to 280KB", "took maybe 90 seconds"
- Include actual technical knowledge: file formats (PNG vs JPEG vs WebP), compression, DPI, color modes — explained simply but accurately
- Mention <a href="https://clipcut.org">ClipCut</a> naturally, 1-2 times
  (ClipCut: free browser-based background removal & image editor, no signup, one-click background color fill)

Required structure:
1. Key answer in 2-3 sentences right after the intro
2. At least 5 h2 subheadings (questions or bold statements, not generic labels)
3. 2-3 FAQ items mid-post:
<div style="margin:28px 0 8px;">
<p style="margin-bottom:6px;"><strong>Q. question?</strong></p>
<p style="margin-bottom:24px;">answer</p>
</div>
4. 3-4 callout boxes:
<div style="background:#e8f4fd;border-left:4px solid #2563eb;padding:14px 18px;margin:24px 0;border-radius:0 8px 8px 0;">
<strong>💡 actual compelling point here</strong>
</div>
5. All <p> tags get style="margin-bottom:14px"
6. h2, p, ul, li, strong, div only (no h1, no img tags)

=== 응답 형식 (정확히 이 형식으로 출력) ===
KO_TITLE: [SEO 최적화 한국어 제목 — 주제 키워드를 제목 앞쪽에 배치, 25자 이내, "~하는 법"·"총정리"·"후기"·"이유"·"차이" 등 클릭 유도 표현 포함]
KO_CONTENT:
[한국어 HTML 본문]
===END_KO===
EN_TITLE: [SEO-optimized English title — keyword near the front, 55 chars max, include a hook word like "how to", "best", "guide", "free", or "without"]
EN_CONTENT:
[English HTML body]
===END_EN==="""

    import time, re
    models = ["gemini-2.5-flash", "gemini-2.0-flash"]
    response = None
    last_error = None
    for model in models:
        for attempt in range(3):
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                break
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait = 60 if "503" in str(e) or "UNAVAILABLE" in str(e) else 10
                    print(f"  [{model}] Gemini 오류 ({e.__class__.__name__}), {wait}초 후 재시도... ({attempt+1}/3)")
                    time.sleep(wait)
                else:
                    print(f"  [{model}] 3회 실패, 다음 모델로 전환")
        if response is not None:
            break
    if response is None:
        raise last_error

    text = re.sub(r"```(?:html)?", "", response.text).strip()

    ko_title_match = re.search(r'KO_TITLE:\s*(.+)', text, re.IGNORECASE)
    ko_title = ko_title_match.group(1).strip() if ko_title_match else ""

    ko_content_match = re.search(r'KO_CONTENT:\s*\n?(.*?)===END_KO===', text, re.DOTALL | re.IGNORECASE)
    ko_content = ko_content_match.group(1).strip() if ko_content_match else ""

    en_title_match = re.search(r'EN_TITLE:\s*(.+)', text, re.IGNORECASE)
    en_title = en_title_match.group(1).strip() if en_title_match else ""

    en_content_match = re.search(r'EN_CONTENT:\s*\n?(.*?)===END_EN===', text, re.DOTALL | re.IGNORECASE)
    en_content = en_content_match.group(1).strip() if en_content_match else ""

    print(f"  (KO content: {len(ko_content)}자, EN content: {len(en_content)}자)")

    ko_content += """
<hr style="margin:32px 0;border:none;border-top:1px solid #e0e0e0;">
<div style="background:#f0f7ff;border-radius:12px;padding:20px 24px;margin-top:16px;">
  <p style="margin:0 0 8px;font-weight:bold;font-size:1.05em;">✂️ 지금 바로 무료로 써보세요</p>
  <p style="margin:0 0 12px;color:#444;">배경제거·누끼따기·이미지 크기 조절을 설치 없이 브라우저에서 바로. 회원가입도 필요 없어요.</p>
  <a href="https://clipcut.org" style="display:inline-block;background:#2563eb;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:bold;">👉 ClipCut 무료로 사용하기</a>
</div>"""

    en_content += """
<hr style="margin:32px 0;border:none;border-top:1px solid #e0e0e0;">
<div style="background:#f0f7ff;border-radius:12px;padding:20px 24px;margin-top:16px;">
  <p style="margin:0 0 8px;font-weight:bold;font-size:1.05em;">✂️ Try it yourself — it's free</p>
  <p style="margin:0 0 12px;color:#444;">Background removal, image resizing, and more — right in your browser. No install, no signup.</p>
  <a href="https://clipcut.org" style="display:inline-block;background:#2563eb;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:bold;">👉 Try ClipCut for Free</a>
</div>"""

    return ko_title, ko_content, en_title, en_content


def post_to_blogger(service, blog_id, title, content):
    body = {"kind": "blogger#post", "title": title, "content": content}
    result = service.posts().insert(blogId=blog_id, body=body).execute()
    return result["url"]


def main():
    ko_keyword, ko_topic = random.choice(TOPICS_KO)
    ko_fmt = random.choice(FORMATS_KO)
    en_keyword, en_topic = random.choice(TOPICS_EN)
    en_fmt = random.choice(FORMATS_EN)

    print(f"[KO] 키워드: {ko_keyword} / {ko_topic}")
    print(f"[EN] keyword: {en_keyword} / {en_topic}")

    print("Gemini로 한/영 글 동시 생성 중...")
    ko_title, ko_content, en_title, en_content = generate_posts(
        ko_keyword, ko_topic, ko_fmt,
        en_keyword, en_topic, en_fmt,
    )
    print(f"[KO] 제목: {ko_title}")
    print(f"[EN] title: {en_title}")

    print("Pixabay에서 이미지 검색 중...")
    ko_images = fetch_images(ko_keyword, "ko", count=3)
    ko_content = insert_images(ko_content, ko_images)
    en_images = fetch_images(en_keyword, "en", count=3)
    en_content = insert_images(en_content, en_images)
    print(f"이미지 삽입 완료 (KO: {len(ko_images)}장, EN: {len(en_images)}장)")

    print("Blogger 인증 중...")
    service = get_blogger_service()
    blog_id = get_blog_id(service)

    print("[KO] 글 발행 중...")
    ko_url = post_to_blogger(service, blog_id, ko_title, ko_content)
    print(f"[KO] 발행 완료: {ko_url}")

    print("[EN] 글 발행 중...")
    en_url = post_to_blogger(service, blog_id, en_title, en_content)
    print(f"[EN] 발행 완료: {en_url}")


if __name__ == "__main__":
    main()
