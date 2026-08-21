"""네이버 카페 '2판교 라이프' 바른밥상 점심메뉴 수집."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

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
