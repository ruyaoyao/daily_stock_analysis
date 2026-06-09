# -*- coding: utf-8 -*-
"""Tests for per-stock TW chip flow: 三大法人买卖超 + 融资融券 (twse_openapi TSE + FinMind OTC fallback)."""

from unittest.mock import patch

from data_provider.base import DataFetcherManager
from src.analyzer import GeminiAnalyzer


# --- DataFetcherManager.get_tw_stock_chip_flow routing ---

def test_chip_flow_none_for_non_tw():
    assert DataFetcherManager().get_tw_stock_chip_flow("AAPL") is None
    assert DataFetcherManager().get_tw_stock_chip_flow("600519") is None


def test_chip_flow_tse_via_twse_openapi_converts_shares_to_lots():
    inst = {"date": "2026-06-08", "foreign_net": -20_464_649, "trust_net": 730_000,
            "dealer_net": -214_367, "total_net": -19_949_016}
    margin = {"date": None, "margin_balance": 27_603, "short_balance": None,
              "margin_usage_pct": 0.43}
    with patch("data_provider.twse_openapi.get_institutional_investors", return_value=inst), \
         patch("data_provider.twse_openapi.get_margin_balance", return_value=margin):
        out = DataFetcherManager().get_tw_stock_chip_flow("tw2330")
    assert out is not None
    i = out["institutional"]
    assert i["source"] == "twse_openapi"
    assert i["foreign_net_lots"] == -20465      # 股 → 张 (round)
    assert i["trust_net_lots"] == 730
    assert i["total_net_lots"] == -19949
    assert out["margin"]["margin_balance_lots"] == 27603
    assert out["margin"]["margin_change_lots"] is None  # openapi single-day has no prev


def test_chip_flow_otc_falls_back_to_finmind():
    # twse_openapi returns None for OTC (TPEx blocked) -> FinMind fallback used.
    fm_inst = {"date": "2026-06-09", "foreign_net_lots": -379, "trust_net_lots": -79,
               "dealer_net_lots": 293, "total_net_lots": -165, "source": "finmind"}
    fm_margin = {"date": "2026-06-09", "margin_balance_lots": 8896, "margin_change_lots": -79,
                 "short_balance_lots": 84, "short_change_lots": -3, "margin_usage_pct": 7.44,
                 "source": "finmind"}

    class _FakeFinMind:
        def get_institutional_net(self, code):
            return fm_inst

        def get_margin_flow(self, code):
            return fm_margin

    mgr = DataFetcherManager()
    with patch("data_provider.twse_openapi.get_institutional_investors", return_value=None), \
         patch("data_provider.twse_openapi.get_margin_balance", return_value=None), \
         patch.object(mgr, "_get_fetcher_by_name", return_value=_FakeFinMind()):
        out = mgr.get_tw_stock_chip_flow("tw6488")
    assert out["institutional"]["source"] == "finmind"
    assert out["institutional"]["total_net_lots"] == -165
    assert out["margin"]["margin_change_lots"] == -79


def test_chip_flow_none_when_all_sources_empty():
    mgr = DataFetcherManager()
    with patch("data_provider.twse_openapi.get_institutional_investors", return_value=None), \
         patch("data_provider.twse_openapi.get_margin_balance", return_value=None), \
         patch.object(mgr, "_get_fetcher_by_name", return_value=None):
        assert mgr.get_tw_stock_chip_flow("tw6488") is None


def test_shares_to_lots_rounding_and_none():
    assert DataFetcherManager._shares_to_lots(None) is None
    assert DataFetcherManager._shares_to_lots(1_500) == 2      # round-half-to-even/away -> 2
    assert DataFetcherManager._shares_to_lots(-20_464_649) == -20465


# --- FinMind per-stock institutional / margin parsing ---

def test_finmind_institutional_net_aggregates_types():
    from data_provider.finmind_tw_fetcher import FinMindTwFetcher
    rows = [
        {"date": "2026-06-08", "name": "Foreign_Investor", "buy": 0, "sell": 100000},
        {"date": "2026-06-09", "name": "Foreign_Investor", "buy": 1000000, "sell": 1379000},
        {"date": "2026-06-09", "name": "Foreign_Dealer_Self", "buy": 0, "sell": 0},
        {"date": "2026-06-09", "name": "Investment_Trust", "buy": 2705000, "sell": 44913},
        {"date": "2026-06-09", "name": "Dealer_self", "buy": 5000, "sell": 1000},
        {"date": "2026-06-09", "name": "Dealer_Hedging", "buy": 0, "sell": 2000},
    ]
    f = FinMindTwFetcher()
    with patch.object(f, "_finmind_rows", return_value=rows):
        r = f.get_institutional_net("tw2330")
    assert r["date"] == "2026-06-09"           # latest day only
    assert r["foreign_net_lots"] == round((1000000 - 1379000) / 1000)   # -379
    assert r["trust_net_lots"] == round((2705000 - 44913) / 1000)       # 2660
    assert r["dealer_net_lots"] == round((5000 - 1000 - 2000) / 1000)   # 2
    assert r["source"] == "finmind"


def test_finmind_margin_flow_computes_change():
    from data_provider.finmind_tw_fetcher import FinMindTwFetcher
    rows = [
        {"date": "2026-06-08", "MarginPurchaseTodayBalance": 8975, "MarginPurchaseYesterdayBalance": 9000,
         "ShortSaleTodayBalance": 87, "ShortSaleYesterdayBalance": 90, "MarginPurchaseLimit": 119568},
        {"date": "2026-06-09", "MarginPurchaseTodayBalance": 8896, "MarginPurchaseYesterdayBalance": 8975,
         "ShortSaleTodayBalance": 84, "ShortSaleYesterdayBalance": 87, "MarginPurchaseLimit": 119568},
    ]
    f = FinMindTwFetcher()
    with patch.object(f, "_finmind_rows", return_value=rows):
        r = f.get_margin_flow("tw6488")
    assert r["date"] == "2026-06-09"
    assert r["margin_balance_lots"] == 8896
    assert r["margin_change_lots"] == 8896 - 8975   # -79
    assert r["short_change_lots"] == 84 - 87        # -3
    assert r["margin_usage_pct"] == round(8896 / 119568 * 100, 2)


def test_finmind_methods_none_for_non_tw():
    from data_provider.finmind_tw_fetcher import FinMindTwFetcher
    f = FinMindTwFetcher()
    assert f.get_institutional_net("AAPL") is None
    assert f.get_margin_flow("600519") is None


# --- analyzer block rendering ---

def test_analyzer_chip_flow_block_zh_and_en():
    flow = {
        "institutional": {"date": "2026-06-08", "foreign_net_lots": -20465, "trust_net_lots": 730,
                          "dealer_net_lots": -214, "total_net_lots": -19949, "source": "twse_openapi"},
        "margin": {"date": "2026-06-09", "margin_balance_lots": 28350, "margin_change_lots": 747,
                   "short_balance_lots": 84, "short_change_lots": -3, "margin_usage_pct": 7.44,
                   "source": "finmind"},
    }
    zh = GeminiAnalyzer._build_tw_chip_flow_block(flow, "zh")
    assert "个股筹码流动" in zh
    assert "+730" in zh and "-19,949" in zh         # signed net, thousands sep
    assert "28,350" in zh and "+747" in zh           # margin balance + change
    en = GeminiAnalyzer._build_tw_chip_flow_block(flow, "en")
    assert "TW Chip Flow" in en and "lots" in en


def test_analyzer_chip_flow_block_empty_returns_blank():
    assert GeminiAnalyzer._build_tw_chip_flow_block({}, "zh") == ""
    assert GeminiAnalyzer._build_tw_chip_flow_block({"institutional": None, "margin": None}, "zh") == ""
