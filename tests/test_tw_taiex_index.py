# -*- coding: utf-8 -*-
"""Tests for the authoritative TAIEX (加權指數) fetcher.

Price: TWSE MIS real-time API (current session) -> openapi MI_5MINS_HIST (daily,
may lag) -> yfinance. Turnover: RWD FMTQIK (current) -> openapi FMTQIK (may lag),
date-matched to the index date so a prior session's turnover is never stamped on
today's index. yfinance ^TWII (laggy/gappy/inaccurate) must not drive the index.
"""

from unittest.mock import patch

from data_provider import twse_openapi as tw

# MIS real-time (ex_ch=tse_t00.tw): a 6/10 down day.
MIS_TAIEX = {
    "rtcode": "0000",
    "msgArray": [{
        "n": "發行量加權股價指數", "d": "20260610", "t": "13:33:00",
        "z": "43225.54", "y": "44704.44", "o": "44581.45", "h": "44676.49", "l": "43225.54",
    }],
}

# openapi daily MI_5MINS_HIST (lags -> only up to 6/09).
TAIEX_OHLC = [
    {"Date": "1150608", "OpeningIndex": "44507.49", "HighestIndex": "44900.00", "LowestIndex": "43400.00", "ClosingIndex": "43502.78"},
    {"Date": "1150609", "OpeningIndex": "43687.62", "HighestIndex": "44821.71", "LowestIndex": "43687.62", "ClosingIndex": "44704.44"},
]

# RWD FMTQIK (current): list-of-list, ROC slashed date.
RWD_FMTQIK = {
    "stat": "OK", "date": "20260610",
    "data": [
        ["115/06/09", "14,106,451,926", "1,224,062,987,846", "5,700,000", "44,704.44", "1,201.66"],
        ["115/06/10", "15,773,244,263", "1,424,069,567,256", "8,485,375", "43,225.54", "-1,478.90"],
    ],
}
RWD_FMTQIK_ONLY_0609 = {
    "stat": "OK", "date": "20260609",
    "data": [
        ["115/06/08", "12,000,000,000", "1,000,000,000,000", "5,000,000", "43,502.78", "-2,174.68"],
        ["115/06/09", "14,106,451,926", "1,224,062,987,846", "5,700,000", "44,704.44", "1,201.66"],
    ],
}


def _router(mis=None, hist=None, rwd_fmtqik=None):
    def _get(url, params=None):
        if "mis.twse.com.tw" in url:
            return mis
        if "MI_5MINS_HIST" in url:
            return hist
        if "FMTQIK" in url:          # RWD or openapi; tests drive the RWD path
            return rwd_fmtqik
        return None
    return _get


def test_taiex_prefers_mis_with_matching_day_turnover():
    with patch.object(tw, "_get_json", side_effect=_router(mis=MIS_TAIEX, hist=TAIEX_OHLC, rwd_fmtqik=RWD_FMTQIK)):
        idx = tw.get_tw_taiex_index()
    assert idx["current"] == 43225.54 and idx["prev_close"] == 44704.44
    assert idx["change_pct"] == round((43225.54 - 44704.44) / 44704.44 * 100, 4)  # ~ -3.31%
    assert idx["change_pct"] < 0
    # RWD FMTQIK has 6/10 -> turnover is today's, not the prior session
    assert idx["amount"] == 1424069567256.0
    assert idx["volume"] == 15773244263.0


def test_taiex_turnover_na_when_fmtqik_lags():
    # MIS gives 6/10 but FMTQIK only has up to 6/09 -> no mislabeled turnover.
    with patch.object(tw, "_get_json", side_effect=_router(mis=MIS_TAIEX, hist=TAIEX_OHLC, rwd_fmtqik=RWD_FMTQIK_ONLY_0609)):
        idx = tw.get_tw_taiex_index()
    assert idx["current"] == 43225.54 and idx["change_pct"] < 0
    assert idx["amount"] == 0.0 and idx["volume"] == 0.0


def test_taiex_falls_back_to_hist_when_mis_unavailable():
    with patch.object(tw, "_get_json", side_effect=_router(mis=None, hist=TAIEX_OHLC, rwd_fmtqik=RWD_FMTQIK)):
        idx = tw.get_tw_taiex_index()
    assert idx["current"] == 44704.44 and idx["prev_close"] == 43502.78
    assert idx["change_pct"] == round((44704.44 - 43502.78) / 43502.78 * 100, 4)  # +2.76%
    assert idx["amount"] == 1224062987846.0    # hist date 6/09 -> RWD 6/09 row


def test_taiex_none_when_all_sources_fail():
    with patch.object(tw, "_get_json", side_effect=_router(mis=None, hist=None, rwd_fmtqik=None)):
        assert tw.get_tw_taiex_index() is None


def test_roc_to_ad_conversion_handles_slashes():
    assert tw._roc_to_ad_yyyymmdd("1150610") == "20260610"
    assert tw._roc_to_ad_yyyymmdd("115/06/10") == "20260610"
    assert tw._roc_to_ad_yyyymmdd("") is None
