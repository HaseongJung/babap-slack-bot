"""바른밥상 점심메뉴 Slack 봇 — Socket Mode 단일 상시 프로세스."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime, time as dtime, timedelta

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import menu
import summarizer
from config import (
    AUTO_POST_ENABLED,
    AUTO_SOURCES,
    DEADLINE_HOUR,
    KST,
    KR_HOLIDAYS,
    POST_HOUR,
    POST_MINUTE,
    RETRY_MAX,
    RETRY_MIN,
    SLACK_APP_TOKEN,
    SLACK_BOT_TOKEN,
    SLACK_CHANNEL_ID,
    STATE_PATH,
    setup_logging,
)

app = App(token=SLACK_BOT_TOKEN, token_verification_enabled=False)
CHANNEL = SLACK_CHANNEL_ID
log = logging.getLogger("lunchbot")

_post_lock = threading.Lock()


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("state.json 읽기 실패, 빈 상태로 시작")
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(exist_ok=True)
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
    """다음 자동 포스팅 목표 시각. 오늘 AUTO_SOURCES 전부 끝났거나 휴일이면 다음 영업일 11시."""
    today = now.date()
    all_done = all(state.get(f"{src}_lunch") == today.isoformat() for src in AUTO_SOURCES)
    done = all_done or now.hour >= DEADLINE_HOUR
    if done or not is_business_day(today):
        return datetime.combine(next_business_day(today), dtime(POST_HOUR, POST_MINUTE), tzinfo=KST)
    return max(datetime.combine(today, dtime(POST_HOUR, POST_MINUTE), tzinfo=KST), now)


def next_after(ok: bool, now: datetime, fails: int = 0) -> datetime:
    """포스팅 시도 1회 후의 다음 시각. 재시도 남음이면 10분 뒤, 아니면 다음 영업일 11시.

    fails: 오늘 연속 실패 횟수(방금 실패 포함). RETRY_MAX 초과면 포기.
    """
    if not ok and now.hour < DEADLINE_HOUR and fails <= RETRY_MAX:
        return now + timedelta(minutes=RETRY_MIN)
    return datetime.combine(next_business_day(now.date()), dtime(POST_HOUR, POST_MINUTE), tzinfo=KST)


def post_menu(source: str = "barun", menu_key: str = "lunch") -> tuple[bool, str]:
    """수집해서 채널에 올리고 state를 갱신한다. (ok, 사용자용 메시지) 반환.

    수동 호출 기준: 이미 보냈어도 다시 보내준다 (state는 자동 포스팅용 기록).
    """
    with _post_lock:
        result = menu.collect(source, menu_key)
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
        state[f"{source}_{menu_key}"] = datetime.now(tz=KST).date().isoformat()
        save_state(state)
        return True, f"업로드 완료: {article.subject} ({len(images)}장)"


def _post_and_respond(respond, source: str, menu_key: str) -> None:
    try:
        _, msg = post_menu(source, menu_key)
    except Exception:
        log.exception("수동 호출 실패")
        msg = "오류가 났어요. 로그(bot.log)를 확인해 주세요."
    respond(msg)


@app.command("/lunch")
def lunch(ack, respond):
    ack()
    _post_and_respond(respond, "barun", "lunch")


@app.command("/dinner")
def dinner(ack, respond):
    ack()
    _post_and_respond(respond, "barun", "dinner")


@app.command("/lunch2")
def lunch2(ack, respond):
    ack()
    _post_and_respond(respond, "jeonggyeoun", "lunch")


@app.event("message")
def handle_message(event, client):
    """채널 메시지에 URL이 포함되면 Ollama로 요약해 thread reply."""
    if event.get("bot_id"):
        return
    text = event.get("text", "")
    if not text:
        return

    channel = event["channel"]
    thread_ts = event["ts"]

    def _summarize_and_reply():
        result = summarizer.handle_url_message(text)
        if result is None:
            return
        url, summary = result
        try:
            client.chat_postMessage(
                channel=channel,
                text=f"📰 *요약* (<{url}|원문>)\n\n{summary}",
                thread_ts=thread_ts,
            )
        except Exception:
            log.exception("요약 reply 실패")

    threading.Thread(target=_summarize_and_reply, daemon=True).start()


def scheduler_loop() -> None:
    next_run = next_post_time(load_state(), datetime.now(tz=KST))
    fails = {src: 0 for src in AUTO_SOURCES}
    log.info("스케줄러 시작, 다음 실행: %s", next_run.isoformat())
    while True:
        now = datetime.now(tz=KST)
        if now < next_run:
            time.sleep(min((next_run - now).total_seconds(), 60))
            continue
        today_iso = now.date().isoformat()
        state = load_state()
        pending = [src for src in AUTO_SOURCES if state.get(f"{src}_lunch") != today_iso]
        if not pending or not is_business_day(now.date()):
            log.info("오늘 자동 포스팅 대상 없음 (이미 보냈거나 휴일)")
            next_run = datetime.combine(
                next_business_day(now.date()), dtime(POST_HOUR, POST_MINUTE), tzinfo=KST
            )
            fails = {src: 0 for src in AUTO_SOURCES}
            continue
        candidates = []
        for src in pending:
            log.info("자동 포스팅 시도: %s", src)
            try:
                ok, msg = post_menu(src, "lunch")
                log.info("%s", msg)
            except Exception:
                log.exception("자동 포스팅 실패: %s", src)
                ok = False
            fails[src] = 0 if ok else fails[src] + 1
            if not ok:
                candidates.append(next_after(ok, datetime.now(tz=KST), fails[src]))
        finished = datetime.now(tz=KST)
        if candidates:
            next_run = min(candidates)
            if next_run.date() != finished.date():
                fails = {src: 0 for src in AUTO_SOURCES}
        else:
            next_run = datetime.combine(
                next_business_day(finished.date()), dtime(POST_HOUR, POST_MINUTE), tzinfo=KST
            )
            fails = {src: 0 for src in AUTO_SOURCES}


def main() -> None:
    setup_logging()
    app.client.auth_test()
    log.info("Slack bot token OK")
    if AUTO_POST_ENABLED:
        threading.Thread(target=scheduler_loop, daemon=True).start()
    else:
        log.info("자동 포스팅 비활성화 (AUTO_POST_ENABLED=False)")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()


if __name__ == "__main__":
    main()
