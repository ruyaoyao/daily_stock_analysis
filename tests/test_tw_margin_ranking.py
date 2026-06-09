# -*- coding: utf-8 -*-
"""Tests for the TW market-wide 融資增加 ranking (TWSE MI_MARGN)."""

from unittest.mock import patch

import pytest

from data_provider import twse_openapi as tw

# Mirrors the openapi MI_MARGN row shape (units = 張).
ROWS = [
    {"股票代號": "2303", "股票名稱": "聯電", "融資前日餘額": "154409", "融資今日餘額": "183923",
     "融券前日餘額": "3420", "融券今日餘額": "2840", "融資限額": "1000000", "資券互抵": "0"},
    {"股票代號": "2409", "股票名稱": "友達", "融資前日餘額": "212076", "融資今日餘額": "218562",
     "融券前日餘額": "24210", "融券今日餘額": "32404", "融資限額": "500000", "資券互抵": "0"},
    {"股票代號": "0001", "股票名稱": "小型", "融資前日餘額": "100", "融資今日餘額": "90",
     "融券前日餘額": "0", "融券今日餘額": "0", "融資限額": "1000", "資券互抵": "0"},
]


def test_ranking_sorted_by_margin_increase_with_derived_fields():
    with patch.object(tw, "_get_json", return_value=ROWS):
        r = tw.get_tw_margin_ranking(2)
    assert [x["stock_code"] for x in r] == ["2303", "2409"]  # +29514 > +6486 > -10
    assert r[0]["margin_change"] == 29514
    assert r[1]["margin_change"] == 6486
    # 券資比 = 融券今餘 / 融資今餘 * 100
    assert r[1]["short_margin_ratio"] == round(32404 / 218562 * 100, 2)
    # 融資使用率 = 融資今餘 / 融資限額 * 100
    assert r[0]["margin_usage_pct"] == round(183923 / 1000000 * 100, 2)
    assert r[1]["short_change"] == 32404 - 24210  # +8194


def test_ranking_short_increase_sort():
    with patch.object(tw, "_get_json", return_value=ROWS):
        r = tw.get_tw_margin_ranking(1, sort_by="short_increase")
    assert r[0]["stock_code"] == "2409"  # short +8194 is largest


def test_ranking_margin_decrease_sort():
    with patch.object(tw, "_get_json", return_value=ROWS):
        r = tw.get_tw_margin_ranking(1, sort_by="margin_decrease")
    assert r[0]["stock_code"] == "0001"  # -10 is the largest decrease


def test_ranking_none_on_fetch_failure():
    with patch.object(tw, "_get_json", return_value=None):
        assert tw.get_tw_margin_ranking() is None


# --- screener API endpoint ---

def test_endpoint_returns_ranking_payload():
    from api.v1.endpoints import tw_margin as ep
    sample = [{"stock_code": "2303", "name": "聯電", "margin_change": 29514}]
    with patch("data_provider.twse_openapi.get_tw_margin_ranking", return_value=sample):
        out = ep.tw_margin_ranking(top_n=5, sort_by="margin_increase")
    assert out["success"] is True
    assert out["market"] == "tw" and out["unit"] == "張"
    assert out["count"] == 1 and out["ranking"][0]["stock_code"] == "2303"


def test_endpoint_graceful_when_source_unavailable():
    from api.v1.endpoints import tw_margin as ep
    with patch("data_provider.twse_openapi.get_tw_margin_ranking", return_value=None):
        out = ep.tw_margin_ranking(top_n=5, sort_by="margin_increase")
    assert out["success"] is False and out["ranking"] == [] and out["error"]


def test_endpoint_rejects_invalid_sort():
    from fastapi import HTTPException
    from api.v1.endpoints import tw_margin as ep
    with pytest.raises(HTTPException) as exc:
        ep.tw_margin_ranking(top_n=5, sort_by="bogus")
    assert exc.value.status_code == 400
