"""네이버 카페 '2판교 라이프' 바른밥상 점심메뉴 수집."""
from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CAFE_ID = 30487307
MENU_ID = 26
KEYWORD = "바른밥상"  # ponytail: 타 식당 추가 시 이 키워드 목록만 손대면 됨
KST = ZoneInfo("Asia/Seoul")

LIST_URL = (
    f"https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/{CAFE_ID}"
    f"/menus/{MENU_ID}/articles?page=1&pageSize=15&sortBy=TIME&viewType=L"
)
ARTICLE_URL = (
    f"https://article.cafe.naver.com/gw/v4/cafes/{CAFE_ID}/articles/{{aid}}"
    f"?query=&menuId={MENU_ID}&boardType=L&useCafeId=true&requestFrom=A"
)


@dataclass
class Article:
    article_id: int
    subject: str

    @property
    def url(self) -> str:
        return f"https://cafe.naver.com/f-e/cafes/{CAFE_ID}/articles/{self.article_id}"


def parse_article_list(data: dict, today: date) -> Article | None:
    """목록 API 응답에서 제목에 KEYWORD 포함 + 오늘(KST) 작성 글을 반환."""
    for item in data.get("result", {}).get("articleList", []):
        a = item.get("item", {})
        written = datetime.fromtimestamp(a.get("writeDateTimestamp", 0) / 1000, tz=KST).date()
        if KEYWORD in a.get("subject", "") and written == today:
            return Article(a["articleId"], a["subject"])
    return None


def extract_image_urls(content_html: str) -> list[str]:
    """본문 HTML에서 cafeptthumb(카페 본문 이미지 CDN) URL만 순서대로."""
    return re.findall(r'<img[^>]+src="(https://cafeptthumb[^"]+)"', content_html)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://cafe.naver.com/",
}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def find_today_article(s: requests.Session) -> Article | None:
    data = s.get(LIST_URL, timeout=10).json()
    return parse_article_list(data, datetime.now(tz=KST).date())


def get_image_urls(s: requests.Session, article: Article) -> list[str]:
    data = s.get(ARTICLE_URL.format(aid=article.article_id), timeout=10).json()
    html = data.get("result", {}).get("article", {}).get("contentHtml", "")
    return extract_image_urls(html)


def download_images(s: requests.Session, urls: list[str]) -> list[Path]:
    paths = []
    for i, url in enumerate(urls):
        suffix = Path(url.split("?")[0]).suffix or ".png"
        p = Path(tempfile.gettempdir()) / f"lunch_{datetime.now(tz=KST):%Y%m%d}_{i}{suffix}"
        r = s.get(url, timeout=15)
        r.raise_for_status()
        p.write_bytes(r.content)
        paths.append(p)
    return paths


def collect(image_index: int | None = None) -> tuple[Article, list[Path]] | None:
    """오늘 바른밥상 글을 찾아 이미지를 임시 디렉터리에 내려받는다.

    image_index: 0-based. 지정하면 그 순서의 이미지 1장만 내려받는다
    (점심=2, 저녁=3 — 카페 게시 패턴). 범위 밖이면 빈 리스트.
    """
    s = _session()
    article = find_today_article(s)
    if article is None:
        return None
    urls = get_image_urls(s, article)
    if image_index is not None:
        urls = urls[image_index : image_index + 1]
    return article, download_images(s, urls)


if __name__ == "__main__":
    result = collect()
    if result is None:
        print("오늘 글 없음")
    else:
        a, imgs = result
        print(f"{a.article_id} | {a.subject}\n{a.url}")
        print("\n".join(str(p) for p in imgs))
