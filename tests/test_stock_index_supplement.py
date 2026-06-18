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


# --- Served payload (frontend autocomplete index) ----------------------------
# Bug: serve_stock_index streamed the freshest index file verbatim. When the
# upstream remote cache (no Taiwan) was newest, the served /stocks.index.json had
# zero TW/TWO stocks, so 5351 鈺創 and every other Taiwan stock was unsearchable
# in the web UI — even though backend name lookup was already protected.


def _remote_payload():
    return [
        ["000001.SZ", "000001", "平安银行", "pinganyinhang", "payh", [], "CN", "stock", True, 100],
        ["AAPL", "AAPL", "苹果", "pingguo", "pg", [], "US", "stock", True, 100],
    ]


def test_supplement_payload_adds_local_only_markets(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled.json"
    bundled.write_text(json.dumps([
        ["tw5351", "tw5351", "鈺創", "yuchuang", "yc", ["5351"], "TWO", "stock", True, 100],
        ["tw2330", "tw2330", "台積電", "taijidian", "tjd", ["2330"], "TW", "stock", True, 100],
        # collides with a remote entry -> remote stays authoritative, not duplicated
        ["000001.SZ", "000001", "平安银行(bundled-stale)", "x", "y", [], "CN", "stock", True, 100],
    ], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(L, "_bundled_stock_index_paths", lambda: (bundled,))

    merged = L.supplement_payload_with_bundled_markets(_remote_payload())
    codes = [item[0] for item in merged]

    assert "tw5351" in codes and "tw2330" in codes
    assert codes.count("000001.SZ") == 1
    cn = next(item for item in merged if item[0] == "000001.SZ")
    assert cn[2] == "平安银行"  # remote value preserved, bundled-stale dropped


def test_supplement_payload_noop_when_no_bundled(monkeypatch):
    monkeypatch.setattr(L, "_bundled_stock_index_paths", lambda: ())
    payload = _remote_payload()
    assert L.supplement_payload_with_bundled_markets(payload) == payload


def test_served_bytes_supplements_remote_cache(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled.json"
    bundled.write_text(json.dumps([
        ["tw5351", "tw5351", "鈺創", "yuchuang", "yc", ["5351"], "TWO", "stock", True, 100],
        ["000001.SZ", "000001", "平安银行(bundled-stale)", "x", "y", [], "CN", "stock", True, 100],
    ], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(L, "_bundled_stock_index_paths", lambda: (bundled,))

    remote_cache = tmp_path / "remote_cache.json"
    remote_cache.write_text(json.dumps(_remote_payload(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(L, "get_remote_stock_index_cache_path", lambda: remote_cache)
    L.clear_stock_index_cache()

    served = json.loads(L.get_served_stock_index_bytes(remote_cache))
    codes = [item[0] for item in served]

    # Taiwan stock is now present in the served payload
    assert "tw5351" in codes
    # Remote stays authoritative for codes it already covers (no stale duplicate)
    assert codes.count("000001.SZ") == 1
    cn = next(item for item in served if item[0] == "000001.SZ")
    assert cn[2] == "平安银行"
    L.clear_stock_index_cache()


def test_served_bytes_returns_bundled_file_verbatim(tmp_path, monkeypatch):
    """A bundled index already carries local markets -> serve it unchanged."""
    remote_cache = tmp_path / "remote_cache.json"  # does not exist
    monkeypatch.setattr(L, "get_remote_stock_index_cache_path", lambda: remote_cache)

    bundled_file = tmp_path / "static.json"
    raw = json.dumps([
        ["tw5351", "tw5351", "鈺創", "yuchuang", "yc", ["5351"], "TWO", "stock", True, 100],
    ], ensure_ascii=False).encode("utf-8")
    bundled_file.write_bytes(raw)

    assert L.get_served_stock_index_bytes(bundled_file) == raw
