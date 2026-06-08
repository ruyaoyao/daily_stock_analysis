# -*- coding: utf-8 -*-
"""Native Google Gemini client (raw REST, ``x-goog-api-key`` header).

Optional, opt-in alternative to LiteLLM's ``gemini/`` provider for Google AI
Studio. It calls the native ``generativelanguage`` ``generateContent`` endpoint
and authenticates with the official ``x-goog-api-key`` HEADER — the method
Google documents and which newer AI Studio key formats expect — instead of the
``?key=`` query parameter that LiteLLM's ``gemini/`` provider uses. Adds
multi-key round-robin plus per-key retry/backoff and optional base_url override
for a gateway.

The approach is adapted from the proven, SDK-free Gemini client in the
``quant-trading`` project. It is disabled by default (``NATIVE_GEMINI_ENABLED``)
and returns LiteLLM-shaped payloads so the analyzer consumes it unchanged:
- non-stream: ``{"choices": [{"message": {"content": text}}], "usage": {...}}``
- stream:    ``[{"choices": [{"delta": {"content": text}}], "usage": {...}}]``
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_NATIVE_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

_MAX_RETRIES = 3
_RETRY_BACKOFF_SEC = 1.5
_TIMEOUT_SEC = 60
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Round-robin starting offset shared across calls so load spreads over keys.
_rr_lock = threading.Lock()
_rr_index = 0


def should_use_native_gemini(model: str, config: Any) -> bool:
    """Whether this call should be routed through the native Gemini client.

    Only intercepts Google AI Studio models (``gemini/<model>``) when the
    feature flag is enabled; everything else stays on LiteLLM.
    """
    if not getattr(config, "native_gemini_enabled", False):
        return False
    return bool(model) and model.strip().lower().startswith("gemini/")


def _ordered_keys(config: Any) -> List[str]:
    """Return the configured Gemini keys rotated by a per-call offset."""
    global _rr_index
    keys = [k for k in (getattr(config, "gemini_api_keys", None) or []) if k]
    if not keys:
        return []
    with _rr_lock:
        start = _rr_index % len(keys)
        _rr_index = (_rr_index + 1) % len(keys)
    return keys[start:] + keys[:start]


def _flatten_content(content: Any) -> str:
    """Flatten OpenAI-style string or content-block lists into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _build_gemini_body(
    messages: Any,
    max_tokens: Optional[int],
    temperature: Optional[float],
) -> Dict[str, Any]:
    """Translate OpenAI-shaped messages into a Gemini ``generateContent`` body."""
    system_parts: List[str] = []
    contents: List[Dict[str, Any]] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        text = _flatten_content(msg.get("content")).strip()
        if not text:
            continue
        role = msg.get("role")
        if role == "system":
            system_parts.append(text)
        else:
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": text}]})

    body: Dict[str, Any] = {"contents": contents or [{"role": "user", "parts": [{"text": ""}]}]}
    if system_parts:
        body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

    generation_config: Dict[str, Any] = {}
    if max_tokens:
        generation_config["maxOutputTokens"] = int(max_tokens)
    if temperature is not None:
        try:
            generation_config["temperature"] = float(temperature)
        except (TypeError, ValueError):
            pass
    if generation_config:
        body["generationConfig"] = generation_config
    return body


def _extract_text(data: Dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
    return "".join(
        p.get("text", "") for p in parts if isinstance(p, dict)
    ).strip()


def _usage(data: Dict[str, Any]) -> Dict[str, int]:
    meta = data.get("usageMetadata") or {}
    prompt = int(meta.get("promptTokenCount") or 0)
    completion = int(meta.get("candidatesTokenCount") or 0)
    total = int(meta.get("totalTokenCount") or (prompt + completion))
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def native_gemini_completion(model: str, call_kwargs: Dict[str, Any], *, config: Any) -> Any:
    """Run a Gemini completion natively; return a LiteLLM-shaped payload.

    Raises ``RuntimeError`` when no key is configured or every key fails, so the
    analyzer's existing model-fallback loop can move on to the next model.
    """
    keys = _ordered_keys(config)
    if not keys:
        raise RuntimeError("NATIVE_GEMINI_ENABLED is set but no GEMINI_API_KEY is configured")

    model_id = model.split("/", 1)[1] if "/" in model else model
    base_url = (
        getattr(config, "native_gemini_base_url", None) or DEFAULT_NATIVE_GEMINI_BASE_URL
    ).rstrip("/")
    url = f"{base_url}/{model_id}:generateContent"

    body = _build_gemini_body(
        call_kwargs.get("messages"),
        call_kwargs.get("max_tokens"),
        call_kwargs.get("temperature"),
    )
    stream = bool(call_kwargs.get("stream"))

    last_error: Optional[str] = None
    for key in keys:
        for attempt in range(_MAX_RETRIES):
            try:
                resp = requests.post(
                    url,
                    json=body,
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    timeout=_TIMEOUT_SEC,
                )
            except requests.RequestException as exc:
                last_error = f"network error: {exc}"
                time.sleep(_RETRY_BACKOFF_SEC * (attempt + 1))
                continue

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError as exc:
                    last_error = f"invalid JSON: {exc}"
                    break  # non-retryable for this key -> next key
                text = _extract_text(data)
                if not text:
                    last_error = "empty Gemini response"
                    break
                usage = _usage(data)
                if stream:
                    return [{"choices": [{"delta": {"content": text}}], "usage": usage}]
                return {
                    "choices": [{"message": {"role": "assistant", "content": text}}],
                    "usage": usage,
                }

            detail = (resp.text or "")[:200]
            last_error = f"HTTP {resp.status_code}: {detail}"
            if resp.status_code in _RETRYABLE_STATUS:
                logger.warning(
                    "[native-gemini] %s transient %s (attempt %s/%s), retrying",
                    model_id, resp.status_code, attempt + 1, _MAX_RETRIES,
                )
                time.sleep(_RETRY_BACKOFF_SEC * (attempt + 1))
                continue
            # Non-retryable (e.g. 400/401/403/404): try the next key.
            break

    raise RuntimeError(
        f"native Gemini call failed across {len(keys)} key(s): {last_error}"
    )
