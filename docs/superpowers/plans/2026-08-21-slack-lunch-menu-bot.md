# 바른밥상 점심메뉴 Slack 봇 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버 카페 "2판교 라이프"의 바른밥상 일일 점심메뉴 글을 수집해 Slack 채널에 매일 11:00 자동 포스팅 + `/lunch` 커맨드 수동 응답하는 단일 Python 프로세스.

**Architecture:** 상시 구동 프로세스 1개. 수집은 무인증 HTTP(네이버 카페 내부 API 2개 + 이미지 CDN), Slack은 Bolt Socket Mode(공인 URL 불필요). 스케줄은 내장 스레드 루프가 담당.

**Tech Stack:** Python 3.12+, uv(가상환경/의존성), slack-bolt, requests, pytest

**Spec:** `docs/superpowers/specs/2026-08-21-slack-lunch-menu-bot-design.md`

## Global Constraints

- 가상환경/의존성 관리: **uv** (`uv sync`, `uv run`). pip 직접 사용 금지.
- 런타임 의존성은 `slack-bolt`, `requests`, `tzdata`(Windows의 zoneinfo용) 3개만.
- 모든 시각 판단은 `ZoneInfo("Asia/Seoul")` 기준.
- 경로는 `pathlib`, 임시파일은 `tempfile` (Windows→macOS 이식성).
- 카페 API 요청 시 헤더 `User-Agent`(브라우저) + `Referer: https://cafe.naver.com/` 필수.
- 글 필터: 제목에 `"바른밥상"` 포함 + 작성일이 오늘(KST).
- 슬래시 커맨드명: `/lunch` (한글 불가).
- 자동 포스팅: 매일 11:00, 실패 시 10분 간격 재시도, 13:00 마감.
- 중복 방지: `state.json`의 `last_posted_date`.

---

### Task 1: 프로젝트 스캐폴드 (uv)

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`

**Interfaces:**
- Consumes: 없음
- Produces: uv 프로젝트(`.venv`, `uv.lock`), `uv run pytest` 실행 환경

- [ ] **Step 1: pyproject.toml 작성**

```toml
[project]
name = "slack-lunch-bot"
version = "0.1.0"
description = "네이버 카페 바른밥상 점심메뉴 Slack 봇"
requires-python = ">=3.12"
dependencies = [
    "slack-bolt>=1.20",
    "requests>=2.32",
    "tzdata>=2024.1",
]

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: .gitignore 작성**

```gitignore
.venv/
__pycache__/
.pytest_cache/
.env
bot.log
state.json
```

(`uv.lock`는 커밋한다 — 재현 가능한 의존성 고정)

- [ ] **Step 3: .env.example 작성**

```env
# Slack 앱 생성 후 값 채워 .env 로 복사 (Task 6)
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_CHANNEL_ID=C0123456789
```

- [ ] **Step 4: uv 동기화 및 pytest 동작 확인**

Run: `uv sync`
Expected: `.venv` 생성, slack-bolt/requests/tzdata/pytest 설치, `uv.lock` 생성

Run: `uv run pytest`
Expected: `no tests ran` (collected 0 items) — 에러 없음

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore .env.example uv.lock
git commit -m "chore: uv project scaffold"
```

---

### Task 2: menu.py 순수 로직 (글 검색·이미지 URL 추출)

**Files:**
- Create: `menu.py`
- Create: `conftest.py` (루트 — sys.path 등록 역할)
- Test: `tests/test_menu.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `Article` dataclass: `Article(article_id: int, subject: str)`, 프로퍼티 `url: str`
  - `parse_article_list(data: dict, today: date) -> Article | None`
  - `extract_image_urls(content_html: str) -> list[str]`

- [ ] **Step 1: 실패 테스트 작성**

`conftest.py` (빈 역할만):

```python
# 루트 conftest — 루트 디렉터리를 sys.path에 추가해 `import menu` 가능하게 함
```

`tests/test_menu.py`:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_menu.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'menu'` 또는 `ImportError`

- [ ] **Step 3: menu.py 구현 (순수 로직 부분만)**

```python
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
```

같은 파일에 이어서:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_menu.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add menu.py conftest.py tests/test_menu.py
git commit -m "feat: parse cafe article list and extract image urls"
```

---

### Task 3: menu.py I/O (수집 파이프라인 + 단독 실행 모드)

**Files:**
- Modify: `menu.py` (끝에 추가)
- Test: `tests/test_menu.py` (끝에 추가)

**Interfaces:**
- Consumes: Task 2의 `Article`, `parse_article_list`, `extract_image_urls`
- Produces:
  - `collect() -> tuple[Article, list[Path]] | None` — 오늘 글 + 다운로드된 이미지 임시파일 목록. 글 없으면 `None`
  - `uv run python menu.py` — 수집 단독 실행(오늘 글 ID/제목/URL/이미지 경로 출력)

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_menu.py` 끝에:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_menu.py -v`
Expected: 3개 신규 테스트 FAIL — `AttributeError: module 'menu' has no attribute 'collect'`

- [ ] **Step 3: 구현 — menu.py 맨 위 import 수정 + 끝에 I/O 추가**

`menu.py` 상단 import 블록을 다음으로 교체:

```python
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
```

`menu.py` 끝에 추가:

```python
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
        p.write_bytes(s.get(url, timeout=15).content)
        paths.append(p)
    return paths


def collect() -> tuple[Article, list[Path]] | None:
    """오늘 바른밥상 글을 찾아 이미지를 임시 디렉터리에 내려받는다."""
    s = _session()
    article = find_today_article(s)
    if article is None:
        return None
    return article, download_images(s, get_image_urls(s, article))


if __name__ == "__main__":
    result = collect()
    if result is None:
        print("오늘 글 없음")
    else:
        a, imgs = result
        print(f"{a.article_id} | {a.subject}\n{a.url}")
        print("\n".join(str(p) for p in imgs))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_menu.py -v`
Expected: 8 passed

- [ ] **Step 5: 실제 카페 대상 라이브 검증 (Slack 토큰 불필요)**

Run: `uv run python menu.py`
Expected: 오늘 바른밥상 글이 올라와 있는 시간대(평일 10:30 이후)라면 `5xxx | 8월 21일 판교이노베이션랩 "바른밥상" ...` + 이미지 임시파일 경로 출력. 글이 없는 시간대면 `오늘 글 없음` — 둘 다 정상.

- [ ] **Step 6: Commit**

```bash
git add menu.py tests/test_menu.py
git commit -m "feat: cafe collection pipeline with retries and standalone mode"
```

---

### Task 4: 스케줄 결정 로직 + 상태 파일 (bot.py 전반부)

**Files:**
- Create: `bot.py`
- Test: `tests/test_bot.py`

**Interfaces:**
- Consumes: 없음 (이 태스크의 bot.py는 아직 slack_bolt 미임포트)
- Produces:
  - `STATE_PATH: Path` (모듈 상수)
  - `load_state() -> dict`, `save_state(state: dict) -> None`
  - `next_post_time(state: dict, now: datetime) -> datetime` — 오늘 완료/마감 지나면 내일 11:00, 아니면 max(오늘 11:00, now)
  - `next_after(ok: bool, state: dict, now: datetime) -> datetime` — 시도 후 다음 시각 (실패+13시 전이면 +10분)

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_bot.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

import bot

KST = ZoneInfo("Asia/Seoul")


def dt(h, m=0):
    return datetime(2026, 8, 21, h, m, tzinfo=KST)  # 금요일


TOMORROW_11 = datetime(2026, 8, 22, 11, 0, tzinfo=KST)


def test_next_when_already_posted_today():
    assert bot.next_post_time({"last_posted_date": "2026-08-21"}, dt(9)) == TOMORROW_11


def test_next_when_not_posted_before_11():
    assert bot.next_post_time({}, dt(9)) == dt(11)


def test_next_when_missed_but_before_deadline():
    assert bot.next_post_time({}, dt(11, 20)) == dt(11, 20)


def test_next_when_past_deadline():
    assert bot.next_post_time({}, dt(13, 30)) == TOMORROW_11


def test_retry_10min_after_failed_attempt():
    assert bot.next_after(False, {}, dt(11, 0)) == dt(11, 10)


def test_give_up_after_deadline():
    assert bot.next_after(False, {}, dt(13, 0)) == TOMORROW_11


def test_next_day_after_success():
    state = {"last_posted_date": "2026-08-21"}
    assert bot.next_after(True, state, dt(11, 0)) == TOMORROW_11


def test_state_roundtrip(tmp_path, monkeypatch):
    p = tmp_path / "state.json"
    monkeypatch.setattr(bot, "STATE_PATH", p)
    assert bot.load_state() == {}
    bot.save_state({"last_posted_date": "2026-08-21"})
    assert bot.load_state() == {"last_posted_date": "2026-08-21"}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_bot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot'`

- [ ] **Step 3: bot.py 작성 (이 태스크 분량)**

```python
"""바른밥상 점심메뉴 Slack 봇 — Socket Mode 단일 상시 프로세스."""
from __future__ import annotations

import json
import os
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
STATE_PATH = Path(__file__).with_name("state.json")
POST_HOUR = 11       # 매일 자동 포스팅 시각
DEADLINE_HOUR = 13   # 이 시각부터는 재시도 안 함
RETRY_MIN = 10       # 글 발견 실패 시 재시도 간격(분)


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def next_post_time(state: dict, now: datetime) -> datetime:
    """다음 자동 포스팅 목표 시각. 오늘 완료했거나 마감 지났으면 내일 11시."""
    today = now.date()
    tomorrow = datetime.combine(today + timedelta(days=1), dtime(POST_HOUR), tzinfo=KST)
    if state.get("last_posted_date") == today.isoformat() or now.hour >= DEADLINE_HOUR:
        return tomorrow
    return max(datetime.combine(today, dtime(POST_HOUR), tzinfo=KST), now)


def next_after(ok: bool, state: dict, now: datetime) -> datetime:
    """포스팅 시도 1회 후의 다음 시각. 실패+마감 전이면 10분 뒤 재시도."""
    if not ok and now.hour < DEADLINE_HOUR:
        return now + timedelta(minutes=RETRY_MIN)
    return next_post_time(state, now)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_bot.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add bot.py tests/test_bot.py
git commit -m "feat: schedule decision logic and posted-state file"
```

---

### Task 5: Slack Bolt 앱 + 포스팅 + 커맨드 + 스케줄러 루프

**Files:**
- Modify: `bot.py` (이어서 추가), `conftest.py` (env 스텁 추가)
- Test: `tests/test_bot.py` (끝에 추가)

**Interfaces:**
- Consumes: Task 3의 `menu.collect()`, `menu.Article`; Task 4의 상태/스케줄 함수
- Produces:
  - `post_menu() -> tuple[bool, str]` — 수집→채널 포스팅→state 저장. 성공 여부와 사용자용 메시지
  - `/lunch` 슬래시 커맨드 핸들러
  - `main()` — 스케줄러 스레드 + SocketModeHandler 시작

- [ ] **Step 1: conftest.py에 env 스텁 추가**

`conftest.py` 전체 교체:

```python
# 루트 conftest — 루트 디렉터리를 sys.path에 추가 + 테스트용 슬랙 env 스텁
import os

os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("SLACK_CHANNEL_ID", "C-TEST")
```

- [ ] **Step 2: 실패 테스트 추가**

`tests/test_bot.py` 끝에:

```python
import json


def test_post_menu_uploads_and_saves_state(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(bot.app.client, "chat_postMessage", lambda **kw: calls.append(("msg", kw)) or {})
    monkeypatch.setattr(bot.app.client, "files_upload_v2", lambda **kw: calls.append(("file", kw)) or {})
    img = tmp_path / "menu.png"
    img.write_bytes(b"x")
    monkeypatch.setattr(bot.menu, "collect", lambda: (bot.menu.Article(5298, "오늘의 메뉴"), [img]))
    monkeypatch.setattr(bot, "STATE_PATH", tmp_path / "state.json")

    ok, msg = bot.post_menu()

    assert ok is True
    assert calls[0][0] == "msg" and "오늘의 메뉴" in calls[0][1]["text"]
    assert calls[1] == ("file", {"channel": "C-TEST", "file": str(img), "title": "오늘의 메뉴"})
    assert not img.exists()  # 임시파일 삭제 확인
    expected_date = datetime.now(tz=KST).date().isoformat()
    assert json.loads((tmp_path / "state.json").read_text(encoding="utf-8")) == {
        "last_posted_date": expected_date
    }


def test_post_menu_no_article_today(monkeypatch, tmp_path):
    monkeypatch.setattr(bot.menu, "collect", lambda: None)
    monkeypatch.setattr(bot, "STATE_PATH", tmp_path / "state.json")
    ok, msg = bot.post_menu()
    assert ok is False
    assert "안 올라왔" in msg
    assert not (tmp_path / "state.json").exists()


def test_post_menu_zero_images_still_posts_link(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(bot.app.client, "chat_postMessage", lambda **kw: calls.append("msg") or {})
    monkeypatch.setattr(bot.app.client, "files_upload_v2", lambda **kw: calls.append("file") or {})
    monkeypatch.setattr(bot.menu, "collect", lambda: (bot.menu.Article(5298, "오늘의 메뉴"), []))
    monkeypatch.setattr(bot, "STATE_PATH", tmp_path / "state.json")

    ok, msg = bot.post_menu()

    assert ok is True
    assert calls == ["msg", "msg"]  # 본문 메시지 + 이미지 없음 안내, 파일 업로드 없음
    assert (tmp_path / "state.json").exists()
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `uv run pytest tests/test_bot.py -v`
Expected: 3개 신규 FAIL — `AttributeError: module 'bot' has no attribute 'app'`

- [ ] **Step 4: bot.py에 Slack 부분 구현**

`bot.py`의 기존 import 블록(`from zoneinfo import ZoneInfo`까지) 뒤에 추가:

```python
import logging
import threading
import time
```

기존 import 블록 뒤에 이어서:

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log", encoding="utf-8")],
)
log = logging.getLogger("lunchbot")


def load_env(path: Path = Path(__file__).with_name(".env")) -> None:
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env()

import menu  # noqa: E402
from slack_bolt import App  # noqa: E402
from slack_bolt.adapter.socket_mode import SocketModeHandler  # noqa: E402

app = App(token=os.environ["SLACK_BOT_TOKEN"])
CHANNEL = os.environ["SLACK_CHANNEL_ID"]
```

파일 끝에 추가:

```python
def post_menu() -> tuple[bool, str]:
    """수집해서 채널에 올리고 state를 갱신한다. (ok, 사용자용 메시지) 반환."""
    result = menu.collect()
    if result is None:
        return False, "아직 오늘 메뉴가 안 올라왔어요 (보통 10:00~10:30 업로드)"
    article, images = result
    app.client.chat_postMessage(
        channel=CHANNEL, text=f"🍚 *{article.subject}*\n<{article.url}|원문 보기>"
    )
    for p in images:
        app.client.files_upload_v2(channel=CHANNEL, file=str(p), title=article.subject)
        p.unlink(missing_ok=True)
    if not images:
        app.client.chat_postMessage(channel=CHANNEL, text="⚠️ 글은 올라왔는데 이미지가 없어요. 원문 링크만 남깁니다.")
    save_state({"last_posted_date": datetime.now(tz=KST).date().isoformat()})
    return True, f"업로드 완료: {article.subject} ({len(images)}장)"
    # ponytail: 업로드 도중 실패하면 state 미갱신 → 다음 재시도에 메시지가 중복될 수 있음. 희귀 케이스라 수용.


@app.command("/lunch")
def lunch(ack, respond):
    ack()
    try:
        _, msg = post_menu()
    except Exception:
        log.exception("수동 호출 실패")
        msg = "오류가 났어요. 로그(bot.log)를 확인해 주세요."
    respond(msg)


def scheduler_loop() -> None:
    next_run = next_post_time(load_state(), datetime.now(tz=KST))
    log.info("스케줄러 시작, 다음 실행: %s", next_run.isoformat())
    while True:
        now = datetime.now(tz=KST)
        if now < next_run:
            time.sleep(min((next_run - now).total_seconds(), 60))
            continue
        log.info("자동 포스팅 시도")
        try:
            ok, msg = post_menu()
            log.info("%s", msg)
        except Exception:
            log.exception("자동 포스팅 실패")
            ok = False
        next_run = next_after(ok, load_state(), datetime.now(tz=KST))


def main() -> None:
    threading.Thread(target=scheduler_loop, daemon=True).start()
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 전체 테스트 통과 확인**

Run: `uv run pytest -v`
Expected: 19 passed (menu 8 + bot 11)

- [ ] **Step 6: Commit**

```bash
git add bot.py conftest.py tests/test_bot.py
git commit -m "feat: slack bolt app with /lunch command and auto-post scheduler"
```

---

### Task 6: Slack 앱 생성 + .env + 라이브 검증 + README

**Files:**
- Create: `README.md`
- Create: `.env` (gitignored — 커밋하지 않음!)

**Interfaces:**
- Consumes: Task 1~5 전체
- Produces: 실행 가능한 완성 봇, 운영 문서

- [ ] **Step 1: Slack 앱 생성 (수동, 브라우저 작업)**

1. https://api.slack.com/apps → **Create New App** → From scratch, 이름 `lunch-bot`
2. **Socket Mode** 켜기 → App-Level Token 생성 (scope: `connections:write`) → 값을 `SLACK_APP_TOKEN`으로
3. **OAuth & Permissions** → Bot Token Scopes: `chat:write`, `files:write`, `commands` → Install to Workspace → 값을 `SLACK_BOT_TOKEN`으로
4. **Slash Commands** → Create: Command `/lunch`, Request URL는 더미(예: `https://example.com`) — Socket Mode면 호출은 소켓으로 옴
5. 봇을 대상 채널에 초대 (`/invite @lunch-bot`)

- [ ] **Step 2: .env 작성**

`.env.example`을 복사해 실제 값으로:

```env
SLACK_BOT_TOKEN=xoxb-<실제값>
SLACK_APP_TOKEN=xapp-<실제값>
SLACK_CHANNEL_ID=C<대상채널ID>
```

채널 ID는 Slack에서 채널 우클릭 → 채널 세부정보 → 맨 아래 ID.

- [ ] **Step 3: 봇 실행 + 라이브 검증**

Run: `uv run python bot.py`
Expected: `SocketModeClient#start()` 로그 후 대기 상태.

Slack 테스트 채널에서 `/lunch` 입력 → 글 올라온 시간대면 메시지+이미지 게시, 아니면 "아직 안 올라왔어요" 응답. `state.json` 생성 확인. Ctrl+C 종료.

- [ ] **Step 4: README 작성**

```markdown
# 바른밥상 점심메뉴 Slack 봇

네이버 카페 '2판교 라이프'의 바른밥상 오늘 메뉴 글을 Slack 채널에 올린다.
매일 11:00 (KST) 자동 포스팅 + `/lunch` 커맨드 수동 호출.

## 실행 (Windows 테스트 / Mac Studio 동일)

    uv sync
    cp .env.example .env   # 값 채우기
    uv run python bot.py

## 수집만 단독 확인 (Slack 불필요)

    uv run python menu.py

## Slack 앱 설정

Task 6 Step 1 절차(`docs/superpowers/plans/2026-08-21-slack-lunch-menu-bot.md`) 참조.
Socket Mode라 공인 URL/포트 불필요.

## Mac Studio 상시 구동 (launchd)

`~/Library/LaunchAgents/com.slackbot.lunch.plist`:

    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
      <key>Label</key><string>com.slackbot.lunch</string>
      <key>WorkingDirectory</key><string>/Users/USERNAME/slack_bot</string>
      <key>ProgramArguments</key>
      <array>
        <string>/Users/USERNAME/slack_bot/.venv/bin/python</string>
        <string>bot.py</string>
      </array>
      <key>RunAtLoad</key><true/>
      <key>KeepAlive</key><true/>
      <key>StandardOutPath</key><string>/tmp/lunchbot.out</string>
      <key>StandardErrorPath</key><string>/tmp/lunchbot.err</string>
    </dict>
    </plist>

등록: `launchctl load ~/Library/LaunchAgents/com.slackbot.lunch.plist`
(Mac에서도 `uv sync` 먼저 — `.venv` 경로가 plist와 일치해야 함)

## 설정값

| 항목 | 위치 | 기본 |
|---|---|---|
| 자동 포스팅 시각 | `bot.py` `POST_HOUR` | 11 |
| 재시도 마감 | `bot.py` `DEADLINE_HOUR` | 13 |
| 재시도 간격(분) | `bot.py` `RETRY_MIN` | 10 |
| 대상 식당 키워드 | `menu.py` `KEYWORD` | 바른밥상 |

로그: 콘솔 + `bot.log`. 중복방지 상태: `state.json`.
```

- [ ] **Step 5: 최종 확인 + Commit**

Run: `uv run pytest -v`
Expected: 19 passed

```bash
git add README.md
git commit -m "docs: README with setup, launchd deploy guide"
```

(.env는 gitignore되어 있으니 절대 `git add`하지 않도록 확인)

---

## 셀프 리뷰 결과

- 스펙 커버리지: 자동 포스팅(Task 4,5), 수동 `/lunch`(Task 5), 이미지 처리(Task 3,5), 에러처리 3종(Task 3 재시도/Task 5 0장·업로드 실패), 로그(Task 5), 배포 문서(Task 6), 테스트 전략(Task 2~5 단위 + Task 3/6 라이브) — 전 스펙 섹션 대응 ✅
- 플레이스홀더 스캔: "적절히", "TBD", "Task N 참조"(코드 없이) 없음 ✅
- 타입 일치: `Article(article_id, subject)` / `collect() -> tuple[Article, list[Path]] | None` / `post_menu() -> tuple[bool, str]` / `next_post_time(state, now)` / `next_after(ok, state, now)` 전 태스크 일관 ✅
