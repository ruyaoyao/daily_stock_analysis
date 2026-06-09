# -*- coding: utf-8 -*-
"""Tests for the TPEx (上柜/OTC) securities list fetcher + board-aware index rows."""

from unittest.mock import MagicMock, patch


def _finmind_payload():
    return {
        "msg": "success",
        "status": 200,
        "data": [
            {"stock_id": "6488", "stock_name": "環球晶", "type": "tpex", "industry_category": "半導體業", "date": "2026-06-09"},
            {"stock_id": "5483", "stock_name": "中美晶", "type": "tpex", "industry_category": "半導體業", "date": "2026-06-09"},
            {"stock_id": "00679B", "stock_name": "元大美債20年", "type": "tpex", "industry_category": "ETF", "date": "2026-06-09"},
            # twse + emerging must be excluded
            {"stock_id": "2330", "stock_name": "台積電", "type": "twse", "industry_category": "半導體業", "date": "2026-06-09"},
            {"stock_id": "6571", "stock_name": "盛弘", "type": "emerging", "industry_category": "生技", "date": "2026-06-09"},
            # duplicate code (later date) must not duplicate
            {"stock_id": "6488", "stock_name": "環球晶", "type": "tpex", "industry_category": "半導體業", "date": "2020-01-01"},
        ],
    }


def test_fetch_tpex_filters_to_tpex_and_dedupes():
    from data_provider.tpex_stock_list import fetch_tpex_listed_securities
    resp = MagicMock()
    resp.json.return_value = _finmind_payload()
    resp.raise_for_status.return_value = None
    with patch("data_provider.tpex_stock_list.requests.get", return_value=resp):
        rows = fetch_tpex_listed_securities()
    codes = sorted(r["symbol"] for r in rows)
    assert codes == ["00679B", "5483", "6488"]   # only tpex, deduped
    by_code = {r["symbol"]: r for r in rows}
    assert by_code["6488"]["name"] == "環球晶"
    assert by_code["6488"]["asset_type"] == "stock"
    assert by_code["00679B"]["asset_type"] == "etf"   # 00-prefixed -> etf


def test_fetch_tpex_empty_on_failure():
    from data_provider.tpex_stock_list import fetch_tpex_listed_securities
    with patch("data_provider.tpex_stock_list.requests.get", side_effect=RuntimeError("boom")):
        assert fetch_tpex_listed_securities() == []


def test_build_tw_rows_encodes_board_market():
    import importlib.util
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "_gen_index", repo / "scripts" / "generate_index_from_csv.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    item = [{"symbol": "6488", "name": "環球晶", "asset_type": "stock", "aliases": ["6488"]}]
    tw = mod.build_tw_compressed_rows(item, market="TW")
    two = mod.build_tw_compressed_rows(item, market="TWO")
    assert tw[0][0] == "tw6488" and tw[0][6] == "TW"     # canonical code keeps tw prefix
    assert two[0][0] == "tw6488" and two[0][6] == "TWO"  # only market field differs
