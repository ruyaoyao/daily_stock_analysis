# -*- coding: utf-8 -*-
"""Tests for TW per-stock valuation (TWSE BWIBBU_ALL) and realtime-quote enrichment."""

from unittest.mock import patch

from data_provider import twse_openapi as tw

# BWIBBU_ALL: list-of-dicts; PEratio empty string for loss-making names.
BWIBBU = [
    {"Date": "1150608", "Code": "2330", "Name": "台積電", "PEratio": "30.86", "DividendYield": "0.96", "PBratio": "10.10"},
    {"Date": "1150608", "Code": "1101", "Name": "台泥", "PEratio": "", "DividendYield": "3.35", "PBratio": "0.76"},
]


def _reset_cache():
    tw._tw_valuation_cache["date"] = None
    tw._tw_valuation_cache["map"] = None


def test_valuation_lookup_and_code_normalization():
    _reset_cache()
    with patch.object(tw, "_get_json", return_value=BWIBBU):
        for code in ("2330", "tw2330", "TW2330"):
            r = tw.get_tw_valuation(code)
            assert r is not None
            assert r["pe_ratio"] == 30.86
            assert r["pb_ratio"] == 10.10
            assert r["dividend_yield"] == 0.96


def test_valuation_loss_making_keeps_pb_when_pe_empty():
    _reset_cache()
    with patch.object(tw, "_get_json", return_value=BWIBBU):
        r = tw.get_tw_valuation("1101")
    assert r is not None
    assert r["pe_ratio"] is None
    assert r["pb_ratio"] == 0.76


def test_valuation_none_for_unknown_code():
    _reset_cache()
    with patch.object(tw, "_get_json", return_value=BWIBBU):
        assert tw.get_tw_valuation("9999") is None


def test_valuation_none_on_fetch_failure():
    _reset_cache()
    with patch.object(tw, "_get_json", return_value=None):
        assert tw.get_tw_valuation("2330") is None


def test_valuation_uses_per_day_cache():
    _reset_cache()
    with patch.object(tw, "_get_json", return_value=BWIBBU) as mock_get:
        tw.get_tw_valuation("2330")
        tw.get_tw_valuation("1101")
        tw.get_tw_valuation("2330")
    assert mock_get.call_count == 1  # one BWIBBU_ALL download served all lookups


# --- DataFetcherManager._enrich_tw_valuation ---

class _FakeQuote:
    def __init__(self, pe=None, pb=None):
        self.pe_ratio = pe
        self.pb_ratio = pb


def test_enrich_fills_missing_pe_pb():
    from data_provider.base import DataFetcherManager
    q = _FakeQuote(pe=None, pb=None)
    with patch("data_provider.twse_openapi.get_tw_valuation",
               return_value={"pe_ratio": 30.86, "pb_ratio": 10.10, "dividend_yield": 0.96}):
        DataFetcherManager()._enrich_tw_valuation(q, "tw2330")
    assert q.pe_ratio == 30.86
    assert q.pb_ratio == 10.10


def test_enrich_does_not_clobber_existing_values():
    from data_provider.base import DataFetcherManager
    q = _FakeQuote(pe=11.1, pb=2.2)
    with patch("data_provider.twse_openapi.get_tw_valuation") as mock_val:
        DataFetcherManager()._enrich_tw_valuation(q, "tw2330")
    mock_val.assert_not_called()  # both present → skip fetch entirely
    assert q.pe_ratio == 11.1 and q.pb_ratio == 2.2


def test_enrich_is_safe_when_source_unavailable():
    from data_provider.base import DataFetcherManager
    q = _FakeQuote(pe=None, pb=None)
    with patch("data_provider.twse_openapi.get_tw_valuation", return_value=None):
        DataFetcherManager()._enrich_tw_valuation(q, "tw9999")
    assert q.pe_ratio is None and q.pb_ratio is None
