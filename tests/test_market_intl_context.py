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

    def _echo(yf, yf_code, name, code, before_date=None):
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

    def _side_effect(yf, yf_code, name, code, before_date=None):
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


# --- date alignment: overnight US session, not "latest" (off-schedule robustness) ---

import pandas as pd
from datetime import date


def _hist_df(rows):
    """rows: list of (date_str, close). Builds a yfinance-like daily DataFrame."""
    idx = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[1] for r in rows],
            "Low": [r[1] for r in rows],
            "Close": [r[1] for r in rows],
            "Volume": [0 for _ in rows],
        },
        index=idx,
    )


def test_fetch_before_date_picks_session_strictly_before_review_day():
    """A 6/25 TW review must use the 6/24 (overnight) close, not 6/25's latest bar."""
    from data_provider.yfinance_fetcher import YfinanceFetcher
    f = YfinanceFetcher()
    full = _hist_df([
        ("2026-06-23", 100.0),
        ("2026-06-24", 110.0),   # <- overnight session for a 6/25 TW review
        ("2026-06-25", 130.0),   # <- "latest" (too fresh / same-day) must be ignored
    ])
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = full
    fake_yf = MagicMock()
    fake_yf.Ticker.return_value = fake_ticker

    item = f._fetch_yf_ticker_data(fake_yf, "^SOX", "費城半導體指數", "SOX",
                                   before_date=date(2026, 6, 25))
    assert item is not None
    assert item["current"] == 110.0                    # 6/24 close, not 6/25
    assert item["prev_close"] == 100.0                 # 6/23 close
    assert round(item["change_pct"], 4) == 10.0        # (110-100)/100


def test_fetch_before_date_none_keeps_latest_behavior():
    from data_provider.yfinance_fetcher import YfinanceFetcher
    f = YfinanceFetcher()
    two_day = _hist_df([("2026-06-24", 110.0), ("2026-06-25", 130.0)])
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = two_day
    fake_yf = MagicMock()
    fake_yf.Ticker.return_value = fake_ticker

    item = f._fetch_yf_ticker_data(fake_yf, "^SOX", "費城半導體指數", "SOX")
    assert item["current"] == 130.0                    # latest row preserved
    fake_ticker.history.assert_called_with(period="2d")


def test_fetch_before_date_returns_none_when_no_earlier_session():
    from data_provider.yfinance_fetcher import YfinanceFetcher
    f = YfinanceFetcher()
    only_after = _hist_df([("2026-06-25", 130.0), ("2026-06-26", 140.0)])
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = only_after
    fake_yf = MagicMock()
    fake_yf.Ticker.return_value = fake_ticker

    item = f._fetch_yf_ticker_data(fake_yf, "^SOX", "費城半導體指數", "SOX",
                                   before_date=date(2026, 6, 25))
    assert item is None


def test_yf_global_macro_threads_before_date_to_each_indicator():
    from data_provider.yfinance_fetcher import YfinanceFetcher
    f = YfinanceFetcher()
    seen = []

    def _capture(yf, yf_code, name, code, before_date=None):
        seen.append(before_date)
        return {"current": 1.0, "change_pct": 0.0}

    with patch.dict(sys.modules, {"yfinance": MagicMock()}), \
         patch.object(f, "_fetch_yf_ticker_data", side_effect=_capture):
        f.get_global_macro_indicators(before_date=date(2026, 6, 25))
    assert seen == [date(2026, 6, 25)] * 4


def test_manager_passes_before_date_when_fetcher_supports_it():
    mgr = DataFetcherManager()
    captured = {}

    # Real function (not MagicMock) so inspect.signature sees the before_date param.
    def _getter(before_date=None):
        captured["before_date"] = before_date
        return [{"code": "SOX", "current": 1.0}]

    fetcher = MagicMock()
    fetcher.name = "fake"
    fetcher.get_global_macro_indicators = _getter
    mgr._fetchers = [fetcher]
    assert mgr.get_global_macro_indicators(before_date=date(2026, 6, 25)) == [
        {"code": "SOX", "current": 1.0}
    ]
    assert captured["before_date"] == date(2026, 6, 25)


def test_manager_falls_back_to_no_arg_for_legacy_fetcher():
    """A fetcher whose getter lacks before_date must still be called (no TypeError)."""
    mgr = DataFetcherManager()
    legacy = MagicMock()
    legacy.name = "legacy"

    # Real function (not MagicMock) so inspect.signature sees no before_date param.
    def _legacy_getter():
        return [{"code": "SOX", "current": 2.0}]

    legacy.get_global_macro_indicators = _legacy_getter
    mgr._fetchers = [legacy]
    assert mgr.get_global_macro_indicators(before_date=date(2026, 6, 25)) == [
        {"code": "SOX", "current": 2.0}
    ]


def test_macro_before_date_tw_is_review_day_us_is_none():
    a_tw = MarketAnalyzer(region="tw")
    assert a_tw._macro_before_date(MarketOverview(date="2026-06-25")) == date(2026, 6, 25)
    a_us = MarketAnalyzer(region="us")
    assert a_us._macro_before_date(MarketOverview(date="2026-06-25")) is None
    # Malformed date is fail-safe (None -> latest behavior, no crash).
    assert a_tw._macro_before_date(MarketOverview(date="not-a-date")) is None


def test_get_global_macro_threads_review_date_for_tw():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-25")
    with patch.object(a.data_manager, "get_global_macro_indicators",
                      return_value=[{"code": "SOX", "current": 1.0}]) as g:
        a._get_global_macro(ov)
    g.assert_called_once_with(before_date=date(2026, 6, 25))
