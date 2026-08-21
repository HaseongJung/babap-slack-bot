# 바른밥상 점심메뉴 Slack 봇 — 설계 문서

날짜: 2026-08-21
상태: 승인됨 (접근 방식 A)

## 목표

네이버 카페 "2판교 라이프"의 `Today 밥집 메뉴` 게시판에서 **판교이노베이션랩 "바른밥상"** 일일 점심메뉴 글을 수집하여, 회사 Slack 채널에:

1. **자동 포스팅** — 매일 오전 11:00 (KST)
2. **수동 호출** — `/점심` 슬래시 커맨드 입력 시 즉시 응답

## 검증된 사실 (2026-08-21 실측)

무인증(로그인 없이) HTTP 요청만으로 전 과정 수행 가능. 헤드리스 브라우저 불필요.
필수 헤더: `User-Agent`(브라우저) + `Referer: https://cafe.naver.com/`

| 용도 | 엔드포인트 |
|---|---|
| 글 목록 | `GET https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/30487307/menus/26/articles?page=1&pageSize=15&sortBy=TIME&viewType=L` |
| 글 본문 | `GET https://article.cafe.naver.com/gw/v4/cafes/30487307/articles/{articleId}?query=&menuId=26&boardType=L&useCafeId=true&requestFrom=A` |
| 이미지 | 본문 응답의 `result.article.contentHtml` 내 `<img src="https://cafeptthumb-phinf.pstatic.net/...">` URL, 직접 다운로드 가능 (200, image/png) |

- 카페 ID: 30487307, 게시판(menuId): 26
- 글 식별: `articleList[].item.articleId`, 제목 `subject`, 작성시각 `writeDateTimestamp`(ms epoch)
- 바른밥상 글은 평일 아침 10:00~10:30 사이 업로드됨
- 같은 게시판에 타 식당(송원식당, 정겨운맛풍경 등)도 올라오므로 제목에 `"바른밥상"` 포함 + 작성일이 **오늘(KST 기준)** 조건으로 필터링

## 아키텍처

Python 단일 상시 프로세스. Slack Bolt Socket Mode (공인 URL 불필요 → PC/Mac Studio 어디서든 실행 가능).

```
[네이버 카페 API] → menu.py (수집) → bot.py (스케줄러 + Slack 송신) → [Slack 채널]
                                          ↑ Slack Socket Mode (/점심 커맨드 수신)
```

## 구성

```
slack_bot/
├── bot.py            # 진입점: Bolt 앱, 스케줄러, Slack 업로드 (~150줄)
├── menu.py           # 카페 수집: 목록→본문→이미지 다운로드 (~60줄)
├── pyproject.toml    # uv 프로젝트 정의
├── .env              # SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_CHANNEL_ID
├── .env.example
└── state.json        # 중복 포스팅 방지용 last_posted_date (자동 생성)
```

- **런타임**: Python 3.12+, 가상환경/의존성 관리는 **uv** (`uv sync`로 설치)
- **의존성**: `slack-bolt`, `requests` — 이게 전부

## 상세 동작

### 자동 포스팅 (매일 11:00 KST)

1. `state.json`의 `last_posted_date`가 오늘이면 스킵 (재시작 중복 방지)
2. 목록 API → 제목에 "바른밥상" 포함 + 작성일이 오늘인 글 검색
3. 없으면 10분 간격 재시도, 13:00까지 → 실패 시 로그 남기고 종료
4. 있으면 본문 API → 이미지 URL 추출 → 임시 파일로 다운로드
5. Slack 채널에 메시지(제목+원문 링크) + 이미지 파일 업로드
6. `last_posted_date` 갱신

### 수동 호출 (`/점심`)

- 같은 수집 로직 즉시 실행
- 글이 아직 없으면 "아직 오늘 메뉴가 안 올라왔어요 (보통 10:00~10:30 업로드)" ephemeral 응답
- 수동 응답은 자동 포스팅 상태와 무관하게 항상 응답

### 이미지 처리

- `contentHtml`에서 정규식으로 `<img src="...">` URL 전부 추출 (당일 4장 기준)
- `?type=w1600` 파라미터 포함 원본 사용
- OS 임시 디렉터리에 다운로드 후 Slack `files_upload_v2`로 업로드, 후 임시 파일 삭제
- URL 링크만 보낼 경우 Slack 프리뷰가 안 뜰 수 있어 파일 업로드 방식 채택

## Slack 앱 설정 (구현 시 생성)

1. api.slack.com/apps → 새 앱 생성
2. Socket Mode 활성화 → App-Level Token (`connections:write`) = `SLACK_APP_TOKEN`
3. Bot Token Scopes: `chat:write`, `files:write`, `commands`
4. Slash Command: `/점심`
5. 봇을 대상 채널에 초대

## 에러 처리

- HTTP 요청 실패: 3회 재시도 후 로그
- 본문에 이미지 0개: "글은 올라왔는데 이미지가 없어요" + 원문 링크만 전송
- Slack 업로드 실패: 로그 + 재시도 루프에서 다음 시도에 재전송 (state 미갱신)
- 로그: 콘솔 + `bot.log` 파일 (logging 모듈)

## 배포

1. **Windows (테스트)**: `uv run python bot.py` — 콘솔에서 직접 실행
2. **Mac Studio (상시)**: launchd `~/Library/LaunchAgents/com.slackbot.lunch.plist`로 상시 구동. 로케일 무관하게 스케줄은 `Asia/Seoul` 타임존 명시 (zoneinfo)

코드는 플랫폼 무관 (경로는 `pathlib`, 임시파일은 `tempfile`).

## 테스트

- `uv run python menu.py` — 수집만 단독 실행: 오늘 글 ID/제목/이미지 URL 출력으로 스크래핑 검증 (Slack 토큰 불필요)
- `bot.py`는 실제 Slack 워크스페이스 테스트 채널에서 수동 커맨드로 검증

## 비목표 (YAGNI)

- 타 식당 지원 (필요시 제목 필터만 바꾸면 됨 — `menu.py` 상수)
- @멘션 응답 (슬래시 커맨드로 충분)
- 이미지 히스토리 저장, DB, 웹 대시보드
- 주말 포스팅 (주말엔 글 자체가 없음; 스케줄은 매일 돌지만 재시도 루프가 13:00 실패로 자연 종료)
