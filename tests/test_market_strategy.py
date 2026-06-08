# -*- coding: utf-8 -*-
"""Tests for market strategy blueprints."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.core.market_strategy import get_market_strategy_blueprint
from src.market_analyzer import MarketAnalyzer, MarketOverview


class TestMarketStrategyBlueprint(unittest.TestCase):
    """Validate CN/US strategy blueprint basics."""

    def test_cn_blueprint_contains_action_framework(self):
        blueprint = get_market_strategy_blueprint("cn")
        block = blueprint.to_prompt_block()

        self.assertIn("A股市场三段式复盘策略", block)
        self.assertIn("Action Framework", block)
        self.assertIn("进攻", block)

    def test_us_blueprint_contains_regime_strategy(self):
        blueprint = get_market_strategy_blueprint("us")
        block = blueprint.to_prompt_block()

        self.assertIn("US Market Regime Strategy", block)
        self.assertIn("Risk-on", block)
        self.assertIn("Macro & Flows", block)


class TestMarketAnalyzerStrategyPrompt(unittest.TestCase):
    """Validate strategy section is injected into prompt/report."""

    def test_cn_prompt_contains_strategy_plan_section(self):
        analyzer = MarketAnalyzer(region="cn")
        prompt = analyzer._build_review_prompt(MarketOverview(date="2026-02-24"), [])

        self.assertIn("明日交易計劃", prompt)
        self.assertIn("A股市场三段式复盘策略", prompt)

    def test_us_prompt_contains_strategy_plan_section(self):
        with patch("src.market_analyzer.get_config", return_value=SimpleNamespace(report_language="en")):
            analyzer = MarketAnalyzer(region="us")

        prompt = analyzer._build_review_prompt(MarketOverview(date="2026-02-24"), [])

        self.assertIn("Strategy Plan", prompt)
        self.assertIn("US Market Regime Strategy", prompt)

    def test_us_prompt_localizes_strategy_markdown_when_report_language_is_zh(self):
        with patch("src.market_analyzer.get_config", return_value=SimpleNamespace(report_language="zh")):
            analyzer = MarketAnalyzer(region="us")

        prompt = analyzer._build_review_prompt(MarketOverview(date="2026-02-24"), [])

        self.assertIn("美股市場", prompt)
        self.assertNotIn("US Market Regime Strategy", prompt)
        self.assertNotIn("Strategy Blueprint", prompt)
        self.assertIn("風險偏好", prompt)

    def test_cn_prompt_uses_english_shell_when_report_language_is_en(self):
        with patch("src.market_analyzer.get_config", return_value=SimpleNamespace(report_language="en")):
            analyzer = MarketAnalyzer(region="cn")

        prompt = analyzer._build_review_prompt(MarketOverview(date="2026-02-24"), [])

        self.assertIn("# Today's Market Data", prompt)
        self.assertIn("### 1. Market Summary", prompt)
        self.assertIn("A-share Three-Phase Recap Strategy", prompt)
        self.assertNotIn("### 一、市场总结", prompt)
        self.assertNotIn("A股市场三段式复盘策略", prompt)



class TestTaiwanMarketReviewNewsFilter(unittest.TestCase):
    """Validate TW market review scope and news filtering."""

    def test_tw_prompt_uses_taiwan_market_scope(self):
        with patch("src.market_analyzer.get_config", return_value=SimpleNamespace(report_language="zh-Hant")):
            analyzer = MarketAnalyzer(region="tw")
        self.assertEqual(analyzer._get_market_scope_name(), "台股市場")
        prompt = analyzer._build_review_prompt(MarketOverview(date="2026-06-08"), [])
        self.assertIn("台股市場", prompt)
        self.assertNotIn("A股市場", prompt.split("台股市場")[0])

    def test_filter_market_review_news_drops_crypto_noise(self):
        noise = {"title": "Binance 的見解：覆盤", "snippet": "crypto market", "url": "https://binance.com/x"}
        relevant = {"title": "台股加權指數收黑", "snippet": "集中市場", "url": "https://news.example/tw"}
        filtered = MarketAnalyzer._filter_market_review_news([noise, relevant], "tw")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["title"], relevant["title"])

    def test_filter_market_review_news_keeps_non_tw_region(self):
        item = {"title": "Binance recap", "snippet": "", "url": "https://binance.com/x"}
        filtered = MarketAnalyzer._filter_market_review_news([item], "us")
        self.assertEqual(filtered, [item])

if __name__ == "__main__":
    unittest.main()
