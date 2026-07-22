#!/usr/bin/env python3
"""애드센스 승인 필수 페이지(개인정보처리방침·소개·연락처·면책조항)를
blogs.json의 각 블로그에 Blogger pages API로 자동 생성한다.

사용법:
  python3 create_pages.py health      # 특정 블로그
  python3 create_pages.py --all       # blogs.json 전체

운영자 정보(이름·이메일·시행일)는 site_config.json의 값을 치환해 넣는다(하드코딩 금지).
값이 플레이스홀더(<<...>>)이면 경고를 출력하되 생성은 진행한다.
이미 같은 제목의 페이지가 있으면 pages().list로 확인해 건너뛴다(재실행해도 중복 생성 안 함).

인증은 publisher.get_blogger_service()를 재활용한다(발행기와 동일 토큰/스코프).
"""
import json
import sys

# 발행 코어의 OAuth 인증만 재활용한다(인증·이미지·발행 로직은 건드리지 않음).
from publisher import get_blogger_service

BLOGS_FILE = "blogs.json"
SITE_CONFIG_FILE = "site_config.json"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def is_placeholder(value):
    return isinstance(value, str) and value.strip().startswith("<<")


def load_site_config():
    cfg = load_json(SITE_CONFIG_FILE)
    placeholders = [k for k, v in cfg.items() if is_placeholder(v)]
    if placeholders:
        print(
            "경고: site_config.json에 아직 채우지 않은 플레이스홀더가 있습니다 → "
            + ", ".join(placeholders)
            + "\n  (사장이 값을 채운 뒤 재실행하거나 페이지를 수정하세요. 지금은 그대로 진행합니다.)",
            file=sys.stderr,
        )
    return cfg


# ---------------------------------------------------------------------------
# 페이지 본문 템플릿 (조사 문서 _knowledge/adsense_approval_requirements.md 요건 반영)
# 운영자 정보는 모두 cfg 치환으로만 들어간다.
# ---------------------------------------------------------------------------

def privacy_policy_page(cfg, blog):
    """개인정보처리방침 — 구글 애드센스 필수 고지 문구(제3자 쿠키·구글/DoubleClick·opt-out) 포함."""
    brand = cfg.get("site_brand", "")
    email = cfg.get("contact_email", "")
    effective = cfg.get("privacy_effective_date", "")
    content = f"""
<h2>개인정보처리방침</h2>
<p><b>{brand}</b>(이하 "본 사이트")는 방문자의 개인정보를 중요하게 생각하며, 개인정보 보호법 등 관련 법령을 준수합니다. 본 방침은 본 사이트가 어떤 정보를 수집하고 어떻게 이용·보호하는지, 그리고 광고와 쿠키에 관한 사항을 안내합니다.</p>

<h3>1. 수집하는 정보와 이용 목적</h3>
<ul>
<li>본 사이트는 회원가입 절차가 없으며 이름·연락처 등 개인정보를 직접 수집하지 않습니다.</li>
<li>다만 방문 통계 분석 및 광고 게재를 위해 쿠키, 접속 로그(IP, 브라우저 정보), 방문 기록 등이 자동으로 수집·이용될 수 있습니다.</li>
<li>문의 시 제공하신 이메일 주소는 문의 응대 목적으로만 사용하며, 목적 달성 후 파기합니다.</li>
</ul>

<h3>2. 쿠키(Cookie)의 사용</h3>
<ul>
<li>쿠키는 웹사이트가 방문자의 브라우저에 저장하는 작은 텍스트 파일로, 맞춤 콘텐츠와 광고 제공, 이용 통계 분석에 사용됩니다.</li>
<li>방문자는 웹 브라우저 설정에서 쿠키 저장을 거부하거나 삭제할 수 있으며, 이 경우 일부 서비스 이용이 제한될 수 있습니다.</li>
</ul>

<h3>3. 제3자 광고 및 구글 애드센스 고지</h3>
<ul>
<li><b>제3자 공급업체(구글 포함)는 사용자가 본 웹사이트 또는 다른 웹사이트를 이전에 방문한 기록을 바탕으로 쿠키를 사용해 광고를 게재합니다.</b></li>
<li>구글의 광고 쿠키 사용으로 구글과 그 파트너는 사용자의 본 사이트 및/또는 인터넷상의 다른 사이트 방문 기록을 바탕으로 광고를 게재할 수 있습니다.</li>
<li>광고 목적의 제3자 쿠키는 <b>doubleclick.net</b> 또는 국가별 구글 도메인(예: google.com)과 연결될 수 있습니다.</li>
<li>사용자는 <b>구글 광고 설정(https://www.google.com/settings/ads)</b>에서 맞춤 광고를 해제할 수 있습니다.</li>
<li>제3자 공급업체의 쿠키를 통한 맞춤 광고는 <b>www.aboutads.info</b>(및 www.networkadvertising.org)에서 해제(opt-out)할 수 있습니다.</li>
<li>본 사이트는 구글 외 다른 제3자 광고 네트워크를 사용할 경우 해당 네트워크와 opt-out 경로를 별도로 안내합니다.</li>
</ul>

<h3>4. 개인정보의 보유 및 파기</h3>
<p>자동 수집되는 접속 로그·쿠키 정보는 관련 법령이 정한 기간 또는 수집 목적 달성 시까지 보유 후 파기합니다. 문의 이메일은 응대 완료 후 지체 없이 파기합니다.</p>

<h3>5. 정보주체의 권리</h3>
<p>방문자는 언제든지 자신의 개인정보에 대한 열람·정정·삭제·처리정지를 요청할 수 있으며, 본 사이트는 관련 법령에 따라 지체 없이 조치합니다.</p>

<h3>6. 문의처</h3>
<p>개인정보 처리에 관한 문의는 <b>{email}</b> 로 연락 주시기 바랍니다.</p>

<p>본 개인정보처리방침은 <b>{effective}</b>부터 시행됩니다. 내용이 변경될 경우 본 페이지를 통해 고지합니다.</p>
"""
    return "개인정보처리방침", content.strip()


def about_page(cfg, blog):
    """소개(About) — 블로그 주제(theme)에 맞춘 E-E-A-T 서술. 1인칭 경험 포함."""
    brand = cfg.get("site_brand", "")
    owner = cfg.get("owner_name", "")
    email = cfg.get("contact_email", "")
    theme = blog.get("theme", "")
    content = f"""
<h2>소개</h2>
<p>안녕하세요. <b>{brand}</b>의 <b>{theme}</b> 정보 블로그를 운영하는 <b>{owner}</b>입니다. 이 블로그를 찾아주셔서 감사합니다.</p>

<h3>이 블로그는 무엇을 다루나요</h3>
<p>이곳은 <b>{theme}</b>에 관한 실용적이고 믿을 수 있는 정보를 쉽게 풀어 전하는 공간입니다. 복잡한 전문 용어 대신, 직접 찾아보고 정리하면서 제가 이해한 방식 그대로, 초보자도 따라올 수 있게 설명하려고 합니다.</p>

<h3>왜 이 블로그를 운영하나요 (경험과 관심)</h3>
<p>저 역시 {theme} 정보를 직접 찾아 헤매며 잘못된 정보에 시간을 허비한 경험이 많았습니다. 그때마다 "믿을 만한 정보를 한곳에 정리해두면 좋겠다"는 생각을 했고, 그렇게 제가 공부하고 확인한 내용을 기록하기 시작한 것이 이 블로그의 출발점입니다.</p>

<h3>정보의 신뢰성 원칙</h3>
<ul>
<li>공공기관·학회·원자료 등 신뢰 가능한 출처를 근거로 작성합니다.</li>
<li>확인되지 않은 내용은 단정하지 않고, 사실과 의견을 구분해 전달합니다.</li>
<li>새로운 정보가 확인되면 기존 글을 업데이트합니다.</li>
<li>본 블로그의 정보는 일반적인 참고용이며, 전문가의 진단·자문을 대체하지 않습니다(자세한 내용은 면책조항 참고).</li>
</ul>

<h3>연락</h3>
<p>궁금한 점이나 정정이 필요한 내용이 있으면 <b>{email}</b> 로 알려주세요. 소중한 의견을 반영해 더 나은 콘텐츠로 보답하겠습니다.</p>
"""
    return "소개", content.strip()


def contact_page(cfg, blog):
    """연락처(Contact) — 실제 작동하는 이메일 안내."""
    brand = cfg.get("site_brand", "")
    email = cfg.get("contact_email", "")
    content = f"""
<h2>연락처</h2>
<p><b>{brand}</b>를 찾아주셔서 감사합니다. 콘텐츠에 대한 문의, 오류 정정 요청, 제휴 및 광고 문의 등 어떤 내용이든 편하게 연락 주세요.</p>

<h3>이메일 문의</h3>
<p>아래 이메일로 문의하시면 확인 후 최대한 빠르게 답변드리겠습니다.</p>
<ul>
<li>이메일: <b>{email}</b></li>
<li>답변 소요: 보통 1~3일 이내(문의량에 따라 달라질 수 있습니다)</li>
</ul>

<h3>문의 시 참고</h3>
<ul>
<li>정정 요청은 해당 글의 제목과 문제 되는 부분을 함께 적어주시면 빠르게 확인할 수 있습니다.</li>
<li>개인정보 처리 관련 문의도 위 이메일로 접수됩니다.</li>
</ul>
"""
    return "연락처", content.strip()


def disclaimer_page(cfg, blog):
    """면책조항(Disclaimer) — YMYL(건강 등) 전문가 진단/자문 대체 아님 명시."""
    brand = cfg.get("site_brand", "")
    theme = blog.get("theme", "")
    content = f"""
<h2>면책조항</h2>
<p><b>{brand}</b>의 <b>{theme}</b> 관련 콘텐츠는 일반적인 정보 제공을 목적으로 합니다. 아래 내용을 확인해 주세요.</p>

<h3>정보의 성격</h3>
<ul>
<li>본 사이트의 모든 글은 일반적인 참고 정보이며, <b>전문가의 진단·처방·자문을 대체하지 않습니다.</b></li>
<li>건강 관련 정보는 개인의 상태에 따라 다르게 적용될 수 있으므로, 증상이 있거나 지속되면 반드시 의료기관·전문의와 상담하시기 바랍니다.</li>
<li>재정·투자·법률 등 다른 주제에 대한 정보 역시 최종 판단과 책임은 이용자 본인에게 있습니다.</li>
</ul>

<h3>정확성과 책임의 한계</h3>
<ul>
<li>작성 시점 기준으로 정확한 정보를 전달하고자 노력하지만, 시간이 지나면서 내용이 달라질 수 있습니다.</li>
<li>본 사이트의 정보를 근거로 한 판단이나 행동의 결과에 대해 운영자는 법적 책임을 지지 않습니다.</li>
</ul>

<h3>외부 링크</h3>
<p>본 사이트는 참고를 위해 외부 사이트로 연결되는 링크를 포함할 수 있으며, 외부 사이트의 콘텐츠나 정책에 대해서는 책임지지 않습니다.</p>
"""
    return "면책조항", content.strip()


def terms_of_service_page(cfg, blog):
    """이용약관(Terms of Service) — 서비스 이용 조건, 저작권, 이용자 의무, 콘텐츠 제한, 약관 변경."""
    brand = cfg.get("site_brand", "")
    owner = cfg.get("owner_name", "")
    email = cfg.get("contact_email", "")
    effective = cfg.get("privacy_effective_date", "")
    content = f"""
<h2>이용약관</h2>
<p><b>{brand}</b>(이하 "본 사이트")를 이용하셔서 감사합니다. 아래 이용약관은 본 사이트 이용과 관련된 권리와 의무를 정합니다. 본 사이트에 접속하거나 콘텐츠를 이용함으로써 이용약관에 동의하는 것으로 간주됩니다.</p>

<h3>1. 서비스 이용 조건</h3>
<ul>
<li>본 사이트는 누구든지 자유롭게 접속할 수 있으며, 회원가입 없이 모든 콘텐츠를 열람할 수 있습니다.</li>
<li>이용자는 본 사이트를 합법적인 목적으로만 이용해야 하며, 불법적인 활동이나 타인의 권리를 침해하는 행위를 금합니다.</li>
<li>본 사이트의 콘텐츠를 이용하는 과정에서 다른 이용자나 제3자에게 피해를 주거나 불편을 끼치지 않아야 합니다.</li>
</ul>

<h3>2. 지적재산권</h3>
<ul>
<li>본 사이트의 모든 콘텐츠(글, 이미지, 동영상 등)는 <b>{owner}</b>가 저작권을 보유합니다.</li>
<li>이용자는 개인의 학습·정보 목적으로만 콘텐츠를 열람·복사할 수 있으며, 사전 동의 없이 상업적 목적으로 이용·배포·수정할 수 없습니다.</li>
<li>콘텐츠 인용 시에는 출처를 명확히 표시하고, 원문을 손상하지 않는 범위 내에서 이용해야 합니다.</li>
<li>본 사이트의 로고, 디자인, 구조 등 모든 요소도 지적재산권의 보호 대상입니다.</li>
</ul>

<h3>3. 이용자의 의무</h3>
<ul>
<li>이용자는 본 사이트를 이용할 때 개인정보, 로그인 정보 등을 안전하게 관리할 책임이 있습니다.</li>
<li>스팸, 바이러스, 악성 소프트웨어 배포 또는 본 사이트를 공격하는 행위를 금합니다.</li>
<li>타인의 명예를 훼손하거나, 모욕적이거나 혐오적인 댓글·메시지를 남기는 행위를 금합니다.</li>
<li>본 사이트의 보안·운영을 방해하거나 침해하는 행위를 금합니다.</li>
</ul>

<h3>4. 콘텐츠 이용 제한</h3>
<ul>
<li>본 사이트의 글, 이미지, 코드 등을 무단으로 재배포·판매·임대하거나 다른 웹사이트에 올릴 수 없습니다.</li>
<li>크롤러나 자동화 도구를 사용해 대량으로 콘텐츠를 수집하는 행위는 엄격히 금지됩니다.</li>
<li>본 사이트의 소유자나 관리자의 명시적 허락 없이 링크·프레임 등의 기술적 수단으로 콘텐츠를 편입할 수 없습니다.</li>
</ul>

<h3>5. 면책</h3>
<ul>
<li>본 사이트는 "현재 그대로" 제공되며, 특정 목적으로의 적합성이나 무결성을 보장하지 않습니다.</li>
<li>콘텐츠의 정확성, 최신성, 완전성에 관해 어떤 보증도 제공하지 않습니다.</li>
<li>본 사이트 이용으로 인한 손해(데이터 손실, 사업 손실, 간접 손해 포함)에 대해 운영자는 책임을 지지 않습니다.</li>
</ul>

<h3>6. 약관 변경</h3>
<p>본 사이트는 필요에 따라 이용약관을 변경할 수 있으며, 변경 내용은 본 페이지를 통해 공지합니다. 변경된 약관은 공지 후 즉시 적용되며, 이용자가 계속해서 본 사이트를 이용하는 것은 변경된 약관에 동의하는 것으로 간주됩니다.</p>

<h3>7. 문의</h3>
<p>이용약관에 관한 문의나 의견이 있으시면 <b>{email}</b> 로 연락 주시기 바랍니다.</p>

<p>본 이용약관은 <b>{effective}</b>부터 시행됩니다.</p>
"""
    return "이용약관", content.strip()


# 조사 문서가 확정한 필수 페이지 전부(개인정보처리방침·소개·연락처 필수 + YMYL 강력권장 면책조항 + 구글 한국 애드센스 명시 이용약관)
PAGE_BUILDERS = [privacy_policy_page, about_page, contact_page, disclaimer_page, terms_of_service_page]


def get_blog_id(service, url):
    return service.blogs().getByUrl(url=url).execute()["id"]


def existing_page_titles(service, blog_id):
    titles = set()
    request = service.pages().list(blogId=blog_id, fetchBodies=False)
    while request is not None:
        resp = request.execute()
        for item in resp.get("items", []):
            titles.add(item.get("title", ""))
        request = service.pages().list_next(request, resp)
    return titles


def create_pages_for_blog(service, cfg, blog):
    url = blog["url"]
    blog_id = get_blog_id(service, url)
    print(f"[{blog['id']}] {url} (blogId={blog_id})")

    already = existing_page_titles(service, blog_id)
    created, skipped = 0, 0
    for builder in PAGE_BUILDERS:
        title, content = builder(cfg, blog)
        if title in already:
            print(f"  건너뜀(이미 존재): {title}")
            skipped += 1
            continue
        service.pages().insert(
            blogId=blog_id, body={"title": title, "content": content}
        ).execute()
        print(f"  생성: {title}")
        created += 1
    print(f"  → 생성 {created}건, 건너뜀 {skipped}건")


def main():
    args = sys.argv[1:]
    if not args:
        print("사용법: python3 create_pages.py <blog_id> | --all", file=sys.stderr)
        sys.exit(1)

    blogs = load_json(BLOGS_FILE)["blogs"]
    cfg = load_site_config()

    if args[0] == "--all":
        targets = blogs
    else:
        targets = [b for b in blogs if b["id"] == args[0]]
        if not targets:
            print(f"blogs.json에 blog_id '{args[0]}'가 없습니다.", file=sys.stderr)
            sys.exit(1)

    service = get_blogger_service()
    for blog in targets:
        create_pages_for_blog(service, cfg, blog)


if __name__ == "__main__":
    main()
