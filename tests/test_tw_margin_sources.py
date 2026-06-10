# -*- coding: utf-8 -*-
"""Tests for the authoritative T+0 per-stock 融資融券 / 三大法人 parsers.

融資融券: TWSE www MI_MARGN (上市) + TPEx www margin/balance (上櫃, ⚠ 券買賣順序與 TWSE 相反).
三大法人 上櫃: TPEx insti/dailyTrade CSV (foreign=[10], trust=[13], dealer=[22], total=[23]).
"""

from unittest.mock import patch

from data_provider import twse_openapi as tw


# --- 上市 融資融券: TWSE www MI_MARGN (_tse_margin_one) ---

def test_tse_margin_one_parses_balance_and_prev():
    # rwd row: [0代號 1名 2資買 3資賣 4資現償 5資前餘 6資今餘 7資限額
    #           8券回補 9券賣 10券現償 11券前餘 12券今餘 13券限額 ...]
    row = ["2330", "台積電", "100", "282", "0", "28350", "28168", "6483092",
           "0", "0", "0", "0", "0", "6483092", "0", " "]
    payload = {"stat": "OK", "date": "20260610", "tables": [{"data": [row]}]}
    with patch.object(tw, "_get_json", return_value=payload):
        r = tw._tse_margin_one("2330", "20260610")
    assert r["date"] == "2026-06-10"
    assert r["margin_balance"] == 28168 and r["margin_prev"] == 28350   # row[6], row[5]
    assert r["short_balance"] == 0 and r["short_prev"] == 0             # row[12], row[11]
    assert r["margin_usage_pct"] == round(28168 / 6483092 * 100, 4)


# --- 上櫃 融資融券: TPEx www margin/balance (_otc_margin_one) ---

def test_otc_margin_one_parses_with_tpex_short_order():
    # 20 cols: [0代 1名 2資前餘 3資買 4資賣 5資現償 6資餘 7資證 8資使用率 9資限額
    #           10券前餘 11券賣 12券買 13券償 14券餘 15券證 16券使用率 17券限額 18資券相抵 19備註]
    row = ["6488", "環球晶", "8896", "10", "399", "0", "8507", "x", "7.11", "119568",
           "114", "5", "8", "0", "111", "x", "x", "x", "0", " "]
    payload = {"stat": "ok", "tables": [{"data": [row]}]}  # TPEx stat is lowercase
    with patch.object(tw, "_get_tpex_www_json", return_value=payload):
        r = tw._otc_margin_one("6488", "20260610")
    assert r["date"] == "2026-06-10"
    assert r["margin_balance"] == 8507 and r["margin_prev"] == 8896     # row[6], row[2]
    assert r["short_balance"] == 111 and r["short_prev"] == 114         # row[14], row[10]
    assert r["short_sell"] == 5 and r["short_cover"] == 8               # ⚠ row[11] 賣, row[12] 買
    assert r["margin_usage_pct"] == 7.11


def test_otc_margin_one_none_on_bad_stat():
    with patch.object(tw, "_get_tpex_www_json", return_value={"stat": "no data", "tables": []}):
        assert tw._otc_margin_one("6488", "20260610") is None


# --- 上櫃 三大法人: TPEx insti/dailyTrade CSV (_fetch_otc_institutional) ---

def test_otc_institutional_csv_column_mapping_and_identity():
    # 24-col row; net cols: foreign=[10], trust=[13], dealer=[22], total=[23]
    row = ["6488", "環球晶",
           "1449301", "1076327", "372974",      # 2-4 外資不含自營
           "0", "0", "0",                        # 5-7 外資自營
           "1449301", "1076327", "372974",       # 8-10 外資(含自營)
           "0", "771147", "-771147",             # 11-13 投信
           "119000", "162300", "-43300",         # 14-16 自營(自行)
           "256128", "69338", "186790",          # 17-19 自營(避險)
           "375128", "231638", "143490",         # 20-22 自營合計
           "-254683"]                            # 23 三大法人合計
    with patch.object(tw, "_fetch_tpex_otc_insti_map", return_value={"6488": row}):
        r = tw._fetch_otc_institutional("6488", "20260610")
    assert r["market"] == "OTC" and r["date"] == "2026-06-10"
    assert r["foreign_net"] == 372974 and r["trust_net"] == -771147
    assert r["dealer_net"] == 143490 and r["total_net"] == -254683
    # validation identity from the doc: foreign + trust + dealer == total
    assert r["foreign_net"] + r["trust_net"] + r["dealer_net"] == r["total_net"]
