"""모든 설정·상수·로깅 중앙화.

환경변수는 .env 파일에서도 읽어온다 (load_env).
Slack 관련 값은 실제 운영 환경에서만 필요하므로,
test는 conftest.py에서 가짜 값을 먼저 setdefault한 뒤 import한다.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import holidays

# ── .env 로딩 ──────────────────────────────────────────────


def load_env(path: Path = Path(__file__).with_name(".env")) -> None:
    """경로에 .env가 있으면 KEY=VALUE 줄을 os.environ에 setdefault."""
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env()

# ── 시간대 / 공휴일 ────────────────────────────────────────

KST = ZoneInfo("Asia/Seoul")
KR_HOLIDAYS = holidays.country_holidays("KR")  # 음력·대체공휴일 포함

# ── Slack ──────────────────────────────────────────────────

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
SLACK_CHANNEL_ID = os.environ["SLACK_CHANNEL_ID"]

# ── 스케줄러 ───────────────────────────────────────────────

AUTO_POST_ENABLED = True
POST_HOUR = 11       # 매일 자동 포스팅 시각
DEADLINE_HOUR = 13   # 이 시각부터는 재시도 안 함
RETRY_MIN = 10       # 글 발견 실패 시 재시도 간격(분)
RETRY_MAX = 2        # 재시도 최대 횟수 (초기 1회 + 2회 = 하루 최대 3회 시도)

# ── 메뉴 이미지 매핑 ────────────────────────────────────────

MENU_IMAGE_INDEX = {"lunch": 2, "dinner": 3}  # 0-based

# ── 상태 파일 ──────────────────────────────────────────────

STATE_PATH = Path(__file__).with_name("state") / "state.json"

# ── 네이버 카페 스크래핑 ───────────────────────────────────

CAFE_ID = 30487307
MENU_ID = 26
KEYWORD = "바른밥상"  # ponytail: 타 식당 추가 시 이 키워드 목록만 손대면 됨

LIST_URL = (
    f"https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/{CAFE_ID}"
    f"/menus/{MENU_ID}/articles?page=1&pageSize=15&sortBy=TIME&viewType=L"
)
ARTICLE_URL = (
    f"https://article.cafe.naver.com/gw/v4/cafes/{CAFE_ID}/articles/{{aid}}"
    f"?query=&menuId={MENU_ID}&boardType=L&useCafeId=true&requestFrom=A"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://cafe.naver.com/",
}

# ── Ollama ─────────────────────────────────────────────

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
OLLAMA_TIMEOUT = 30  # 초

# ── 로깅 ───────────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
LOG_FILE = Path(__file__).with_name("bot.log")


def setup_logging() -> None:
    """콘솔 + 파일 핸들러를 루트 로거에 추가."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        # 기본 console handler (basicConfig가 안 불린 상태면)
        root.addHandler(logging.StreamHandler())
    # 파일 핸들러
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(fh)
