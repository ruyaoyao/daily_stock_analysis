# -*- coding: utf-8 -*-
"""Tests for TW market-wide chip stats: 三大法人買賣超合計 (BFI82U) + 融資融券餘額 (MI_MARGN MS)."""

from unittest.mock import patch

from data_provider import twse_openapi as tw

# BFI82U: {date, fields, data}; 買賣差額 in 元.
BFI82U = {
    "stat": "OK",
    "date": "20260609",
    "fields": ["單位名稱", "買進金額", "賣出金額", "買賣差額"],
    "data": [
        ["自營商(自行買賣)", "8,130,821,251", "13,253,632,240", "-5,122,810,989"],
        ["自營商(避險)", "37,755,796,040", "39,324,659,277", "-1,568,863,237"],
        ["投信", "56,259,767,955", "32,976,230,521", "23,283,537,434"],
        ["外資及陸資(不含外資自營商)", "442,595,518,013", "534,328,933,959", "-91,733,415,946"],
        ["外資自營商", "0", "0", "0"],
        ["合計", "544,741,903,259", "619,883,455,997", "-75,141,552,738"],
    ],
}

# MI_MARGN selectType=MS: tables[0] is 信用交易統計.
MI_MARGN_MS = {
    "stat": "OK",
    "date": "20260609",
    "tables": [
        {
            "title": "115年06月09日 信用交易統計",
            "fields": ["項目", "買進", "賣出", "現金(券)償還", "前日餘額", "今日餘額"],
            "data": [
                ["融資(交易單位)", "535,278", "417,738", "7,437", "9,066,915", "9,177,018"],
                ["融券(交易單位)", "49,524", "43,363", "15,065", "237,429", "216,203"],
                ["融資金額(仟元)", "43,318,975", "29,972,289", "481,991", "551,012,201", "563,876,896"],
            ],
        },
        {"title": None, "fields": None},
    ],
}


def test_institutional_total_aggregates_to_yi():
    with patch.object(tw, "_get_json", return_value=BFI82U):
        r = tw.get_tw_institutional_total()
    assert r is not None
    assert r["unit"] == "億元"
    assert r["trade_date"] == "2026-06-09"
    # 外資 = 外資及陸資 + 外資自營商 = -91,733,415,946 / 1e8
    assert r["foreign_net"] == round(-91_733_415_946 / 1e8, 2)
    assert r["trust_net"] == round(23_283_537_434 / 1e8, 2)
    # 自營商 = 自行買賣 + 避險
    assert r["dealer_net"] == round((-5_122_810_989 - 1_568_863_237) / 1e8, 2)
    assert r["total_net"] == round(-75_141_552_738 / 1e8, 2)


def test_institutional_total_none_on_fetch_failure():
    with patch.object(tw, "_get_json", return_value=None):
        assert tw.get_tw_institutional_total() is None


def test_margin_total_parses_amount_and_lots():
    with patch.object(tw, "_get_json", return_value=MI_MARGN_MS):
        r = tw.get_tw_margin_total()
    assert r is not None
    # 融資金額(仟元) → 億元：仟元 / 1e5
    assert r["margin_balance_yi"] == round(563_876_896 / 1e5, 2)
    assert r["margin_prev_yi"] == round(551_012_201 / 1e5, 2)
    assert r["margin_change_yi"] == round(563_876_896 / 1e5 - 551_012_201 / 1e5, 2)
    # 融券(交易單位) → 張
    assert r["short_balance_lots"] == 216203
    assert r["short_prev_lots"] == 237429
    assert r["short_change_lots"] == 216203 - 237429
    assert r["trade_date"] == "2026-06-09"


def test_margin_total_none_on_fetch_failure():
    with patch.object(tw, "_get_json", return_value=None):
        assert tw.get_tw_margin_total() is None


# --- DataFetcherManager routing ---

def test_manager_chip_stats_routes_tw():
    from data_provider.base import DataFetcherManager
    with patch("data_provider.twse_openapi.get_tw_institutional_total", return_value={"total_net": -751.42}), \
         patch("data_provider.twse_openapi.get_tw_margin_total", return_value={"margin_balance_yi": 5638.77}):
        out = DataFetcherManager().get_market_chip_stats(region="tw")
    assert out is not None
    assert out["institutional"]["total_net"] == -751.42
    assert out["margin"]["margin_balance_yi"] == 5638.77


def test_manager_chip_stats_none_for_non_tw():
    from data_provider.base import DataFetcherManager
    assert DataFetcherManager().get_market_chip_stats(region="cn") is None
    assert DataFetcherManager().get_market_chip_stats(region=None) is None


def test_manager_chip_stats_none_when_both_sources_unavailable():
    from data_provider.base import DataFetcherManager
    with patch("data_provider.twse_openapi.get_tw_institutional_total", return_value=None), \
         patch("data_provider.twse_openapi.get_tw_margin_total", return_value=None):
        assert DataFetcherManager().get_market_chip_stats(region="tw") is None
