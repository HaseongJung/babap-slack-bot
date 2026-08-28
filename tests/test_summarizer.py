from unittest.mock import patch, MagicMock

import summarizer


class TestExtractUrls:
    def test_finds_https_url(self):
        assert summarizer.extract_urls("Check this https://example.com/article out") == [
            "https://example.com/article"
        ]

    def test_finds_http_url(self):
        assert summarizer.extract_urls("http://news.com/123") == ["http://news.com/123"]

    def test_finds_multiple_urls(self):
        text = "a https://a.com b http://b.com c"
        result = summarizer.extract_urls(text)
        assert result == ["https://a.com", "http://b.com"]

    def test_slack_mrkdwn_link(self):
        # Slack은 링크를 <url|표시텍스트> 형태로 전송
        text = "<https://www.digitalmarketer.co.kr/insights/article|digitalmarketer.co.kr/insights/article>"
        assert summarizer.extract_urls(text) == [
            "https://www.digitalmarketer.co.kr/insights/article"
        ]

    def test_slack_bare_link_in_angle_brackets(self):
        assert summarizer.extract_urls("<https://example.com/a>") == ["https://example.com/a"]

    def test_no_url_returns_empty(self):
        assert summarizer.extract_urls("no url here") == []

    def test_empty_string(self):
        assert summarizer.extract_urls("") == []

    def test_korean_text_with_url(self):
        text = "text https://news.naver.com/article/123 text"
        result = summarizer.extract_urls(text)
        assert len(result) == 1
        assert result[0].startswith("https://news.naver.com")


def _fake_response(text: str = "<html>...</html>") -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


class TestFetchContent:
    @patch("summarizer.trafilatura.extract", return_value="A" * 100)
    @patch("summarizer.requests.get")
    def test_returns_extracted_text(self, mock_get, mock_extract):
        mock_get.return_value = _fake_response()
        assert summarizer.fetch_content("https://example.com") == "A" * 100

    @patch("summarizer.trafilatura.extract", return_value="short")
    @patch("summarizer.requests.get")
    def test_returns_none_for_short_content(self, mock_get, mock_extract):
        mock_get.return_value = _fake_response()
        assert summarizer.fetch_content("https://example.com") is None

    @patch("summarizer.trafilatura.extract", return_value=None)
    @patch("summarizer.requests.get")
    def test_returns_none_when_trafilatura_fails(self, mock_get, mock_extract):
        mock_get.return_value = _fake_response()
        assert summarizer.fetch_content("https://example.com") is None

    @patch("summarizer.requests.get", side_effect=Exception("connection error"))
    def test_returns_none_on_fetch_failure(self, mock_get):
        assert summarizer.fetch_content("https://example.com") is None


class TestSummarize:
    @patch("summarizer.requests.post")
    def test_returns_summary(self, mock_post):
        mock_post.return_value = MagicMock()
        mock_post.return_value.json.return_value = {"response": "summary text"}
        result = summarizer.summarize("some text")
        assert result == "summary text"

    @patch("summarizer.requests.post", side_effect=Exception("ollama down"))
    def test_returns_none_on_failure(self, mock_post):
        assert summarizer.summarize("some text") is None

    def test_truncates_long_content(self):
        long_text = "x" * 5000
        with patch("summarizer.requests.post") as mock_post:
            mock_post.return_value = MagicMock()
            mock_post.return_value.json.return_value = {"response": "summary"}
            summarizer.summarize(long_text)
            call_args = mock_post.call_args
            prompt = call_args.kwargs["json"]["prompt"]
            assert len(prompt) < 6000


class TestHandleUrlMessage:
    @patch("summarizer.summarize", return_value="summary result")
    @patch("summarizer.fetch_content", return_value="long enough content. " * 20)
    def test_returns_url_and_summary(self, mock_fetch, mock_summarize):
        result = summarizer.handle_url_message("see https://example.com/article")
        assert result == ("https://example.com/article", "summary result")
        mock_fetch.assert_called_once_with("https://example.com/article")

    def test_returns_none_when_no_url(self):
        assert summarizer.handle_url_message("no url here") is None

    @patch("summarizer.fetch_content", return_value=None)
    def test_returns_none_when_fetch_fails(self, mock_fetch):
        assert summarizer.handle_url_message("https://example.com") is None

    @patch("summarizer.summarize", return_value=None)
    @patch("summarizer.fetch_content", return_value="long enough content. " * 20)
    def test_returns_none_when_summarize_fails(self, mock_fetch, mock_summarize):
        assert summarizer.handle_url_message("https://example.com") is None
