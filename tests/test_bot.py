import json
from datetime import datetime
from zoneinfo import ZoneInfo

import bot

KST = ZoneInfo("Asia/Seoul")


def dt(h, m=0):
    return datetime(2026, 8, 21, h, m, tzinfo=KST)  # 금요일


NEXT_11 = datetime(2026, 8, 24, 11, 0, tzinfo=KST)  # 주말 건너뛴 다음 월요일


def test_next_when_already_posted_today():
    assert bot.next_post_time({"lunch": "2026-08-21"}, dt(9)) == NEXT_11


def test_next_when_not_posted_before_11():
    assert bot.next_post_time({}, dt(9)) == dt(11)


def test_next_when_missed_but_before_deadline():
    assert bot.next_post_time({}, dt(11, 20)) == dt(11, 20)


def test_next_when_past_deadline():
    assert bot.next_post_time({}, dt(13, 30)) == NEXT_11


def test_retry_10min_after_failed_attempt():
    assert bot.next_after(False, {}, dt(11, 0)) == dt(11, 10)


def test_give_up_after_deadline():
    assert bot.next_after(False, {}, dt(13, 0)) == NEXT_11


def test_next_day_after_success():
    state = {"lunch": "2026-08-21"}
    assert bot.next_after(True, state, dt(11, 0)) == NEXT_11


def test_skips_weekend_to_monday():
    saturday = datetime(2026, 8, 22, 9, tzinfo=KST)
    assert bot.next_post_time({}, saturday) == NEXT_11


def test_skips_holiday_run():
    """2026-08-15(토) 광복절 + 08-17(월) 대체공휴일 → 다음 영업일은 08-18(화)."""
    friday_after_deadline = datetime(2026, 8, 14, 13, 30, tzinfo=KST)
    assert bot.next_post_time({}, friday_after_deadline) == datetime(2026, 8, 18, 11, 0, tzinfo=KST)


def test_skips_lunar_new_year_run():
    """2026 설날 연휴 02-16~18(월~수) → 02-13(금) 이후 다음 영업일은 02-19(목)."""
    friday_after_deadline = datetime(2026, 2, 13, 13, 30, tzinfo=KST)
    assert bot.next_post_time({}, friday_after_deadline) == datetime(2026, 2, 19, 11, 0, tzinfo=KST)


def test_state_roundtrip(tmp_path, monkeypatch):
    p = tmp_path / "state.json"
    monkeypatch.setattr(bot, "STATE_PATH", p)
    assert bot.load_state() == {}
    bot.save_state({"lunch": "2026-08-21"})
    assert bot.load_state() == {"lunch": "2026-08-21"}


def test_post_menu_uploads_and_saves_state(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(bot.app.client, "chat_postMessage", lambda **kw: calls.append(("msg", kw)) or {})
    monkeypatch.setattr(bot.app.client, "files_upload_v2", lambda **kw: calls.append(("file", kw)) or {})
    img = tmp_path / "menu.png"
    img.write_bytes(b"x")
    seen = []

    def fake_collect(image_index=None):
        seen.append(image_index)
        return (bot.menu.Article(5298, "오늘의 메뉴"), [img])

    monkeypatch.setattr(bot.menu, "collect", fake_collect)
    monkeypatch.setattr(bot, "STATE_PATH", tmp_path / "state.json")

    ok, msg = bot.post_menu("lunch")

    assert ok is True
    assert seen == [2]  # 점심 = 3번째 이미지(0-based 2)
    assert calls[0][0] == "msg" and "오늘의 메뉴" in calls[0][1]["text"]
    assert calls[1] == ("file", {"channel": "C-TEST", "file": str(img), "title": "오늘의 메뉴"})
    assert not img.exists()  # 임시파일 삭제 확인
    expected_date = datetime.now(tz=KST).date().isoformat()
    assert json.loads((tmp_path / "state.json").read_text(encoding="utf-8")) == {
        "lunch": expected_date
    }


def test_post_menu_dinner_uses_fourth_image(monkeypatch, tmp_path):
    img = tmp_path / "menu.png"
    img.write_bytes(b"x")
    seen = []
    monkeypatch.setattr(
        bot.menu, "collect", lambda image_index=None: (seen.append(image_index), (bot.menu.Article(1, "s"), [img]))[1]
    )
    monkeypatch.setattr(bot.app.client, "chat_postMessage", lambda **kw: {})
    monkeypatch.setattr(bot.app.client, "files_upload_v2", lambda **kw: {})
    monkeypatch.setattr(bot, "STATE_PATH", tmp_path / "state.json")

    ok, _ = bot.post_menu("dinner")

    assert ok is True
    assert seen == [3]  # 저녁 = 4번째 이미지(0-based 3)


def test_post_menu_no_article_today(monkeypatch, tmp_path):
    monkeypatch.setattr(bot.menu, "collect", lambda image_index=None: None)
    monkeypatch.setattr(bot, "STATE_PATH", tmp_path / "state.json")
    ok, msg = bot.post_menu()
    assert ok is False
    assert "안 올라왔" in msg
    assert not (tmp_path / "state.json").exists()


def test_post_menu_zero_images_still_posts_link(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(bot.app.client, "chat_postMessage", lambda **kw: calls.append("msg") or {})
    monkeypatch.setattr(bot.app.client, "files_upload_v2", lambda **kw: calls.append("file") or {})
    monkeypatch.setattr(bot.menu, "collect", lambda image_index=None: (bot.menu.Article(5298, "오늘의 메뉴"), []))
    monkeypatch.setattr(bot, "STATE_PATH", tmp_path / "state.json")

    ok, msg = bot.post_menu()

    assert ok is True
    assert calls == ["msg", "msg"]  # 본문 메시지 + 이미지 없음 안내, 파일 업로드 없음
    assert (tmp_path / "state.json").exists()


def test_post_menu_resends_even_if_already_posted_today(monkeypatch, tmp_path):
    """수동 호출은 중복방지에 막히지 않고 항상 다시 보낸다."""
    calls = []
    collect_calls = [0]

    def fake_collect(image_index=None):
        collect_calls[0] += 1
        img = tmp_path / "menu.png"
        img.write_bytes(b"x")
        return (bot.menu.Article(5298, "오늘의 메뉴"), [img])

    monkeypatch.setattr(bot.app.client, "chat_postMessage", lambda **kw: calls.append("msg") or {})
    monkeypatch.setattr(bot.app.client, "files_upload_v2", lambda **kw: calls.append("file") or {})
    monkeypatch.setattr(bot, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(bot.menu, "collect", fake_collect)

    ok1, _ = bot.post_menu("lunch")
    ok2, msg2 = bot.post_menu("lunch")

    assert ok1 is True and ok2 is True
    assert collect_calls[0] == 2  # 두 번 다 수집 실행
    assert "완료" in msg2
    assert calls.count("msg") == 2 and calls.count("file") == 2


def test_load_state_returns_empty_on_corrupt_json(tmp_path, monkeypatch):
    corrupt = tmp_path / "state.json"
    corrupt.write_text("THIS IS NOT JSON{{{", encoding="utf-8")
    monkeypatch.setattr(bot, "STATE_PATH", corrupt)
    assert bot.load_state() == {}
