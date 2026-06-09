# -*- coding: utf-8 -*-
"""
TPEx (上櫃 / OTC) securities list for the stock autocomplete index.

Source: FinMind ``TaiwanStockInfo`` (covers 上市 twse / 上櫃 tpex / 興櫃 emerging).
We take the ``tpex`` rows so 櫃買 stocks become searchable. No API key required
(FinMind works tokenless at a lower rate limit; ``FINMIND_TOKEN`` raises it).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

_FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"
_TIMEOUT = 40
# OTC codes are typically 4-6 alphanumerics (e.g. 6488, 5483, 00679B).
_TW_CODE_RE = re.compile(r"^[0-9A-Z]{4,6}$")


def _guess_asset_type(code: str, name: str) -> str:
    if code.startswith("00"):
        return "etf"
    lowered = name.lower()
    if "etf" in lowered or "指數" in name or "指数" in name:
        return "etf"
    return "stock"


def fetch_tpex_listed_securities(token: str = "") -> List[Dict[str, Any]]:
    """Fetch all 上櫃 (OTC) securities via FinMind TaiwanStockInfo.

    Returns rows shaped for ``build_tw_compressed_rows``:
        {"symbol": "6488", "name": "環球晶", "asset_type": "stock", "aliases": [...]}
    Empty list on any failure (caller decides how to degrade).
    """
    token = (token or os.getenv("FINMIND_TOKEN") or "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = requests.get(
            _FINMIND_API_URL,
            params={"dataset": "TaiwanStockInfo"},
            headers=headers,
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning("[TPEx stock list] FinMind TaiwanStockInfo 获取失败: %s", exc)
        return []

    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        logger.warning("[TPEx stock list] FinMind 返回空数据")
        return []

    by_code: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("type") != "tpex":
            continue
        code = str(row.get("stock_id") or "").strip().upper()
        name = str(row.get("stock_name") or "").strip()
        if not name or not _TW_CODE_RE.fullmatch(code):
            continue
        # TaiwanStockInfo may repeat a code across dates; first valid wins.
        if code in by_code:
            continue
        by_code[code] = {
            "symbol": code,
            "name": name,
            "asset_type": _guess_asset_type(code, name),
            "aliases": [code],
        }

    result = list(by_code.values())
    logger.info("[TPEx stock list] 取得上柜证券 %d 档", len(result))
    return result
