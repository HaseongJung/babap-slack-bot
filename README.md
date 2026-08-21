# 바른밥상 점심메뉴 Slack 봇

네이버 카페 '2판교 라이프'의 바른밥상 오늘 메뉴 글을 Slack 채널에 올린다.
`/lunch` = 점심 메뉴(3번째 사진), `/dinner` = 저녁 메뉴(4번째 사진) 수동 호출.
자동 포스팅 로직은 보존되어 있으나 현재 비활성 (`bot.py` `AUTO_POST_ENABLED=False`로 켤 수 있고, 켜면 매일 11:00 KST 점심만 발송).

## 실행 (Windows 테스트 / Mac Studio 동일)

    uv sync
    cp .env.example .env   # 값 채우기
    uv run python bot.py

## 수집만 단독 확인 (Slack 불필요)

    uv run python menu.py

## Slack 앱 설정

1. [api.slack.com/apps](https://api.slack.com/apps)에서 새 앱 생성
2. Socket Mode 활성화 → App-Level Token 생성 (`connections:write` 스코프) = `SLACK_APP_TOKEN`
3. Bot Token Scopes: `chat:write`, `files:write`, `commands`
4. Slash Command 생성: `/lunch`, `/dinner`
5. 봇을 대상 채널에 초대

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
| 자동 포스팅 사용 | `bot.py` `AUTO_POST_ENABLED` | False |
| 자동 포스팅 시각 | `bot.py` `POST_HOUR` | 11 |
| 재시도 마감 | `bot.py` `DEADLINE_HOUR` | 13 |
| 재시도 간격(분) | `bot.py` `RETRY_MIN` | 10 |
| 점심/저녁 이미지 순번 | `bot.py` `MENU_IMAGE_INDEX` | lunch=2, dinner=3 (0-based) |
| 대상 식당 키워드 | `menu.py` `KEYWORD` | 바른밥상 |

로그: 콘솔 + `bot.log`. 중복방지 상태: `state.json`.
