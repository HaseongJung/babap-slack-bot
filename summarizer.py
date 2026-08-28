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
                "prompt": f"다음 글을 3~5줄 이내로 핵심만 요약해:\n\n{text}",
                "stream": False,
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
