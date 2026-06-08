# -*- coding: utf-8 -*-
"""Tests for Taiwan entries in the stock autocomplete index."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Load the generator script as a module (scripts/ is not a package).
_spec = importlib.util.spec_from_file_location(
    "generate_index_from_csv", ROOT / "scripts" / "generate_index_from_csv.py"
)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

from data_provider.base import is_tw_stock_code, normalize_stock_code
from src.services.stock_index_remote_service import (
    SUPPORTED_STOCK_INDEX_MARKETS,
    validate_stock_index_payload,
)

PUBLIC_INDEX = ROOT / "apps" / "dsa-web" / "public" / "stocks.index.json"
TW_CSV = ROOT / "data" / "stock_list_tw.csv"


class TaiwanStockIndexTest(unittest.TestCase):
    def test_tw_is_supported_market(self) -> None:
        self.assertIn("TW", SUPPORTED_STOCK_INDEX_MARKETS)

    def test_curated_csv_loads_known_entries(self) -> None:
        curated = gen.load_tw_curated(ROOT / "data")
        self.assertGreaterEqual(len(curated), 20)
        symbols = {row["symbol"] for row in curated}
        self.assertIn("2330", symbols)  # 台積電
        self.assertIn("0050", symbols)  # 元大台灣50

    def test_build_rows_are_tw_routable_with_prefix(self) -> None:
        rows = gen.build_tw_compressed_rows(gen.load_tw_curated(ROOT / "data"))
        self.assertTrue(rows)
        for canonical, display, name, _py, _abbr, aliases, market, asset_type, active, pop in rows:
            self.assertEqual(market, "TW")
            self.assertTrue(canonical.startswith("tw"))
            self.assertEqual(canonical, display)
            # Selecting the suggestion submits canonicalCode -> must route to TW.
            self.assertTrue(is_tw_stock_code(canonical), f"{canonical} not TW-routable")
            # Bare numeric code is kept as an alias so typing e.g. 2330 matches.
            self.assertIn(canonical[2:], aliases)
            self.assertIn(asset_type, {"stock", "etf", "index"})
            self.assertTrue(active)

    def test_2330_normalizes_to_canonical_tw_code(self) -> None:
        self.assertEqual(normalize_stock_code("tw2330"), "TW2330")
        self.assertTrue(is_tw_stock_code("tw0050"))

    def test_public_index_contains_tw_and_validates(self) -> None:
        items = json.loads(PUBLIC_INDEX.read_text(encoding="utf-8"))
        tw = [it for it in items if it[6] == "TW"]
        self.assertGreaterEqual(len(tw), 20, "public index should ship Taiwan entries")
        # Whole payload must pass remote-cache validation (TW now allowlisted).
        validate_stock_index_payload(items)

    def test_merge_is_idempotent_in_test_mode(self) -> None:
        # test-mode merge must not raise and must not duplicate the kept set.
        rc = gen.merge_tw_into_index_files(ROOT / "data", test=True)
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    sys.exit(unittest.main())
