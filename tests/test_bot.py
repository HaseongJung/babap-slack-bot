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
