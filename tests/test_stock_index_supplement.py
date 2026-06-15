# -*- coding: utf-8 -*-
"""Regression: a remote (upstream) stock index that lacks fork-local markets
(Taiwan TW/TWO) must not drop those stocks.

Bug: the remote index URL points to upstream (no Taiwan); its fetched cache (newest)
shadowed the bundled index, so 1815 富喬 / all TW stocks vanished from search/resolution.
The loader now unions bundled-only entries into the remote map (active-wins), keeping
the remote authoritative + fresh for its markets while preserving local markets.
"""

import json

import src.data.stock_index_loader as L


def test_supplement_adds_local_only_market_and_keeps_active(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled.json"
    bundled.write_text(json.dumps([
        ["tw1815", "tw1815", "富喬", "fuqiao", "fq", ["1815"], "TWO", "stock", True, 100],
        ["tw2330", "tw2330", "台積電", "taijidian", "tjd", ["2330"], "TW", "stock", True, 100],
        # collides with an entry already in the active (remote) map -> active must win
        ["000001.SZ", "000001", "平安银行(bundled-stale)", "x", "y", [], "CN", "stock", True, 100],
    ], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(L, "_bundled_stock_index_paths", lambda: (bundled,))

    # active map = what a TW-less remote index produced (has CN, no TW)
    active = {}
    for key in L._build_lookup_keys("000001.SZ", "000001"):
        active[key] = "平安银行"

    merged = L._supplement_with_bundled_entries(active)

    # local-only TW markets are added back
    assert "富喬" in merged.values()
    assert "台積電" in merged.values()
    # active (remote, fresh) value wins over the bundled stale duplicate
    cn_key = next(iter(L._build_lookup_keys("000001.SZ", "000001")))
    assert merged[cn_key] == "平安银行"


def test_supplement_noop_when_no_bundled(monkeypatch):
    monkeypatch.setattr(L, "_bundled_stock_index_paths", lambda: ())
    active = {"tw2330": "台積電"}
    assert L._supplement_with_bundled_entries(active) == {"tw2330": "台積電"}


def test_supplement_resolves_via_get_index_stock_name(tmp_path, monkeypatch):
    """End-to-end: with a TW-less remote map active, get_index_stock_name still finds TW."""
    bundled = tmp_path / "bundled.json"
    bundled.write_text(json.dumps([
        ["tw1815", "tw1815", "富喬", "fuqiao", "fq", ["1815"], "TWO", "stock", True, 100],
    ], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(L, "_bundled_stock_index_paths", lambda: (bundled,))
    L.clear_stock_index_cache()
    # seed the in-process cache with a remote-only (no TW) map, then supplement
    monkeypatch.setattr(L, "_STOCK_INDEX_CACHE", L._supplement_with_bundled_entries({}))
    assert L.get_index_stock_name("tw1815") == "富喬"
    L.clear_stock_index_cache()
