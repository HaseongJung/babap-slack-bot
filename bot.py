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
