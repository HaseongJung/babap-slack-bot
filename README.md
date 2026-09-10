# 바른밥상 점심메뉴 Slack 봇

네이버 카페 '2판교 라이프'의 바른밥상 오늘 메뉴 글을 Slack 채널에 올린다.
`/lunch` = 점심 메뉴(3번째 사진), `/dinner` = 저녁 메뉴(4번째 사진) 수동 호출.
매일 영업일 11:00 KST에 점심만 자동 발송 (`config.py` `AUTO_POST_ENABLED=True`).

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

## Mac Studio 상시 구동 (Docker — 권장)

    docker compose up -d --build

로그: `docker compose logs -f`. 업데이트: 코드 수정 후 위 명령 재실행.
Socket Mode라 포트 매핑 불필요. `.env`는 compose가 자동 주입.

## Mac Studio 상시 구동 (launchd — Docker 없이)

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
| 자동 포스팅 사용 | `config.py` `AUTO_POST_ENABLED` | True |
| 자동 포스팅 시각 | `config.py` `POST_HOUR`/`POST_MINUTE` | 11:15 |
| 재시도 마감 | `config.py` `DEADLINE_HOUR` | 13 |
| 재시도 간격(분) | `config.py` `RETRY_MIN` | 10 |
| 재시도 최대 횟수 | `config.py` `RETRY_MAX` | 2 |
| 점심/저녁 이미지 순번 | `config.py` `MENU_IMAGE_INDEX` | lunch=2, dinner=3 (0-based) |
| 대상 식당 키워드 | `config.py` `KEYWORD` | 바른밥상 |

로그: 콘솔 + `bot.log`. 중복방지 상태: `state/state.json` (디렉터리 마운트).
