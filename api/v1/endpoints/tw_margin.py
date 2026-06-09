# -*- coding: utf-8 -*-
"""Taiwan margin / short-selling ranking API (融資融券 Top N screener).

Backed by the keyless TWSE MI_MARGN dataset via
``data_provider.twse_openapi.get_tw_margin_ranking``. Read-only, post-market
oriented (TWSE publishes settled figures after close).
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Query

from api.v1.errors import api_error

router = APIRouter()

_VALID_SORTS = ("margin_increase", "margin_decrease", "short_increase")


@router.get("/ranking")
def tw_margin_ranking(
    top_n: int = Query(50, ge=1, le=200, description="返回前 N 名"),
    sort_by: str = Query("margin_increase", description="margin_increase / margin_decrease / short_increase"),
) -> Dict[str, Any]:
    """TWSE 上市融資融券排行（默认按『融資增加』降序，单位：张）。

    每档含 融資/融券 餘額与当日增减、融資使用率、券资比。数据源不可用（盘后未
    结算或来源异常）时返回 ``success=False`` 的优雅降级负载，而非 5xx。
    """
    if sort_by not in _VALID_SORTS:
        raise api_error(
            400, "invalid_sort_by", f"sort_by 必须是 {list(_VALID_SORTS)} 之一"
        )

    from data_provider.twse_openapi import get_tw_margin_ranking as _ranking

    rows = _ranking(top_n, sort_by=sort_by)
    if rows is None:
        return {
            "success": False,
            "sort_by": sort_by,
            "count": 0,
            "ranking": [],
            "error": "TWSE 融資融券資料暫不可用（可能盤後尚未結算或來源異常）",
        }
    return {
        "success": True,
        "market": "tw",
        "unit": "張",
        "sort_by": sort_by,
        "count": len(rows),
        "ranking": rows,
    }
