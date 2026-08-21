import json
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
