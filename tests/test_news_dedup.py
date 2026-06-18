# -*- coding: utf-8 -*-
"""Regression: per-stock news must dedup the same story republished by different
outlets (e.g. 1802 台玻 returned identical titles from 經濟日報 and UDN).

URL dedup alone misses these (different URLs, same title). _rank_news_response now
dedups by a source-suffix-stripped, whitespace-collapsed title key.
"""

from src.search_service import SearchService, SearchResult, SearchResponse


def test_normalized_title_strips_source_suffix():
    f = SearchService._normalized_news_title
    a = f("臺玻5月營收月減、年增 法人看好今年毛利率逐季成長 - 經濟日報")
    b = f("臺玻5月營收月減、年增 法人看好今年毛利率逐季成長 - UDN")
    c = f("臺玻5月營收月減、年增 法人看好今年毛利率逐季成長｜鉅亨網")
    assert a == b == c and a != ""
    # distinct stories stay distinct
    assert f("台玻 1802 法說會重點") != a
    # empty title -> empty key (caller keeps such items)
    assert f("") == "" and f(None) == ""


def test_rank_dedups_same_title_across_sources():
    ss = SearchService()
    t = "臺玻5月營收月減、年增 法人看好今年毛利率逐季成長"
    resp = SearchResponse(query="1802", provider="TaiwanRSS", success=True, results=[
        SearchResult(title=f"{t} - 經濟日報", snippet="台玻 1802 營收", url="https://money.udn.com/a",
                     source="經濟日報", published_date="2026-06-13"),
        SearchResult(title=f"{t} - UDN", snippet="台玻 1802 營收", url="https://news.google.com/x",
                     source="UDN", published_date="2026-06-13"),
        SearchResult(title="台玻 1802 法說會重點", snippet="台玻 1802", url="https://x/b",
                     source="鉅亨", published_date="2026-06-13"),
    ])
    ranked = ss._rank_news_response(resp, stock_code="1802", stock_name="台玻",
                                    prefer_chinese=True, max_results=5, log_scope="1802")
    titles = [r.title for r in ranked.results]
    assert len(ranked.results) == 2, titles                    # 3 -> 2 (one dup removed)
    assert sum(1 for x in titles if x.startswith(t)) == 1       # only one of the dup pair kept


def test_rank_keeps_distinct_untitled_items():
    ss = SearchService()
    resp = SearchResponse(query="1802", provider="p", success=True, results=[
        SearchResult(title="", snippet="a", url="https://x/1", source="s", published_date="2026-06-13"),
        SearchResult(title="", snippet="b", url="https://x/2", source="s", published_date="2026-06-13"),
    ])
    ranked = ss._rank_news_response(resp, stock_code="1802", stock_name="台玻",
                                    prefer_chinese=True, max_results=5, log_scope="1802")
    assert len(ranked.results) == 2   # empty-title items are not collapsed together
