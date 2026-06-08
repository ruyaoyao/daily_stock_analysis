# -*- coding: utf-8 -*-
"""Tests for the opt-in native Gemini client (header auth + rotation + retry)."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

if "newspaper" not in sys.modules:
    sys.modules["newspaper"] = MagicMock()

from src.llm import native_gemini as ng


def _cfg(keys=("k1",), enabled=True, base_url=None):
    return SimpleNamespace(
        native_gemini_enabled=enabled,
        gemini_api_keys=list(keys),
        native_gemini_base_url=base_url
        or "https://generativelanguage.googleapis.com/v1beta/models",
    )


def _resp(status=200, payload=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.json.return_value = payload if payload is not None else {}
    return r


def _ok_payload(text="pong"):
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2, "totalTokenCount": 5},
    }


class TestGating:
    def test_only_gemini_prefix_when_enabled(self):
        cfg = _cfg()
        assert ng.should_use_native_gemini("gemini/gemini-2.5-flash", cfg) is True
        assert ng.should_use_native_gemini("claude-sonnet-4-6", cfg) is False
        assert ng.should_use_native_gemini("gpt-5.5", cfg) is False

    def test_disabled_flag(self):
        assert ng.should_use_native_gemini("gemini/x", _cfg(enabled=False)) is False


class TestBodyTranslation:
    def test_system_and_messages_mapped(self):
        body = ng._build_gemini_body(
            [{"role": "system", "content": "S"}, {"role": "user", "content": "U"},
             {"role": "assistant", "content": "A"}],
            max_tokens=128, temperature=0.4,
        )
        assert body["systemInstruction"] == {"parts": [{"text": "S"}]}
        assert body["contents"] == [
            {"role": "user", "parts": [{"text": "U"}]},
            {"role": "model", "parts": [{"text": "A"}]},
        ]
        assert body["generationConfig"] == {"maxOutputTokens": 128, "temperature": 0.4}


class TestCompletion:
    def test_uses_header_auth_not_query_param(self):
        seen = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            seen["url"] = url
            seen["headers"] = headers
            return _resp(payload=_ok_payload())

        with patch("src.llm.native_gemini.requests.post", side_effect=fake_post):
            ng.native_gemini_completion("gemini/gemini-2.5-flash", {"messages": [{"role": "user", "content": "hi"}]}, config=_cfg())
        assert seen["headers"]["x-goog-api-key"] == "k1"
        assert "key=" not in seen["url"]
        assert seen["url"].endswith("/gemini-2.5-flash:generateContent")

    def test_non_stream_shape(self):
        with patch("src.llm.native_gemini.requests.post", return_value=_resp(payload=_ok_payload("hello"))):
            out = ng.native_gemini_completion("gemini/m", {"messages": [{"role": "user", "content": "x"}]}, config=_cfg())
        assert out["choices"][0]["message"]["content"] == "hello"
        assert out["usage"]["total_tokens"] == 5

    def test_stream_shape_is_single_chunk_list(self):
        with patch("src.llm.native_gemini.requests.post", return_value=_resp(payload=_ok_payload("hi"))):
            out = ng.native_gemini_completion("gemini/m", {"messages": [{"role": "user", "content": "x"}], "stream": True}, config=_cfg())
        assert isinstance(out, list) and out[0]["choices"][0]["delta"]["content"] == "hi"

    def test_custom_base_url(self):
        seen = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            seen["url"] = url
            return _resp(payload=_ok_payload())

        with patch("src.llm.native_gemini.requests.post", side_effect=fake_post):
            ng.native_gemini_completion("gemini/m", {"messages": [{"role": "user", "content": "x"}]},
                                        config=_cfg(base_url="https://gw.example/v1beta/models"))
        assert seen["url"].startswith("https://gw.example/v1beta/models/m:")

    def test_no_keys_raises(self):
        with pytest.raises(RuntimeError, match="no GEMINI_API_KEY"):
            ng.native_gemini_completion("gemini/m", {"messages": []}, config=_cfg(keys=()))

    def test_retries_then_succeeds(self):
        responses = [_resp(status=429, text="rate"), _resp(payload=_ok_payload("ok"))]
        with patch("src.llm.native_gemini.requests.post", side_effect=responses), \
             patch("src.llm.native_gemini.time.sleep"):
            out = ng.native_gemini_completion("gemini/m", {"messages": [{"role": "user", "content": "x"}]}, config=_cfg())
        assert out["choices"][0]["message"]["content"] == "ok"

    def test_fails_over_to_second_key_on_auth_error(self):
        # First key 401 (non-retryable -> next key), second key 200.
        responses = [_resp(status=401, text="bad key"), _resp(payload=_ok_payload("ok2"))]
        with patch("src.llm.native_gemini.requests.post", side_effect=responses):
            out = ng.native_gemini_completion("gemini/m", {"messages": [{"role": "user", "content": "x"}]}, config=_cfg(keys=("k1", "k2")))
        assert out["choices"][0]["message"]["content"] == "ok2"

    def test_all_keys_fail_raises(self):
        with patch("src.llm.native_gemini.requests.post", return_value=_resp(status=403, text="denied")), \
             patch("src.llm.native_gemini.time.sleep"):
            with pytest.raises(RuntimeError, match="failed across 2 key"):
                ng.native_gemini_completion("gemini/m", {"messages": [{"role": "user", "content": "x"}]}, config=_cfg(keys=("k1", "k2")))


class TestAnalyzerConsumesNativeOutput:
    """The analyzer's extractors must read native payloads unchanged."""

    def test_extractors_read_native_shapes(self):
        from src.analyzer import GeminiAnalyzer
        inst = GeminiAnalyzer.__new__(GeminiAnalyzer)  # avoid heavy __init__
        non_stream = {"choices": [{"message": {"role": "assistant", "content": "abc"}}],
                      "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        assert inst._extract_completion_text(non_stream) == "abc"
        assert inst._normalize_usage(non_stream["usage"])["total_tokens"] == 2
        # streaming one-chunk list
        chunk = [{"choices": [{"delta": {"content": "abc"}}], "usage": {"total_tokens": 2}}]
        text, usage = inst._consume_litellm_stream(chunk, model="gemini/m")
        assert text == "abc" and usage["total_tokens"] == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
