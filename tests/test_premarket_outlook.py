# -*- coding: utf-8 -*-
"""Tests for the TW market-review 「盤前展望」 module (opt-in).

Source: TAIFEX TX night-session futures via Shioaji + US-session backdrop.
Must degrade gracefully (US-session-only) when night futures are unavailable,
and never break the review. Per-stock analysis is unaffected.
"""

from unittest.mock import MagicMock, patch

from data_provider.base import DataFetcherManager
from src.core.trading_calendar import MarketPhase
from src.market_analyzer import MarketAnalyzer, MarketOverview


# --- ShioajiTwFetcher.get_tx_night_quote ---

def test_shioaji_tx_night_quote_parses_snapshot():
    from data_provider.shioaji_tw_fetcher import ShioajiTwFetcher
    f = ShioajiTwFetcher()
    contract = MagicMock(); contract.code = "TXFF6"
    snap = MagicMock(close=23150.0, change_price=-120.0, change_rate=-0.52,
                     high=23300.0, low=23050.0, total_volume=88000)
    api = MagicMock(); api.snapshots.return_value = [snap]
    with patch.object(f._session, "resolve_futures_front_month", return_value=contract), \
         patch.object(f._session, "get_api", return_value=api):
        r = f.get_tx_night_quote()
    assert r is not None
    assert r["code"] == "TXFF6" and r["price"] == 23150.0
    assert r["change_pct"] == -0.52
    assert r["prev_close"] == 23270.0   # close - change_amount
    assert r["source"] == "shioaji"


def test_shioaji_tx_night_quote_none_when_no_contract():
    from data_provider.shioaji_tw_fetcher import ShioajiTwFetcher
    f = ShioajiTwFetcher()
    with patch.object(f._session, "resolve_futures_front_month", return_value=None):
        assert f.get_tx_night_quote() is None


def test_shioaji_tx_night_quote_none_on_exception():
    from data_provider.shioaji_tw_fetcher import ShioajiTwFetcher
    f = ShioajiTwFetcher()
    with patch.object(f._session, "resolve_futures_front_month", side_effect=Exception("no futures perm")):
        assert f.get_tx_night_quote() is None


# --- DataFetcherManager.get_tx_night_quote delegation ---

def test_manager_tx_night_delegates():
    mgr = DataFetcherManager()
    fake = MagicMock(); fake.name = "shioaji"
    fake.get_tx_night_quote.return_value = {"code": "TXFF6", "price": 23150.0}
    mgr._fetchers = [fake]
    assert mgr.get_tx_night_quote() == {"code": "TXFF6", "price": 23150.0}


def test_manager_tx_night_none_when_no_capable_fetcher():
    mgr = DataFetcherManager()
    mgr._fetchers = [object()]
    assert mgr.get_tx_night_quote() is None


# --- MarketAnalyzer._get_premarket_outlook (fail-safe + degraded) ---

_US = [{"code": "SOX", "zh_name": "費城半導體指數", "current": 5800.0, "change_pct": 1.2},
       {"code": "VIX", "zh_name": "波動率指數", "current": 14.5, "change_pct": -2.0}]
_TX = {"code": "TXFF6", "name": "台指期近月", "price": 23150.0, "change_pct": -0.52, "prev_close": 23270.0}
_ADR = {"adr_usd": 240.0, "adr_change_pct": 1.5, "usdtwd": 29.5, "tw2330_close": 1400.0,
        "implied_twd": 1416.0, "premium_pct": 1.14, "source": "yfinance"}


def test_get_premarket_outlook_full():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-11", global_macro=_US)
    with patch.object(a.data_manager, "get_tx_night_quote", return_value=_TX), \
         patch.object(a.data_manager, "get_tsmc_adr_premium", return_value=_ADR):
        a._get_premarket_outlook(ov)
    assert ov.premarket_outlook["tx_night"]["code"] == "TXFF6"
    assert len(ov.premarket_outlook["us_session"]) == 2
    assert ov.premarket_outlook["adr"]["premium_pct"] == 1.14
    assert ov.premarket_outlook["bias"]["label"] in ("偏多", "偏空", "中性")


def test_get_premarket_outlook_degraded_when_no_tx():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-11", global_macro=_US)
    with patch.object(a.data_manager, "get_tx_night_quote", return_value=None), \
         patch.object(a.data_manager, "get_tsmc_adr_premium", return_value=_ADR):
        a._get_premarket_outlook(ov)
    assert ov.premarket_outlook["tx_night"] is None      # degraded
    assert ov.premarket_outlook["us_session"]            # but US session present
    assert ov.premarket_outlook["adr"]                   # ADR still works without Shioaji


def test_get_premarket_outlook_none_when_all_empty():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-11", global_macro=[])
    with patch.object(a.data_manager, "get_tx_night_quote", return_value=None), \
         patch.object(a.data_manager, "get_global_macro_indicators", return_value=[]), \
         patch.object(a.data_manager, "get_tsmc_adr_premium", return_value=None):
        a._get_premarket_outlook(ov)
    assert ov.premarket_outlook is None


def test_get_premarket_outlook_failsafe_on_exception():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-11", global_macro=_US)
    with patch.object(a.data_manager, "get_tx_night_quote", side_effect=Exception("boom")), \
         patch.object(a.data_manager, "get_tsmc_adr_premium", return_value=None):
        a._get_premarket_outlook(ov)   # must not raise
    # tx failed but US session keeps a degraded outlook
    assert ov.premarket_outlook["tx_night"] is None


# --- _build_premarket_outlook_block rendering ---

def test_build_premarket_block_full():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-11",
                        premarket_outlook={"tx_night": _TX, "us_session": _US})
    block = a._build_premarket_outlook_block(ov)
    assert "盤前展望（隔夜前瞻）" in block
    assert "台指期夜盤" in block and "23,150" in block and "↓0.52%" in block
    assert "美股盤後 費城半導體指數" in block and "↑1.20%" in block


def test_build_premarket_block_degraded():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-11",
                        premarket_outlook={"tx_night": None, "us_session": _US})
    block = a._build_premarket_outlook_block(ov)
    assert "資料不可用" in block          # degraded note
    assert "美股盤後 費城半導體指數" in block


def test_build_premarket_block_empty():
    a = MarketAnalyzer(region="tw")
    assert a._build_premarket_outlook_block(MarketOverview(date="2026-06-11")) == ""
    ov = MarketOverview(date="2026-06-11", premarket_outlook={"tx_night": None, "us_session": []})
    assert a._build_premarket_outlook_block(ov) == ""


# --- config toggle defaults opt-in ---

def test_config_premarket_outlook_defaults_false():
    from src.config import Config
    field = Config.__dataclass_fields__["premarket_outlook_enabled"]
    assert field.default is False


# === v1: ADR premium / direction bias / phase-gating / enriched render ===

import sys  # noqa: E402


def test_yf_tsmc_adr_premium_computes_from_three_legs():
    from data_provider.yfinance_fetcher import YfinanceFetcher
    f = YfinanceFetcher()

    def _echo(yf, yf_code, name, code):
        return {"TSM": {"current": 240.0, "change_pct": 1.5},
                "TWD=X": {"current": 29.5, "change_pct": 0.1},
                "2330.TW": {"current": 1400.0, "change_pct": 0.0}}[yf_code]

    with patch.dict(sys.modules, {"yfinance": MagicMock()}), \
         patch.object(f, "_fetch_yf_ticker_data", side_effect=_echo):
        r = f.get_tsmc_adr_premium()
    assert r is not None
    # implied = 240 * 29.5 / 5 = 1416 ; premium = (1416/1400 - 1)*100 = 1.14%
    assert r["implied_twd"] == 1416.0
    assert r["premium_pct"] == 1.14


def test_yf_tsmc_adr_premium_none_when_leg_missing():
    from data_provider.yfinance_fetcher import YfinanceFetcher
    f = YfinanceFetcher()

    def _partial(yf, yf_code, name, code):
        return {"current": 240.0} if yf_code == "TSM" else None   # FX/2330 missing

    with patch.dict(sys.modules, {"yfinance": MagicMock()}), \
         patch.object(f, "_fetch_yf_ticker_data", side_effect=_partial):
        assert f.get_tsmc_adr_premium() is None


def test_premarket_bias_bullish_and_bearish():
    a = MarketAnalyzer(region="tw")
    # ADR signal uses overnight change (adr_change_pct), NOT the structural premium level
    bull = a._compute_premarket_bias(
        {"change_pct": 0.8}, [{"code": "SOX", "change_pct": 1.5}], {"adr_change_pct": 2.0})
    assert bull["label"] == "偏多" and bull["score"] > 0
    bear = a._compute_premarket_bias(
        {"change_pct": -0.9}, [{"code": "SOX", "change_pct": -2.0}], {"adr_change_pct": -2.0})
    assert bear["label"] == "偏空" and bear["score"] < 0
    flat = a._compute_premarket_bias({"change_pct": 0.05}, [], None)
    assert flat["label"] == "中性"


def test_premarket_bias_ignores_structural_adr_premium_level():
    """A large structural ADR premium (e.g. +15%) with flat overnight change
    must NOT make the bias bullish on its own."""
    a = MarketAnalyzer(region="tw")
    r = a._compute_premarket_bias(None, [], {"premium_pct": 14.89, "adr_change_pct": 0.1})
    assert r["score"] == 0 and r["label"] == "中性"


def test_premarket_bias_vix_spike_pulls_bearish():
    a = MarketAnalyzer(region="tw")
    r = a._compute_premarket_bias(None, [{"code": "VIX", "change_pct": 12.0}], None)
    assert r["score"] < 0 and "VIX" in " ".join(r["reasons"])


def test_is_premarket_window_skips_intraday_and_postmarket():
    a = MarketAnalyzer(region="tw")
    with patch("src.market_analyzer.infer_market_phase", return_value=MarketPhase.INTRADAY):
        assert a._is_premarket_window() is False
    with patch("src.market_analyzer.infer_market_phase", return_value=MarketPhase.POSTMARKET):
        assert a._is_premarket_window() is False
    with patch("src.market_analyzer.infer_market_phase", return_value=MarketPhase.PREMARKET):
        assert a._is_premarket_window() is True
    with patch("src.market_analyzer.infer_market_phase", return_value=MarketPhase.NON_TRADING):
        assert a._is_premarket_window() is True   # pre-open prep for next session


def test_build_premarket_block_renders_adr_and_bias():
    a = MarketAnalyzer(region="tw")
    bias = {"label": "偏多", "score": 3, "reasons": ["台指期夜盤 +0.80%", "台積電ADR隔夜 +1.50%"]}
    ov = MarketOverview(date="2026-06-11", premarket_outlook={
        "tx_night": _TX, "us_session": _US, "adr": _ADR, "bias": bias})
    block = a._build_premarket_outlook_block(ov)
    assert "開盤前定調：偏多" in block
    assert "台積電 ADR 隔夜：↑1.50%" in block          # signal = overnight change
    assert "含結構性溢價，非漲跌目標" in block          # premium level caveated
    assert "隔夜/前一交易日盤後" in block
