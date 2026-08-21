"""바른밥상 점심메뉴 Slack 봇 — Socket Mode 단일 상시 프로세스."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
STATE_PATH = Path(__file__).with_name("state.json")
POST_HOUR = 11       # 매일 자동 포스팅 시각
DEADLINE_HOUR = 13   # 이 시각부터는 재시도 안 함
RETRY_MIN = 10       # 글 발견 실패 시 재시도 간격(분)

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

app = App(token=os.environ["SLACK_BOT_TOKEN"], token_verification_enabled=False)
CHANNEL = os.environ["SLACK_CHANNEL_ID"]


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
