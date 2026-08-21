# 루트 conftest — 루트 디렉터리를 sys.path에 추가 + 테스트용 슬랙 env 스텁
import os

os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("SLACK_CHANNEL_ID", "C-TEST")
