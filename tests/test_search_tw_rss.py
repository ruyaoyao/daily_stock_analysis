# -*- coding: utf-8 -*-
"""Unit tests for the Taiwan finance RSS search provider (TaiwanRSS)."""

import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock newspaper before search_service import (optional dependency).
if "newspaper" not in sys.modules:
    mock_np = MagicMock()
    mock_np.Article = MagicMock()
    mock_np.Config = MagicMock()
    sys.modules["newspaper"] = mock_np

from src.search_service import SearchService, TaiwanRSSSearchProvider


RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>測試財經</title>
    <item>
      <title><![CDATA[台積電2330領軍 台股創高]]></title>
      <link>https://ex.com/a</link>
      <pubDate>Sun, 07 Jun 2026 18:00:00 +0800</pubDate>
      <description><![CDATA[<p>台積電 2330 今日大漲</p>]]></description>
    </item>
    <item>
      <title><![CDATA[聯發科法說會]]></title>
      <link>https://ex.com/b</link>
      <pubDate>Sat, 06 Jun 2026 10:00:00 +0800</pubDate>
      <description><![CDATA[聯發科 2454 表示展望樂觀]]></description>
    </item>
    <item>
      <title><![CDATA[美股道瓊收紅]]></title>
      <link>https://ex.com/c</link>
      <pubDate>Fri, 05 Jun 2026 22:00:00 +0800</pubDate>
      <description><![CDATA[華爾街漲勢]]></description>
    </item>
  </channel>
</rss>""".encode("utf-8")

# Decoded reference tokens for readable assertions.
TSMC = "台積電"  # appears in item a
CODE_TSMC = "2330"
CODE_MTK = "2454"  # appears in item b description


class TaiwanRSSProviderTest(unittest.TestCase):
    FEED = "https://feeds.example.com/tw-finance"

    def setUp(self) -> None:
        TaiwanRSSSearchProvider.reset_feed_cache()

    def _provider(self, *, enabled: bool = True, **kwargs) -> TaiwanRSSSearchProvider:
        return TaiwanRSSSearchProvider(
            [self.FEED],
            enabled=enabled,
            google_news_enabled=False,
            finmind_news_enabled=False,
            **kwargs,
        )

    @staticmethod
    def _response(*, status_code: int = 200, content: bytes = RSS_XML) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.content = content
        return resp

    def test_is_available_respects_enabled_flag(self) -> None:
        self.assertTrue(self._provider().is_available)
        self.assertFalse(self._provider(enabled=False).is_available)

    def test_defaults_used_when_no_feeds_supplied(self) -> None:
        provider = TaiwanRSSSearchProvider(None)
        self.assertEqual(
            provider.feed_urls,
            [u.rstrip("/") for u in TaiwanRSSSearchProvider.DEFAULT_FEED_URLS],
        )

    def test_parse_extracts_fields_and_strips_html(self) -> None:
        items = TaiwanRSSSearchProvider._parse_rss(RSS_XML, self.FEED)
        self.assertEqual(len(items), 3)
        first = items[0]
        self.assertIn(TSMC, first.title)
        self.assertEqual(first.url, "https://ex.com/a")
        self.assertEqual(first.published_date, "2026-06-07")
        # HTML tags stripped from the description.
        self.assertNotIn("<p>", first.snippet)
        self.assertIn(TSMC, first.snippet)

    def test_pubdate_normalized_across_timezones(self) -> None:
        self.assertEqual(
            TaiwanRSSSearchProvider._normalize_pubdate("Fri, 05 Jun 2026 22:00:00 +0800"),
            "2026-06-05",
        )
        self.assertEqual(
            TaiwanRSSSearchProvider._normalize_pubdate("Sun, 07 Jun 2026 12:22:09 GMT"),
            "2026-06-07",
        )
        self.assertIsNone(TaiwanRSSSearchProvider._normalize_pubdate(None))

    def test_stock_specific_query_filters_by_name_and_code(self) -> None:
        provider = self._provider()
        with patch("src.search_service.requests.get", return_value=self._response()):
            resp = provider.search(f"{TSMC} {CODE_TSMC} 股票 最新消息", max_results=5)
        self.assertTrue(resp.success)
        self.assertEqual([r.url for r in resp.results], ["https://ex.com/a"])

    def test_query_matches_by_code_only(self) -> None:
        provider = self._provider()
        with patch("src.search_service.requests.get", return_value=self._response()):
            resp = provider.search(f"某檔 {CODE_MTK} 股票 最新消息", max_results=5)
        self.assertTrue(resp.success)
        self.assertEqual([r.url for r in resp.results], ["https://ex.com/b"])

    def test_market_query_returns_latest_headlines_sorted(self) -> None:
        provider = self._provider()
        with patch("src.search_service.requests.get", return_value=self._response()):
            resp = provider.search("台股 大盤 行情", max_results=5)
        self.assertTrue(resp.success)
        # All items, newest first.
        self.assertEqual(
            [r.url for r in resp.results],
            ["https://ex.com/a", "https://ex.com/b", "https://ex.com/c"],
        )

    def test_real_market_review_queries_return_headlines(self) -> None:
        """Regression: the actual TW_PROFILE.news_queries must return general
        headlines. These carry macro markers (加權指數/集中市場) absent from
        _QUERY_STOPWORDS, so they previously fell into the per-stock branch and
        were filtered down to ~0 results — the 大盤覆盤 "搜不到資料" bug."""
        from src.core.market_profile import get_profile

        provider = self._provider()
        cjk_queries = [
            q for q in get_profile("tw").news_queries
            if TaiwanRSSSearchProvider._CJK_RE.search(q)
        ]
        self.assertTrue(cjk_queries, "expected at least one CJK market query")
        for query in cjk_queries:
            provider.reset_feed_cache()
            with patch("src.search_service.requests.get", return_value=self._response()):
                resp = provider.search(query, max_results=5)
            self.assertTrue(resp.success, query)
            # Newest-first general headlines, not narrowed to per-stock hits.
            self.assertEqual(
                [r.url for r in resp.results],
                ["https://ex.com/a", "https://ex.com/b", "https://ex.com/c"],
                query,
            )

    def test_non_taiwan_macro_queries_do_not_return_taiwan_headlines(self) -> None:
        """CN/HK market-review queries share generic terms (大盘/行情/复盘) with
        Taiwan but carry no Taiwan-specific marker, so they must NOT be treated
        as Taiwan market-level queries (otherwise the CN/HK 大盤覆盤 would be
        polluted with Taiwan headlines)."""
        provider = self._provider()
        for query in ("A股 大盘 复盘", "港股 大盘 复盘", "恒生指数 行情", "股市 行情 分析"):
            provider.reset_feed_cache()
            with patch("src.search_service.requests.get", return_value=self._response()):
                resp = provider.search(query, max_results=5)
            self.assertTrue(resp.success, query)
            # None of the fixture headlines contain these CN/HK tokens.
            self.assertEqual(resp.results, [], query)

    def test_non_taiwan_query_short_circuits_without_network(self) -> None:
        provider = self._provider()
        with patch("src.search_service.requests.get") as mock_get:
            resp = provider.search("Apple AAPL stock latest news", max_results=5)
        self.assertTrue(resp.success)
        self.assertEqual(resp.results, [])
        mock_get.assert_not_called()

    def test_all_feeds_unavailable_reports_failure(self) -> None:
        provider = self._provider()
        with patch(
            "src.search_service.requests.get",
            return_value=self._response(status_code=503),
        ):
            resp = provider.search(f"{TSMC} {CODE_TSMC} 股票 最新消息", max_results=5)
        self.assertFalse(resp.success)
        self.assertEqual(resp.results, [])

    def test_feed_failure_is_swallowed_not_raised(self) -> None:
        provider = self._provider()
        with patch(
            "src.search_service.requests.get",
            side_effect=Exception("boom"),
        ):
            resp = provider.search(f"{TSMC} {CODE_TSMC} 股票 最新消息", max_results=5)
        self.assertFalse(resp.success)

    def test_feeds_cached_within_ttl(self) -> None:
        provider = self._provider()
        with patch(
            "src.search_service.requests.get",
            return_value=self._response(),
        ) as mock_get:
            provider.search(f"{TSMC} {CODE_TSMC} 股票 最新消息", max_results=5)
            provider.search(f"某檔 {CODE_MTK} 股票 最新消息", max_results=5)
        # Generic feed cached once; per-stock Yahoo feeds fetched per distinct code.
        self.assertEqual(mock_get.call_count, 3)

    @patch("src.search_service.requests.get")
    def test_per_stock_yahoo_feed_used_when_code_present(self, mock_get) -> None:
        provider = self._provider()

        def _side_effect(url, **kwargs):
            if "rss?s=2303" in url:
                return self._response(content=(
                    b"""<?xml version='1.0'?><rss version='2.0'><channel><item>"""
                    b"""<title><![CDATA[\xe8\x81\xaf\xe9\x9b\xbb2303\xe6\xb8\xac\xe8\xa9\xa6]]></title>"""
                    b"""<link>https://ex.com/stock</link><pubDate>Sun, 07 Jun 2026 18:00:00 +0800</pubDate>"""
                    b"""<description><![CDATA[\xe8\x81\xaf\xe9\x9b\xbb2303]]></description></item></channel></rss>"""
                ))
            return self._response()

        mock_get.side_effect = _side_effect
        resp = provider.search("聯電 TW2303 股票 最新消息", max_results=5)
        self.assertTrue(resp.success)
        self.assertEqual(resp.results[0].url, "https://ex.com/stock")
        called_urls = [call.args[0] for call in mock_get.call_args_list]
        self.assertTrue(any("rss?s=2303" in url for url in called_urls))


    @patch("src.search_service.requests.get")
    def test_google_news_feed_used_when_enabled(self, mock_get) -> None:
        provider = TaiwanRSSSearchProvider(
            [self.FEED],
            google_news_enabled=True,
            finmind_news_enabled=False,
        )

        def _side_effect(url, **kwargs):
            if "news.google.com/rss/search" in url:
                return self._response(content=(
                    b"""<?xml version='1.0'?><rss version='2.0'><channel><item>"""
                    b"""<title><![CDATA[\xe8\x81\xaf\xe9\x9b\xbb2303 Google]]></title>"""
                    b"""<link>https://ex.com/google</link>"""
                    b"""<pubDate>Sun, 07 Jun 2026 18:00:00 +0800</pubDate>"""
                    b"""<description><![CDATA[\xe8\x81\xaf\xe9\x9b\xbb2303]]></description></item></channel></rss>"""
                ))
            return self._response()

        mock_get.side_effect = _side_effect
        resp = provider.search("聯電 TW2303 股票 最新消息", max_results=5)
        self.assertTrue(resp.success)
        self.assertEqual(resp.results[0].url, "https://ex.com/google")
        called_urls = [call.args[0] for call in mock_get.call_args_list]
        self.assertTrue(any("news.google.com/rss/search" in url for url in called_urls))

    @patch("src.search_service.requests.get")
    def test_finmind_news_merged_when_enabled(self, mock_get) -> None:
        provider = TaiwanRSSSearchProvider(
            [self.FEED],
            google_news_enabled=False,
            finmind_news_enabled=True,
        )

        def _side_effect(url, **kwargs):
            if "api.finmindtrade.com" in url:
                return MagicMock(
                    status_code=200,
                    json=lambda: {
                        "status": 200,
                        "msg": "success",
                        "data": [{
                            "date": "2026-06-07",
                            "stock_id": "2303",
                            "source": "工商時報",
                            "title": "聯電2303法說會",
                            "link": "https://ex.com/finmind",
                        }],
                    },
                )
            return self._response()

        mock_get.side_effect = _side_effect
        resp = provider.search("聯電 TW2303 股票 最新消息", max_results=5)
        self.assertTrue(resp.success)
        urls = [r.url for r in resp.results]
        self.assertIn("https://ex.com/finmind", urls)

    def test_google_news_feed_urls_build_query(self) -> None:
        urls = TaiwanRSSSearchProvider._google_news_feed_urls(["聯電"], ["TW2303"])
        self.assertEqual(len(urls), 1)
        self.assertIn("news.google.com/rss/search", urls[0])
        self.assertIn("2303", urls[0])
        self.assertIn("%E8%81%AF%E9%9B%BB", urls[0])



class TaiwanRSSRegistrationTest(unittest.TestCase):
    """TaiwanRSS provider registration inside SearchService."""

    def setUp(self) -> None:
        TaiwanRSSSearchProvider.reset_feed_cache()

    def test_registered_by_default(self) -> None:
        service = SearchService(searxng_public_instances_enabled=False)
        self.assertTrue(
            any(isinstance(p, TaiwanRSSSearchProvider) for p in service._providers)
        )

    def test_not_registered_when_disabled(self) -> None:
        service = SearchService(
            searxng_public_instances_enabled=False,
            tw_rss_enabled=False,
        )
        self.assertFalse(
            any(isinstance(p, TaiwanRSSSearchProvider) for p in service._providers)
        )

    def test_custom_feed_urls_applied(self) -> None:
        service = SearchService(
            searxng_public_instances_enabled=False,
            tw_rss_feed_urls=["https://custom.example.com/rss"],
        )
        provider = next(
            p for p in service._providers if isinstance(p, TaiwanRSSSearchProvider)
        )
        self.assertEqual(provider.feed_urls, ["https://custom.example.com/rss"])




if __name__ == "__main__":
    unittest.main()
