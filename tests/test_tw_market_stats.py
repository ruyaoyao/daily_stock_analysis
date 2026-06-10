# -*- coding: utf-8 -*-
"""Tests for TW 大盤統計 (breadth/turnover) + 類股 sector rankings.

Cross-source date consistency: breadth + sector must come from the *current*
RWD MI_INDEX (the openapi mirror lags a day), so they align with the index /
chip data and the market-review judgment is not built on mixed dates.
"""

from unittest.mock import patch

from data_provider import twse_openapi as tw

RWD_MI_INDEX = {
    "stat": "OK", "date": "20260610",
    "tables": [
        {"title": "115年06月10日 價格指數(臺灣證券交易所)",
         "fields": ["指數", "收盤指數", "漲跌(+/-)", "漲跌點數", "漲跌百分比(%)", "特殊處理註記"],
         "data": [
             ["寶島股價指數", "48,210.10", "<p style='color:green'>-</p>", "1,692.11", "-3.39", ""],
             ["建材營造類指數", "x", "<p>+</p>", "y", "4.45", ""],
             ["電子零組件類指數", "x", "<p>-</p>", "y", "-6.25", ""],
             ["水泥類指數", "x", "<p>+</p>", "y", "0.37", ""],
             ["加權股價指數", "43,225.54", "<p>-</p>", "1,478.90", "-3.31", ""],  # excluded (no 類)
         ]},
        {"title": "115年06月10日 大盤統計資訊",
         "fields": ["成交統計", "成交金額(元)", "成交股數(股)", "成交筆數"],
         "data": [["1.一般股票", "1,293,322,027,390", "7,968,869,996", "6,214,710"]]},
        {"title": "漲跌證券數合計",
         "fields": ["類型", "整體市場", "股票"],
         "data": [
             ["上漲(漲停)", "3,181(110)", "259(14)"],
             ["下跌(跌停)", "9,168(449)", "748(17)"],
             ["持平", "525", "63"],
         ]},
    ],
}

RWD_FMTQIK_0610 = {
    "stat": "OK", "date": "20260610",
    "data": [["115/06/10", "15,773,244,263", "1,424,069,567,256", "8,485,375", "43,225.54", "-1,478.90"]],
}


def _router(mi_index=None, fmtqik=None, openapi_stock=None, openapi_fmtqik=None, openapi_mi=None):
    def _get(url, params=None):
        if "rwd" in url and "MI_INDEX" in url:
            return mi_index
        if "FMTQIK" in url and "rwd" in url:
            return fmtqik
        if "STOCK_DAY_ALL" in url:
            return openapi_stock
        if "FMTQIK" in url:
            return openapi_fmtqik
        if "MI_INDEX" in url:
            return openapi_mi
        return None
    return _get


def test_market_stats_from_rwd_current_day():
    with patch.object(tw, "_get_json", side_effect=_router(mi_index=RWD_MI_INDEX, fmtqik=RWD_FMTQIK_0610)):
        stats = tw.get_tw_market_stats()
    assert stats["trade_date"] == "2026-06-10"
    assert stats["up_count"] == 259 and stats["down_count"] == 748 and stats["flat_count"] == 63
    assert stats["limit_up_count"] == 14 and stats["limit_down_count"] == 17
    assert stats["total_amount"] == round(1424069567256 / 1e8, 2)   # 14240.70 億 (date-matched)


def test_sector_rankings_from_rwd_signed_pct():
    with patch.object(tw, "_get_json", side_effect=_router(mi_index=RWD_MI_INDEX, fmtqik=RWD_FMTQIK_0610)):
        top, bottom = tw.get_tw_sector_rankings(2)
    names_top = [s["name"] for s in top]
    assert names_top[0] == "建材營造"          # +4.45 leads
    assert top[0]["change_pct"] == 4.45
    assert bottom[0]["name"] == "電子零組件"     # -6.25 worst
    assert bottom[0]["change_pct"] == -6.25
    # broad indices (no 類) excluded
    assert all("寶島" not in s["name"] and "加權" not in s["name"] for s in top + bottom)


def test_market_stats_falls_back_to_openapi_when_rwd_unavailable():
    openapi_stock = [
        {"Change": "0.50", "ClosingPrice": "10.50"},
        {"Change": "-0.30", "ClosingPrice": "9.70"},
        {"Change": "0", "ClosingPrice": "5.00"},
    ]
    openapi_fmtqik = [{"Date": "1150609", "TradeValue": "1224062987846", "TAIEX": "44704.44", "Change": "1201.66"}]
    with patch.object(tw, "_get_json", side_effect=_router(
        mi_index=None, fmtqik=None, openapi_stock=openapi_stock, openapi_fmtqik=openapi_fmtqik)):
        stats = tw.get_tw_market_stats()
    assert stats["up_count"] == 1 and stats["down_count"] == 1 and stats["flat_count"] == 1
    assert stats["trade_date"] == "2026-06-09"     # stamped from FMTQIK so divergence is detectable


def test_parse_count_pair():
    assert tw._parse_count_pair("259(14)") == (259, 14)
    assert tw._parse_count_pair("63") == (63, 0)
    assert tw._parse_count_pair("3,181(110)") == (3181, 110)
    assert tw._parse_count_pair("-") == (None, 0)
