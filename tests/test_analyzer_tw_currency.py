# -*- coding: utf-8 -*-
"""Per-stock prompt: Taiwan prices must be labelled NT$ (新台幣); other markets keep 「元」.

Avoids ambiguity when a TW report is read alongside A-share (both used 「元」 before).
"""

from src.analyzer import GeminiAnalyzer


def _ctx(code, name):
    return {
        "code": code,
        "stock_name": name,
        "date": "2026-06-15",
        "today": {"close": 141.5, "open": 134.0, "high": 142.0, "low": 133.5,
                  "pct_chg": 5.99, "volume": 325874, "amount": 45737144000,
                  "ma5": 135.2, "ma10": 132.8, "ma20": 130.1},
        "realtime": {"price": 141.5, "volume_ratio": 2.3, "turnover_rate": 2.6},
    }


def test_tw_stock_prices_labelled_ntd():
    a = GeminiAnalyzer()
    p = a._format_prompt(_ctx("tw2303", "聯電"), "聯電", None)
    assert "元（NT$）" in p                      # price rows carry NT$
    assert "新台幣（NT$）" in p                   # currency note present
    assert "| 141.5 元（NT$） |" in p             # close price row
    assert "| 当前价格 | 141.5 元（NT$） |" in p   # realtime row


def test_non_tw_stock_keeps_yuan():
    a = GeminiAnalyzer()
    p = a._format_prompt(_ctx("600519", "贵州茅台"), "贵州茅台", None)
    assert "元（NT$）" not in p
    assert "新台幣" not in p
    assert "| 141.5 元 |" in p
