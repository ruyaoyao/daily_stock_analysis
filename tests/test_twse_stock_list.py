# -*- coding: utf-8 -*-
"""Tests for TWSE listed stock list fetcher."""

import unittest
from unittest.mock import patch

from data_provider.twse_stock_list import fetch_twse_listed_securities


class TestFetchTwseListedSecurities(unittest.TestCase):
    @patch("data_provider.twse_stock_list._get_json")
    def test_merges_company_and_day_all(self, get_json_mock) -> None:
        get_json_mock.side_effect = [
            [
                {
                    "公司代號": "2344",
                    "公司簡稱": "華邦電",
                    "公司名稱": "華邦電子股份有限公司",
                    "英文簡稱": "Winbond",
                },
                {
                    "公司代號": "2330",
                    "公司簡稱": "台積電",
                    "公司名稱": "台灣積體電路製造股份有限公司",
                    "英文簡稱": "TSMC",
                },
            ],
            [
                {"Code": "0050", "Name": "元大台灣50"},
                {"Code": "2344", "Name": "華邦電"},
            ],
        ]

        rows = fetch_twse_listed_securities()
        by_symbol = {row["symbol"]: row for row in rows}

        self.assertIn("2344", by_symbol)
        self.assertEqual(by_symbol["2344"]["name"], "華邦電")
        self.assertIn("Winbond", by_symbol["2344"]["aliases"])
        self.assertIn("0050", by_symbol)
        self.assertEqual(by_symbol["0050"]["asset_type"], "etf")
        self.assertEqual(len(rows), 3)

    @patch("data_provider.twse_stock_list._get_json", return_value=None)
    def test_returns_empty_when_api_unavailable(self, _mock) -> None:
        self.assertEqual(fetch_twse_listed_securities(), [])


if __name__ == "__main__":
    unittest.main()
