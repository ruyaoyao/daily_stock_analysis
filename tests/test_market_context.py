# -*- coding: utf-8 -*-
"""Tests for market-specific LLM prompt context detection."""

from __future__ import annotations

import unittest

from src.market_context import detect_market, get_market_guidelines, get_market_role


class TestMarketContext(unittest.TestCase):
    def test_detect_market_tw_prefixed_codes(self) -> None:
        self.assertEqual(detect_market("TW2303"), "tw")
        self.assertEqual(detect_market("tw2330"), "tw")
        self.assertEqual(detect_market("2330.TW"), "tw")
        self.assertEqual(detect_market("6271.TWO"), "tw")

    def test_detect_market_other_markets(self) -> None:
        self.assertEqual(detect_market("600519"), "cn")
        self.assertEqual(detect_market("00700"), "hk")
        self.assertEqual(detect_market("AAPL"), "us")

    def test_tw_prompt_role_and_guidelines(self) -> None:
        self.assertEqual(get_market_role("TW2303", "zh"), "台股")
        self.assertIn("台股", get_market_guidelines("TW2303", "zh"))
        self.assertIn("三大法人", get_market_guidelines("TW2303", "zh"))
        self.assertNotIn("A 股", get_market_guidelines("TW2303", "zh"))

    def test_cn_prompt_unchanged(self) -> None:
        self.assertEqual(get_market_role("600519", "zh"), " A 股")
        self.assertIn("A 股", get_market_guidelines("600519", "zh"))


if __name__ == "__main__":
    unittest.main()
