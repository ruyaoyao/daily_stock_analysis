# -*- coding: utf-8 -*-
"""Tests for the market-review 國際情勢/宏觀背景 block.

Source: structured risk indicators (SOX/DXY/VIX/US10Y) via yfinance, injected
into market reviews only (per-stock analysis unaffected). All fail-safe: a
single indicator or the whole block failing must not break the review.
"""

import sys
from unittest.mock import MagicMock, patch

from data_provider.base import DataFetcherManager
from src.market_analyzer import MarketAnalyzer, MarketOverview


# --- YfinanceFetcher.get_global_macro_indicators ---

def test_yf_global_macro_returns_four_indicators_with_bilingual_names():
    from data_provider.yfinance_fetcher import YfinanceFetcher
    f = YfinanceFetcher()

    def _echo(yf, yf_code, name, code):
        return {"code": code, "name": name, "current": 100.0, "change_pct": 1.5}

    with patch.dict(sys.modules, {"yfinance": MagicMock()}), \
         patch.object(f, "_fetch_yf_ticker_data", side_effect=_echo):
        res = f.get_global_macro_indicators()
    assert res is not None and len(res) == 4
    codes = {r["code"] for r in res}
    assert codes == {"SOX", "DXY", "VIX", "US10Y"}
    assert all(r.get("zh_name") and r.get("en_name") for r in res)


def test_yf_global_macro_skips_failed_indicator():
    from data_provider.yfinance_fetcher import YfinanceFetcher
    f = YfinanceFetcher()
    calls = {"n": 0}

    def _side_effect(yf, yf_code, name, code):
        calls["n"] += 1
        return None if calls["n"] == 1 else {"current": 50.0, "change_pct": -0.3}

    with patch.dict(sys.modules, {"yfinance": MagicMock()}), \
         patch.object(f, "_fetch_yf_ticker_data", side_effect=_side_effect):
        res = f.get_global_macro_indicators()
    assert res is not None and len(res) == 3   # first skipped, other three kept


def test_yf_global_macro_none_when_all_fail():
    from data_provider.yfinance_fetcher import YfinanceFetcher
    f = YfinanceFetcher()
    with patch.dict(sys.modules, {"yfinance": MagicMock()}), \
         patch.object(f, "_fetch_yf_ticker_data", return_value=None):
        assert f.get_global_macro_indicators() is None


# --- DataFetcherManager.get_global_macro_indicators delegation ---

def test_manager_global_macro_delegates_to_capable_fetcher():
    mgr = DataFetcherManager()
    fake = MagicMock()
    fake.name = "fake-yf"
    fake.get_global_macro_indicators.return_value = [{"code": "SOX", "current": 1.0}]
    mgr._fetchers = [fake]
    assert mgr.get_global_macro_indicators() == [{"code": "SOX", "current": 1.0}]


def test_manager_global_macro_empty_when_no_capable_fetcher():
    mgr = DataFetcherManager()
    incapable = object()   # has no get_global_macro_indicators attribute
    mgr._fetchers = [incapable]
    assert mgr.get_global_macro_indicators() == []


# --- MarketAnalyzer._get_global_macro (fail-safe) ---

def test_get_global_macro_populates_overview():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-11")
    with patch.object(a.data_manager, "get_global_macro_indicators",
                      return_value=[{"code": "SOX", "zh_name": "費城半導體指數",
                                     "en_name": "SOX", "current": 5800.0, "change_pct": 1.2}]):
        a._get_global_macro(ov)
    assert ov.global_macro and ov.global_macro[0]["code"] == "SOX"


def test_get_global_macro_failsafe_on_exception():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-11")
    with patch.object(a.data_manager, "get_global_macro_indicators",
                      side_effect=Exception("network down")):
        a._get_global_macro(ov)   # must not raise
    assert ov.global_macro == []


# --- MarketAnalyzer._build_global_macro_block rendering ---

_MACRO = [
    {"code": "SOX", "zh_name": "費城半導體指數", "en_name": "Philadelphia Semiconductor (SOX)",
     "current": 5800.12, "change_pct": 1.23},
    {"code": "VIX", "zh_name": "波動率指數", "en_name": "Volatility Index (VIX)",
     "current": 14.5, "change_pct": -2.0},
]


def test_build_global_macro_block_zh():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-11", global_macro=_MACRO)
    with patch.object(a, "_get_review_language", return_value="zh"):
        block = a._build_global_macro_block(ov)
    assert "國際情勢（宏觀背景）" in block
    assert "費城半導體指數: 5,800.12 (↑1.23%)" in block
    assert "波動率指數: 14.50 (↓2.00%)" in block
    assert "風險偏好定調背景" in block


def test_build_global_macro_block_en():
    a = MarketAnalyzer(region="us")
    ov = MarketOverview(date="2026-06-11", global_macro=_MACRO)
    with patch.object(a, "_get_review_language", return_value="en"):
        block = a._build_global_macro_block(ov)
    assert "International Backdrop" in block
    assert "Philadelphia Semiconductor (SOX): 5,800.12 (↑1.23%)" in block
    assert "risk-on/off backdrop" in block


def test_build_global_macro_block_empty_returns_blank():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-11", global_macro=[])
    assert a._build_global_macro_block(ov) == ""


# --- config toggle ---

def test_config_intl_context_field_defaults_true():
    from src.config import Config
    field = Config.__dataclass_fields__["market_intl_context_enabled"]
    assert field.default is True
