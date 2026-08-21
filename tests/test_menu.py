import requests
from datetime import date

from menu import Article, extract_image_urls, parse_article_list

# 2026-08-21 실측 응답 축약본. writeDateTimestamp는 KST 기준:
#   5299 → 08-21 (송원식당=타 식당), 5298 → 08-21 (바른밥상=타깃),
#   5288 → 08-20 (바른밥상=어제 글)
LIST_JSON = {
    "result": {
        "articleList": [
            {"type": "ARTICLE", "item": {
                "articleId": 5299,
                "subject": "8월22일 송원식당 점심메뉴입니다",
                "writeDateTimestamp": 1787277268610,
            }},
            {"type": "ARTICLE", "item": {
                "articleId": 5298,
                "subject": "8월 21일 판교이노베이션랩 \"바른밥상\" 오늘의 메뉴",
                "writeDateTimestamp": 1787274606480,
            }},
            {"type": "ARTICLE", "item": {
                "articleId": 5288,
                "subject": "8월 20일 판교이노베이션랩 \"바른밥상\" 오늘의 메뉴",
                "writeDateTimestamp": 1787188206480,
            }},
        ]
    }
}

TODAY = date(2026, 8, 21)


def test_parse_finds_today_barunbabsang():
    a = parse_article_list(LIST_JSON, TODAY)
    assert a == Article(
        article_id=5298,
        subject="8월 21일 판교이노베이션랩 \"바른밥상\" 오늘의 메뉴",
    )
    assert a.url == "https://cafe.naver.com/f-e/cafes/30487307/articles/5298"


def test_parse_skips_other_restaurant_and_yesterday():
    items = LIST_JSON["result"]["articleList"]
    data = {"result": {"articleList": [items[0], items[2]]}}  # 타 식당 + 어제 바른밥상
    assert parse_article_list(data, TODAY) is None


def test_parse_empty_list():
    assert parse_article_list({"result": {"articleList": []}}, TODAY) is None


CONTENT_HTML = """<div class="se-viewer">
<a data-linktype="img" data-linkdata='{"src": "https://cafeptthumb-phinf.pstatic.net/AAA.png"}'>
<img src="https://cafeptthumb-phinf.pstatic.net/2026img1.png?type=w1600" alt="" class="se-image-resource" />
<img src="https://cafeptthumb-phinf.pstatic.net/2026img2.png?type=w1600" alt="" class="se-image-resource" />
<img src="https://ssl.pstatic.net/static/cafe/other.png" alt="" />
</div>"""


def test_extract_image_urls_only_cafeptthumb_in_order():
    urls = extract_image_urls(CONTENT_HTML)
    assert urls == [
        "https://cafeptthumb-phinf.pstatic.net/2026img1.png?type=w1600",
        "https://cafeptthumb-phinf.pstatic.net/2026img2.png?type=w1600",
    ]


def test_extract_image_urls_empty():
    assert extract_image_urls("<p>텍스트만</p>") == []


# Task 3: I/O tests
from pathlib import Path

import menu


def test_collect_returns_none_when_no_article(monkeypatch):
    monkeypatch.setattr(menu, "find_today_article", lambda s: None)
    assert menu.collect() is None


def test_collect_wires_find_download(monkeypatch):
    art = menu.Article(5298, "오늘의 메뉴")
    monkeypatch.setattr(menu, "find_today_article", lambda s: art)
    monkeypatch.setattr(menu, "get_image_urls", lambda s, a: ["u1", "u2"])
    monkeypatch.setattr(menu, "download_images", lambda s, urls: [Path("/tmp/a"), Path("/tmp/b")])
    assert menu.collect() == (art, [Path("/tmp/a"), Path("/tmp/b")])


def test_download_images_writes_files(monkeypatch, tmp_path):
    class FakeResp:
        content = b"pngdata"
        def raise_for_status(self):
            pass

    class FakeSession:
        def get(self, url, **kw):
            return FakeResp()

    monkeypatch.setattr(menu.tempfile, "gettempdir", lambda: str(tmp_path))
    paths = menu.download_images(
        FakeSession(), ["https://cafeptthumb-phinf.pstatic.net/a/b.png?type=w1600"]
    )
    assert len(paths) == 1
    assert paths[0].read_bytes() == b"pngdata"
    assert paths[0].name.startswith("lunch_") and paths[0].suffix == ".png"


def test_download_images_raises_on_http_error(monkeypatch, tmp_path):
    class ErrResp:
        content = b"not found"
        def raise_for_status(self):
            raise requests.HTTPError("404")

    class FakeSession:
        def get(self, url, **kw):
            return ErrResp()

    monkeypatch.setattr(menu.tempfile, "gettempdir", lambda: str(tmp_path))
    try:
        menu.download_images(
            FakeSession(), ["https://cafeptthumb-phinf.pstatic.net/a/b.png?type=w1600"]
        )
        assert False, "should have raised"
    except requests.HTTPError:
        pass
    assert not any(tmp_path.iterdir())
