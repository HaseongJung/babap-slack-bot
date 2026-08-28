"""URL 자동 요약 — curl_cffi로 본문 수집 + Ollama로 요약."""
from __future__ import annotations

import logging
import re

import trafilatura
from curl_cffi import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT

log = logging.getLogger("lunchbot")

URL_PATTERN = re.compile(r"https?://\S+")

# 요약에 사용할 최대 글자 수 (너무 길면 LLM 컨텍스트 낭비)
MAX_CONTENT_LENGTH = 3000


def extract_urls(text: str) -> list[str]:
    """메시지 텍스트에서 URL 목록을 반환."""
    return URL_PATTERN.findall(text)


def fetch_content(url: str) -> str | None:
    """URL에서 본문 텍스트를 추출. 실패하면 None."""
    try:
        resp = requests.get(url, impersonate="chrome", timeout=15)
        resp.raise_for_status()
    except Exception:
        log.warning("URL 수집 실패: %s", url, exc_info=True)
        return None

    text = trafilatura.extract(resp.text)
    if not text or len(text.strip()) < 50:
        return None
    return text


def summarize(text: str) -> str | None:
    """Ollama로 텍스트를 한국어 3~5줄 요약. 실패하면 None."""
    if len(text) > MAX_CONTENT_LENGTH:
        text = text[:MAX_CONTENT_LENGTH] + "\n...(생략)"

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": (
                    f"다음 웹페이지 본문을 요약해. "
                    f"네비게이션·광고·푸터·사이드바 등 본문이 아닌 내용은 무시하고 "
                    f"핵심 기사/글 내용만 다루며, 두 가지 섹션으로 나눌 출력해.\n\n"
                    f"[3줄 요약]\n"
                    f"핵심을 정확히 3문장으로 요약해. 각 줄은 관련 이모지로 시작해.\n\n"
                    f"[상세 요약]\n"
                    f"조금 더 자세히 5줄 이내로 작성해."
                    f"제목은 [대괄호]로 감싸 첫 항목에 포함해.\n\n"f"--- 예시 ---\n"f"[3줄 요약]\n"f"🚀 삼성전자가 2026년 AI 반도체 출하량을 40% 확대한다고 발표했습니다.\n"f"📈 HBM4 생산을 1만 장으로 늘뢰 수익성을 유지할 것입니다.\n"f"🔔 엔비디아와의 경쟁 심화 소에서 자체 AI 칙개발도 병행합니다.\n\n"f"[상세 요약]\n"f"[삼성전자, AI 반도체 출하량 40% 확대]\n"f"삼성전자가 2026년 하반기 HBM4 및 AI 전용 반도체 생산량을 40% 확대한다고 27일 박혀다. 이에 따라 월 1만 장로 늘뢰 간획입니다."
                ),
                "stream": False,
                "keep_alive": "10m",
            },
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["response"].strip()
    except Exception:
        log.warning("Ollama 요약 실패", exc_info=True)
        return None


def handle_url_message(text: str) -> tuple[str, str] | None:
    """메시지에서 URL을 추출해 첫 번째 URL의 요약을 반환.

    Returns:
        (url, summary) 튜플 또는 URL 없음/실패 시 None
    """
    urls = extract_urls(text)
    if not urls:
        return None

    url = urls[0]
    content = fetch_content(url)
    if content is None:
        return None

    summary = summarize(content)
    if summary is None:
        return None

    return url, summary
