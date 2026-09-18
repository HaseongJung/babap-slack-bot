"""네이버 카페 '2판교 라이프' 바른밥상 점심메뉴 수집."""
from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from curl_cffi import requests

from config import (
    ARTICLE_URL,
    CAFE_ID,
    HEADERS,
    KST,
    LIST_URL,
    SOURCES,
)


@dataclass
class Article:
    article_id: int
    subject: str

    @property
    def url(self) -> str:
        return f"https://cafe.naver.com/f-e/cafes/{CAFE_ID}/articles/{self.article_id}"


def parse_article_list(data: dict, today: date, keyword: str) -> Article | None:
    """목록 API 응답에서 제목에 keyword 포함 + 오늘(KST) 작성 글을 반환."""
    for item in data.get("result", {}).get("articleList", []):
        a = item.get("item", {})
        written = datetime.fromtimestamp(a.get("writeDateTimestamp", 0) / 1000, tz=KST).date()
        if keyword in a.get("subject", "") and written == today:
            return Article(a["articleId"], a["subject"])
    return None


def extract_image_urls(content_html: str) -> list[str]:
    """본문 HTML에서 cafeptthumb(카페 본문 이미지 CDN) URL만 순서대로."""
    return re.findall(r'<img[^>]+src="(https://cafeptthumb[^"]+)"', content_html)


def _session() -> requests.Session:
    s = requests.Session(impersonate="chrome")
    s.headers.update(HEADERS)
    return s


def find_today_article(s: requests.Session, keyword: str) -> Article | None:
    data = s.get(LIST_URL, timeout=10).json()
    return parse_article_list(data, datetime.now(tz=KST).date(), keyword)


def get_image_urls(s: requests.Session, article: Article) -> list[str]:
    data = s.get(ARTICLE_URL.format(aid=article.article_id), timeout=10).json()
    html = data.get("result", {}).get("article", {}).get("contentHtml", "")
    return extract_image_urls(html)


def download_images(s: requests.Session, urls: list[str], prefix: str = "lunch") -> list[Path]:
    paths = []
    for i, url in enumerate(urls):
        suffix = Path(url.split("?")[0]).suffix or ".png"
        p = Path(tempfile.gettempdir()) / f"{prefix}_{datetime.now(tz=KST):%Y%m%d}_{i}{suffix}"
        r = s.get(url, timeout=15)
        r.raise_for_status()
        p.write_bytes(r.content)
        paths.append(p)
    return paths


def collect(source: str, menu_key: str = "lunch") -> tuple[Article, list[Path]] | None:
    """오늘 해당 소스의 글을 찾아 이미지를 임시 디렉터리에 내려받는다.

    source: config.SOURCES의 키. menu_key로 그 소스의 image_index 매핑을 조회해
    해당 순서의 이미지 1장만 내려받는다(매핑에 없는 menu_key면 빈 리스트).
    """
    cfg = SOURCES[source]
    s = _session()
    article = find_today_article(s, cfg["keyword"])
    if article is None:
        return None
    urls = get_image_urls(s, article)
    image_index = cfg["image_index"].get(menu_key)
    if image_index is not None:
        urls = urls[image_index : image_index + 1]
    else:
        urls = []
    return article, download_images(s, urls, prefix=f"{source}_{menu_key}")


if __name__ == "__main__":
    result = collect("barun")
    if result is None:
        print("오늘 글 없음")
    else:
        a, imgs = result
        print(f"{a.article_id} | {a.subject}\n{a.url}")
        print("\n".join(str(p) for p in imgs))
