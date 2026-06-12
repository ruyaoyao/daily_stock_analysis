# -*- coding: utf-8 -*-
"""Regression: a bare TW/CN numeric stock code must not match plain numbers in
foreign-language prose.

TW3715 bug: an English mining article ("...3715 units of torque...") scored a
"标题/摘要命中股票代码 3715" hit and surfaced as related news for 定穎投控(3715).
A numeric code now only counts as an identity hit in stock context: parenthesized
(3715)/（3715）, or text containing CJK characters (TW/CN codes appear in zh news).
"""

from src.search_service import SearchService, SearchResult


def _ss():
    return SearchService()


def test_bare_numeric_code_in_foreign_prose_is_not_a_code_hit():
    ss = _ss()
    mining = SearchResult(
        title="Sandvik drill electrification journey continues with Commando DC310Rie",
        snippet="The new rig delivers 3715 units of torque and operates at depth; mining productivity.",
        url="https://im-mining.com/2026/06/11/sandviks-drill-electrification-commando-dc310rie/",
        source="im-mining.com",
    )
    scored = ss._score_news_relevance(mining, stock_code="3715", stock_name="定穎投控")
    assert scored.relevance_score == 0
    assert scored.relevance_category != SearchService._DIRECT_NEWS_CATEGORY
    # no POSITIVE code hit (the "未命中股票代码..." downgrade reason is expected and fine)
    assert not any("命中股票代码 3715" in r for r in (scored.relevance_reasons or []))


def test_contains_stock_code_identity_term_numeric_rules():
    f = SearchService._contains_stock_code_identity_term
    # bare number in English prose -> not a hit
    assert f("delivers 3715 units of torque", "3715") is False
    # parenthesized -> hit (works even in English: "Holdings (3715)")
    assert f("Define Holdings (3715) reports earnings", "3715") is True
    assert f("定穎投控（3715）法說會", "3715") is True
    # bare number inside Chinese stock news -> hit (TW/CN codes live in zh news)
    assert f("3715 定穎投控 單月新高", "3715") is True
    # embedded in a larger alnum token -> still not a hit (token boundary)
    assert f("model DC3715X spec", "3715") is False


def test_zh_news_and_company_name_still_score_high():
    ss = _ss()
    zh = SearchResult(
        title="3715 定穎投控 - PCB廠5月成績單單月新高",
        snippet="定穎投控單月新高，法人看好下半年",
        url="https://news.google.com/rss/articles/abc",
        source="工商時報",
    )
    scored = ss._score_news_relevance(zh, stock_code="3715", stock_name="定穎投控")
    assert scored.relevance_score >= 45
    assert scored.relevance_category == SearchService._DIRECT_NEWS_CATEGORY


def test_english_parenthesized_code_still_recognized():
    ss = _ss()
    en = SearchResult(
        title="Define Holdings (3715) reports Q2 earnings beat",
        snippet="TPEx-listed (3715) revenue rose on PCB demand",
        url="https://example.com/x",
        source="Reuters",
    )
    scored = ss._score_news_relevance(en, stock_code="3715", stock_name="定穎投控")
    assert scored.relevance_score > 0
    assert any("代码" in r for r in (scored.relevance_reasons or []))
