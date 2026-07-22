#!/usr/bin/env python3
"""기존 블로그 글의 깨진 이미지를 catbox.moe 영구 URL로 교체하는 마이그레이션 스크립트.

처리 케이스:
1. Pixabay URL이 남아있는 글 → catbox.moe로 교체
2. 이미지 태그가 아예 없는 글 (Blogger가 base64 제거) → 새 이미지 삽입
"""

import os
import sys
import re
import json
import urllib.request
import random
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
SCOPES = ["https://www.googleapis.com/auth/blogger"]
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "client_secrets.json"


def setup_credentials(blog_type):
    if blog_type == "insurance":
        token_json = os.environ.get("INSURANCE_BLOGGER_TOKEN_JSON")
        blog_url = os.environ.get("INSURANCE_BLOG_URL", "https://salvia-insurance.blogspot.com")
    else:
        token_json = os.environ.get("BLOGGER_TOKEN_JSON")
        blog_url = "https://salviaproject.blogspot.com"

    client_secrets_json = os.environ.get("BLOGGER_CLIENT_SECRETS_JSON")

    if token_json:
        with open(TOKEN_FILE, "w") as f:
            f.write(token_json)
    if client_secrets_json:
        with open(CREDENTIALS_FILE, "w") as f:
            f.write(client_secrets_json)

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    service = build("blogger", "v3", credentials=creds)
    blog = service.blogs().getByUrl(url=blog_url).execute()
    return service, blog["id"]


def upload_to_catbox(img_bytes, content_type="image/jpeg"):
    ext = "jpg" if "jpeg" in content_type else content_type.split("/")[-1]
    boundary = f"----FormBoundary{random.randint(100000, 999999)}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="reqtype"\r\n\r\n'
        f"fileupload\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileToUpload"; filename="image.{ext}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + img_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        "https://catbox.moe/user.php",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            url = res.read().decode().strip()
        return url if url.startswith("https://files.catbox.moe/") else None
    except Exception:
        return None


def fetch_catbox_images(query, count=3):
    encoded_query = urllib.request.quote(query)
    url = (
        f"https://pixabay.com/api/?key={PIXABAY_API_KEY}"
        f"&q={encoded_query}&image_type=photo&orientation=horizontal"
        f"&per_page=15&safesearch=true&lang=en"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as res:
            data = json.loads(res.read())
        hits = data.get("hits", [])
        random.shuffle(hits)
        result = []
        for h in hits:
            if len(result) >= count:
                break
            try:
                with urllib.request.urlopen(h["webformatURL"], timeout=10) as img_res:
                    img_bytes = img_res.read()
                    content_type = img_res.headers.get("Content-Type", "image/jpeg").split(";")[0]
                catbox_url = upload_to_catbox(img_bytes, content_type)
                if catbox_url:
                    result.append(catbox_url)
            except Exception:
                continue
        return result
    except Exception:
        return []


def make_img_tag(url, idx):
    return (
        f'<p><img src="{url}" '
        f'style="max-width:100%;height:auto;border-radius:8px;margin:12px 0;" '
        f'loading="lazy" alt="{idx}번 이미지"/></p>'
    )


def insert_images_after_h2(content, images):
    """이미지 태그가 없는 글에 새 이미지를 h2 뒤에 삽입."""
    parts = content.split("</h2>")
    result = []
    img_idx = 0
    for i, part in enumerate(parts):
        result.append(part)
        if i < len(parts) - 1:
            result.append("</h2>")
            if img_idx < len(images):
                result.append(make_img_tag(images[img_idx], img_idx + 1))
                img_idx += 1
    return "".join(result)


def fix_post(content, title):
    """글 내용을 분석해서 적절한 방식으로 이미지 수정."""
    has_pixabay = bool(re.search(r'src="https://pixabay\.com/', content))
    has_any_img = bool(re.search(r'<img[^>]+>', content))
    h2_count = content.count("</h2>")

    # 케이스 1: Pixabay URL이 남아있는 경우 → catbox로 교체
    if has_pixabay:
        img_tags = re.findall(r'<img[^>]+src="https://pixabay\.com/[^"]*"[^>]*>', content)
        new_images = fetch_catbox_images(title[:80], count=len(img_tags))
        if not new_images:
            return content, False, "이미지 검색 실패"
        new_content = content
        for i, old_tag in enumerate(img_tags):
            if i >= len(new_images):
                break
            new_tag = re.sub(
                r'src="https://pixabay\.com/[^"]*"',
                f'src="{new_images[i]}"',
                old_tag
            )
            new_content = new_content.replace(old_tag, new_tag, 1)
        return new_content, True, f"Pixabay URL {len(new_images)}개 교체"

    # 케이스 2: 이미지가 없고 h2가 있는 경우 → 이미지 새로 삽입 (Blogger가 base64 제거한 글)
    if not has_any_img and h2_count >= 2:
        count = min(h2_count, 3)
        new_images = fetch_catbox_images(title[:80], count=count)
        if not new_images:
            return content, False, "이미지 검색 실패"
        new_content = insert_images_after_h2(content, new_images)
        return new_content, True, f"이미지 {len(new_images)}개 새로 삽입"

    return content, False, "수정 불필요"


def get_all_posts(service, blog_id):
    posts = []
    page_token = None
    while True:
        kwargs = dict(blogId=blog_id, maxResults=500, fetchBodies=True, status="LIVE")
        if page_token:
            kwargs["pageToken"] = page_token
        response = service.posts().list(**kwargs).execute()
        posts.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return posts


def main():
    blog_type = sys.argv[1] if len(sys.argv) > 1 else "ko"
    print(f"블로그 타입: {blog_type}")

    service, blog_id = setup_credentials(blog_type)
    print(f"블로그 ID: {blog_id}")

    print("글 목록 가져오는 중...")
    posts = get_all_posts(service, blog_id)
    print(f"총 {len(posts)}개 글 발견")

    fixed = 0
    skipped = 0
    for post in posts:
        title = post.get("title", "")
        content = post.get("content", "")
        post_id = post["id"]

        new_content, changed, reason = fix_post(content, title)

        if not changed:
            skipped += 1
            continue

        print(f"수정 중: {title[:60]} ({reason})")
        try:
            service.posts().patch(
                blogId=blog_id,
                postId=post_id,
                body={"content": new_content}
            ).execute()
            print(f"  완료")
            fixed += 1
        except Exception as e:
            print(f"  업데이트 실패: {e}")
            skipped += 1

    print(f"\n완료: {fixed}개 수정, {skipped}개 스킵")


if __name__ == "__main__":
    main()
