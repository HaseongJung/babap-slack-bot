"""바른밥상 점심메뉴 Slack 봇 — Socket Mode 단일 상시 프로세스."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import holidays

KST = ZoneInfo("Asia/Seoul")
KR_HOLIDAYS = holidays.country_holidays("KR")  # 음력·대체공휴일 포함, 연도별 자동 확장
STATE_PATH = Path(__file__).with_name("state.json")
POST_HOUR = 11       # 매일 자동 포스팅 시각
DEADLINE_HOUR = 13   # 이 시각부터는 재시도 안 함
RETRY_MIN = 10       # 글 발견 실패 시 재시도 간격(분)
AUTO_POST_ENABLED = True  # 평일(공휴일 제외) 11시에 점심만 자동 발송
MENU_IMAGE_INDEX = {"lunch": 2, "dinner": 3}  # 0-based: 3번째 사진=점심, 4번째=저녁

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("lunchbot")

_post_lock = threading.Lock()


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
# skip startup auth.test so tests can import with a fake token
CHANNEL = os.environ["SLACK_CHANNEL_ID"]


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("state.json 읽기 실패, 빈 상태로 시작")
        return {}


def save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_PATH)


def is_business_day(d: date) -> bool:
    """KST 기준 평일이고 공휴일이 아닌 날."""
    return d.weekday() < 5 and d not in KR_HOLIDAYS


def next_business_day(d: date) -> date:
    d += timedelta(days=1)
    while not is_business_day(d):
        d += timedelta(days=1)
    return d


def next_post_time(state: dict, now: datetime) -> datetime:
    """다음 자동 포스팅 목표 시각. 오늘 끝났거나 휴일이면 다음 영업일 11시."""
    today = now.date()
    done = state.get("lunch") == today.isoformat() or now.hour >= DEADLINE_HOUR
    if done or not is_business_day(today):
        return datetime.combine(next_business_day(today), dtime(POST_HOUR), tzinfo=KST)
    return max(datetime.combine(today, dtime(POST_HOUR), tzinfo=KST), now)


def next_after(ok: bool, state: dict, now: datetime) -> datetime:
    """포스팅 시도 1회 후의 다음 시각. 실패+마감 전이면 10분 뒤 재시도."""
    if not ok and now.hour < DEADLINE_HOUR:
        return now + timedelta(minutes=RETRY_MIN)
    return next_post_time(state, now)


def post_menu(menu_key: str = "lunch") -> tuple[bool, str]:
    """수집해서 채널에 올리고 state를 갱신한다. (ok, 사용자용 메시지) 반환.

    수동 호출 기준: 이미 보냈어도 다시 보내준다 (state는 자동 포스팅용 기록).
    """
    with _post_lock:
        result = menu.collect(image_index=MENU_IMAGE_INDEX[menu_key])
        if result is None:
            return False, "아직 오늘 메뉴가 안 올라왔어요 (보통 10:00~10:30 업로드)"
        article, images = result
        app.client.chat_postMessage(
            channel=CHANNEL, text=f"🍚 *{article.subject}*\n<{article.url}|원문 보기>"
        )
        try:
            for p in images:
                app.client.files_upload_v2(channel=CHANNEL, file=str(p), title=article.subject)
        finally:
            for p in images:
                p.unlink(missing_ok=True)
        if not images:
            app.client.chat_postMessage(channel=CHANNEL, text="⚠️ 글은 올라왔는데 이미지가 없어요. 원문 링크만 남깁니다.")
        state = load_state()
        state[menu_key] = datetime.now(tz=KST).date().isoformat()
        save_state(state)
        return True, f"업로드 완료: {article.subject} ({len(images)}장)"


def _post_and_respond(respond, menu_key: str) -> None:
    try:
        _, msg = post_menu(menu_key)
    except Exception:
        log.exception("수동 호출 실패")
        msg = "오류가 났어요. 로그(bot.log)를 확인해 주세요."
    respond(msg)


@app.command("/lunch")
def lunch(ack, respond):
    ack()
    _post_and_respond(respond, "lunch")


@app.command("/dinner")
def dinner(ack, respond):
    ack()
    _post_and_respond(respond, "dinner")


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
    fh = logging.FileHandler(Path(__file__).with_name("bot.log"), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(fh)
    app.client.auth_test()
    log.info("Slack bot token OK")
    if AUTO_POST_ENABLED:
        threading.Thread(target=scheduler_loop, daemon=True).start()
    else:
        log.info("자동 포스팅 비활성화 (AUTO_POST_ENABLED=False)")
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    main()
