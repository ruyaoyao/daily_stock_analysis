# -*- coding: utf-8 -*-
"""Tests for the authoritative TAIEX (加權指數) fetcher.

Primary source is the TWSE MIS real-time API (carries the *current* session,
which the openapi daily mirror can lag by a day); MI_5MINS_HIST is the fallback.
yfinance ^TWII was laggy/gappy/inaccurate (missing sessions, wrong levels ->
wrong 漲跌幅), so it must not drive the index.
"""

from unittest.mock import patch

from data_provider import twse_openapi as tw

# MIS real-time API shape (ex_ch=tse_t00.tw): a 6/10 down day.
MIS_TAIEX = {
    "rtcode": "0000",
    "msgArray": [{
        "n": "發行量加權股價指數", "d": "20260610", "t": "13:33:00",
        "z": "43225.54",   # close / last
        "y": "44704.44",   # prev close
        "o": "44581.45", "h": "44676.49", "l": "43225.54",
    }],
}

# openapi daily MI_5MINS_HIST (lags a day -> only up to 6/09).
TAIEX_OHLC = [
    {"Date": "1150608", "OpeningIndex": "44507.49", "HighestIndex": "44900.00", "LowestIndex": "43400.00", "ClosingIndex": "43502.78"},
    {"Date": "1150609", "OpeningIndex": "43687.62", "HighestIndex": "44821.71", "LowestIndex": "43687.62", "ClosingIndex": "44704.44"},
]

FMTQIK_0609 = [
    {"Date": "1150609", "TradeValue": "1224062987846", "TradeVolume": "14106451926"},
]
FMTQIK_0610 = [
    {"Date": "1150610", "TradeValue": "1300000000000", "TradeVolume": "15000000000"},
]


def _router(mis=None, hist=None, fmtqik=None):
    def _get(url, params=None):
        if "mis.twse.com.tw" in url:
            return mis
        if "MI_5MINS_HIST" in url:
            return hist
        if "FMTQIK" in url:
            return fmtqik
        return None
    return _get


def test_taiex_prefers_mis_current_session():
    # MIS available -> use it (6/10), even though hist would give 6/09.
    with patch.object(tw, "_get_json", side_effect=_router(mis=MIS_TAIEX, hist=TAIEX_OHLC, fmtqik=FMTQIK_0609)):
        idx = tw.get_tw_taiex_index()
    assert idx["current"] == 43225.54 and idx["prev_close"] == 44704.44
    assert idx["change"] == round(43225.54 - 44704.44, 4)              # -1478.90
    assert idx["change_pct"] == round((43225.54 - 44704.44) / 44704.44 * 100, 4)  # ~ -3.31%
    assert idx["change_pct"] < 0
    # FMTQIK is 6/09 but index is 6/10 -> turnover must NOT be mislabeled onto today
    assert idx["amount"] == 0.0 and idx["volume"] == 0.0


def test_taiex_mis_uses_matching_day_turnover():
    with patch.object(tw, "_get_json", side_effect=_router(mis=MIS_TAIEX, hist=TAIEX_OHLC, fmtqik=FMTQIK_0610)):
        idx = tw.get_tw_taiex_index()
    assert idx["current"] == 43225.54
    assert idx["amount"] == 1300000000000.0     # FMTQIK date (6/10) matches index date
    assert idx["volume"] == 15000000000.0


def test_taiex_falls_back_to_hist_when_mis_unavailable():
    with patch.object(tw, "_get_json", side_effect=_router(mis=None, hist=TAIEX_OHLC, fmtqik=FMTQIK_0609)):
        idx = tw.get_tw_taiex_index()
    assert idx["current"] == 44704.44 and idx["prev_close"] == 43502.78
    assert idx["change_pct"] == round((44704.44 - 43502.78) / 43502.78 * 100, 4)  # +2.76%
    assert idx["amount"] == 1224062987846.0     # hist date 6/09 matches FMTQIK 6/09


def test_taiex_none_when_all_sources_fail():
    with patch.object(tw, "_get_json", side_effect=_router(mis=None, hist=None, fmtqik=None)):
        assert tw.get_tw_taiex_index() is None


def test_roc_to_ad_conversion():
    assert tw._roc_to_ad_yyyymmdd("1150610") == "20260610"
    assert tw._roc_to_ad_yyyymmdd("") is None
    assert tw._roc_to_ad_yyyymmdd("20260610") is None  # already AD / not 7-digit ROC
