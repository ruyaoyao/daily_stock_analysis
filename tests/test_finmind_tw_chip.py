# -*- coding: utf-8 -*-
"""Tests for Taiwan chip distribution via TDCC / FinMindTwFetcher."""

import unittest
from unittest.mock import MagicMock, patch

from data_provider.base import _is_meaningful_chip_distribution
from data_provider.finmind_tw_fetcher import FinMindTwFetcher
from data_provider.tdcc_opendata import (
    compute_chip_metrics_from_tiers,
    get_shareholding_tiers,
    normalize_tdcc_stock_code,
)


class TestNormalizeTdccStockCode(unittest.TestCase):
    def test_tw_prefix(self) -> None:
        self.assertEqual(normalize_tdcc_stock_code("TW0050"), "0050")
        self.assertEqual(normalize_tdcc_stock_code("tw2330"), "2330")

    def test_suffix(self) -> None:
        self.assertEqual(normalize_tdcc_stock_code("2330.TW"), "2330")


class TestComputeChipMetricsFromTiers(unittest.TestCase):
    def test_maps_large_holder_concentration(self) -> None:
        tiers = [
            {"level": 1, "people": 100, "percent": 10.0, "shares": 100},
            {"level": 10, "people": 10, "percent": 20.0, "shares": 200},
            {"level": 15, "people": 1, "percent": 30.0, "shares": 300},
            {"level": 17, "people": 111, "percent": 100.0, "shares": 600},
        ]
        metrics = compute_chip_metrics_from_tiers(
            tiers,
            current_price=110.0,
            avg_cost=100.0,
        )
        profit_ratio, avg_cost, _, _, concentration_90, _, _, concentration_70 = metrics
        self.assertAlmostEqual(concentration_90, 0.50)
        self.assertAlmostEqual(concentration_70, 0.50)
        self.assertGreater(profit_ratio, 0.5)
        self.assertEqual(avg_cost, 100.0)


class TestFinMindTwFetcher(unittest.TestCase):
    @patch("data_provider.finmind_tw_fetcher.get_shareholding_tiers")
    @patch.object(FinMindTwFetcher, "_fetch_price_stats", return_value=(110.0, 100.0))
    def test_get_chip_distribution_success(self, _price_mock, tiers_mock) -> None:
        tiers_mock.return_value = {
            "code": "0050",
            "date": "2026-06-05",
            "tiers": [
                {"level": 10, "people": 1, "percent": 25.0, "shares": 1},
                {"level": 15, "people": 1, "percent": 20.0, "shares": 1},
                {"level": 17, "people": 2, "percent": 100.0, "shares": 2},
            ],
        }
        fetcher = FinMindTwFetcher()
        fetcher._token = ""
        chip = fetcher.get_chip_distribution("TW0050")
        self.assertIsNotNone(chip)
        assert chip is not None
        self.assertEqual(chip.code, "TW0050")
        self.assertEqual(chip.date, "2026-06-05")
        self.assertTrue(_is_meaningful_chip_distribution(chip))

    @patch("data_provider.finmind_tw_fetcher.get_shareholding_tiers", return_value=None)
    def test_non_tw_returns_none(self, _tiers_mock) -> None:
        fetcher = FinMindTwFetcher()
        self.assertIsNone(fetcher.get_chip_distribution("600519"))


class TestGetShareholdingTiers(unittest.TestCase):
    @patch("data_provider.tdcc_opendata._fetch_tdcc_records")
    def test_filters_by_trimmed_code(self, fetch_mock) -> None:
        fetch_mock.return_value = [
            {
                "證券代號": "0050  ",
                "占集保庫存數比例%": "25.71",
                "人數": "241",
                "\ufeff資料日期": "20260605",
                "股數": "4956907733",
                "持股分級": "15",
            },
            {
                "證券代號": "0050  ",
                "占集保庫存數比例%": "100.00",
                "人數": "3008243",
                "\ufeff資料日期": "20260605",
                "股數": "19273000000",
                "持股分級": "17",
            },
        ]
        result = get_shareholding_tiers("TW0050")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["code"], "0050")
        self.assertEqual(result["date"], "2026-06-05")
        self.assertEqual(len(result["tiers"]), 2)


if __name__ == "__main__":
    unittest.main()
