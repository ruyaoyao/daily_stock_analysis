# -*- coding: utf-8 -*-
"""
TWSE listed securities list (上市) for stock autocomplete index.

Data sources (no API key):
  - Company basic info: https://openapi.twse.com.tw/v1/opendata/t187ap03_L
  - Daily all securities: https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL
    (fills ETFs / other listed instruments not present in company basic info)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_USER_AGENT = "daily-stock-analysis/1.0"
_TIMEOUT = 30

_TWSE_COMPANY_BASIC_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
_TWSE_STOCK_DAY_ALL_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"

# Listed TW codes are typically 4-6 alphanumerics (e.g. 2330, 006208, 00625K).
_TW_CODE_RE = re.compile(r"^[0-9A-Z]{4,6}$")


def _get_json(url: str) -> Optional[Any]:
    try:
        response = requests.get(
            url,
            timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else None
    except Exception as exc:
        logger.warning("[TWSE stock list] fetch failed %s: %s", url, exc)
        return None


def _normalize_code(raw: Any) -> str:
    return str(raw or "").strip().upper()


def _guess_asset_type(code: str, name: str) -> str:
    """Heuristic: TW listed ETFs usually start with 00 and are not common stocks."""
    if code.startswith("00"):
        return "etf"
    lowered = name.lower()
    if "etf" in lowered or "指數" in name or "指数" in name:
        return "etf"
    return "stock"


def fetch_twse_listed_securities() -> List[Dict[str, Any]]:
    """
    Fetch all TWSE-listed securities (上市), merging company stocks and daily universe.

    Returns rows shaped for ``build_tw_compressed_rows``:
        {"symbol": "2344", "name": "華邦電", "asset_type": "stock", "aliases": [...]}
    """
    by_code: Dict[str, Dict[str, Any]] = {}

    company_rows = _get_json(_TWSE_COMPANY_BASIC_URL) or []
    for row in company_rows:
        code = _normalize_code(row.get("公司代號"))
        if not _TW_CODE_RE.fullmatch(code):
            continue
        short_name = str(row.get("公司簡稱") or row.get("公司名稱") or "").strip()
        if not short_name:
            continue
        aliases: List[str] = [code]
        english = str(row.get("英文簡稱") or "").strip()
        if english and english not in aliases:
            aliases.append(english)
        full_name = str(row.get("公司名稱") or "").strip()
        if full_name and full_name not in aliases and full_name != short_name:
            aliases.append(full_name)
        by_code[code] = {
            "symbol": code,
            "name": short_name,
            "asset_type": "stock",
            "aliases": aliases,
        }

    day_rows = _get_json(_TWSE_STOCK_DAY_ALL_URL) or []
    for row in day_rows:
        code = _normalize_code(row.get("Code"))
        if not _TW_CODE_RE.fullmatch(code):
            continue
        name = str(row.get("Name") or "").strip()
        if not name:
            continue
        if code in by_code:
            continue
        by_code[code] = {
            "symbol": code,
            "name": name,
            "asset_type": _guess_asset_type(code, name),
            "aliases": [code],
        }

    result = sorted(by_code.values(), key=lambda item: item["symbol"])
    logger.info(
        "[TWSE stock list] loaded %d listed securities (%d companies + %d supplemental)",
        len(result),
        len(company_rows),
        max(0, len(result) - len(company_rows)),
    )
    return result
