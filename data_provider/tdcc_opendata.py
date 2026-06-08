# -*- coding: utf-8 -*-
"""
TDCC (Taiwan Depository & Clearing Corporation) open data helpers.

Provides shareholding tier distribution (集保戶股權分散表) used as a Taiwan-market
proxy for A-share style chip distribution metrics.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

TDCC_SHAREHOLDING_URL = "https://openapi-t.tdcc.com.tw/v1/opendata/1-5"
_CACHE_LOCK = threading.Lock()
_CACHE: Dict[str, Any] = {"records": None, "fetched_at": 0.0}
_CACHE_TTL_SECONDS = 3600

# TDCC numeric tier ids (see TDCC 股權分散表说明)
_TIER_TOTAL = 17
_TIER_ADJUSTMENT = 16


def normalize_tdcc_stock_code(stock_code: str) -> str:
    """Normalize TW/TW-prefixed/suffixed codes to bare 4-6 digit TDCC code."""
    code = (stock_code or "").strip().upper()
    if code.endswith(".TWO"):
        code = code[:-4]
    elif code.endswith(".TW"):
        code = code[:-3]
    if code.startswith("TW") and code[2:].isdigit():
        return code[2:]
    return code


def _parse_percent(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _parse_int(value: Any) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def _extract_date(row: Dict[str, Any]) -> str:
    for key, value in row.items():
        if "資料日期" in str(key):
            raw = str(value or "").strip()
            if len(raw) == 8 and raw.isdigit():
                return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
            return raw
    return ""


def _fetch_tdcc_records(force_refresh: bool = False) -> List[Dict[str, Any]]:
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get("records")
        fetched_at = float(_CACHE.get("fetched_at") or 0.0)
        if cached is not None and not force_refresh and (now - fetched_at) < _CACHE_TTL_SECONDS:
            return cached

    last_error: Optional[Exception] = None
    for verify in (True, False):
        try:
            response = requests.get(
                TDCC_SHAREHOLDING_URL,
                timeout=120,
                headers={"User-Agent": "daily_stock_analysis/1.0"},
                verify=verify,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("TDCC response is not a list")
            with _CACHE_LOCK:
                _CACHE["records"] = payload
                _CACHE["fetched_at"] = now
            logger.info("[TDCC] 已加载股權分散表 %d 条记录 (verify=%s)", len(payload), verify)
            return payload
        except Exception as exc:
            last_error = exc
            if verify:
                logger.debug("[TDCC] HTTPS verify failed, retry without verify: %s", exc)
                continue
            break

    logger.warning("[TDCC] 加载股權分散表失败: %s", last_error)
    with _CACHE_LOCK:
        return _CACHE.get("records") or []


def get_shareholding_tiers(stock_code: str) -> Optional[Dict[str, Any]]:
    """
    Return latest TDCC shareholding tiers for one Taiwan security.

    Returns:
        {
            "code": "0050",
            "date": "2026-06-05",
            "tiers": [{"level": 1, "people": ..., "percent": ..., "shares": ...}, ...]
        }
    """
    bare_code = normalize_tdcc_stock_code(stock_code)
    if not bare_code:
        return None

    records = _fetch_tdcc_records()
    if not records:
        return None

    matched = [
        row
        for row in records
        if normalize_tdcc_stock_code(str(row.get("證券代號", ""))) == bare_code
    ]
    if not matched:
        logger.info("[TDCC] 未找到 %s 的股權分散表", bare_code)
        return None

    latest_date = max(_extract_date(row) for row in matched if _extract_date(row))
    if not latest_date:
        latest_rows = matched
    else:
        latest_rows = [row for row in matched if _extract_date(row) == latest_date]

    tiers: List[Dict[str, Any]] = []
    for row in latest_rows:
        level_raw = row.get("持股分級")
        try:
            level = int(str(level_raw).strip())
        except (TypeError, ValueError):
            continue
        tiers.append(
            {
                "level": level,
                "people": _parse_int(row.get("人數")),
                "percent": _parse_percent(row.get("占集保庫存數比例%")),
                "shares": _parse_int(row.get("股數")),
            }
        )

    tiers.sort(key=lambda item: item["level"])
    if not tiers:
        return None

    return {"code": bare_code, "date": latest_date, "tiers": tiers}


def compute_chip_metrics_from_tiers(
    tiers: List[Dict[str, Any]],
    *,
    current_price: float,
    avg_cost: float,
) -> Tuple[float, float, float, float, float, float, float, float]:
    """
    Map TDCC tiers + price stats into ChipDistribution-like metrics.

    concentration_* uses large-holder share percentages (decimal 0-1).
    """
    valid = [
        tier
        for tier in tiers
        if tier.get("level") not in (_TIER_ADJUSTMENT, _TIER_TOTAL)
    ]
    large_90 = sum(float(tier.get("percent") or 0.0) for tier in valid if tier.get("level", 0) >= 10)
    large_70 = sum(float(tier.get("percent") or 0.0) for tier in valid if tier.get("level", 0) >= 8)
    concentration_90 = max(0.0, min(1.0, large_90 / 100.0))
    concentration_70 = max(0.0, min(1.0, large_70 / 100.0))

    if avg_cost > 0 and current_price > 0:
        move = (current_price - avg_cost) / avg_cost
        profit_ratio = max(0.05, min(0.95, 0.5 + move * 0.5))
    else:
        profit_ratio = 0.5

    cost_90_low = avg_cost * 0.85 if avg_cost > 0 else 0.0
    cost_90_high = avg_cost * 1.15 if avg_cost > 0 else 0.0
    cost_70_low = avg_cost * 0.90 if avg_cost > 0 else 0.0
    cost_70_high = avg_cost * 1.10 if avg_cost > 0 else 0.0

    return (
        profit_ratio,
        avg_cost,
        cost_90_low,
        cost_90_high,
        concentration_90,
        cost_70_low,
        cost_70_high,
        concentration_70,
    )
