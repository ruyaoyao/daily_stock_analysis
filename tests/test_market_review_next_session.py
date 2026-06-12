# -*- coding: utf-8 -*-
"""Regression: market-review must not say literal 「明日」 when the next session is
not the next calendar day (weekend/holiday).

Bug: a Friday 大盤覆盤 wrote "明日優先觀察…" but TW is closed on Saturday. The
template now resolves the next *trading* session and uses an explicit date when
it isn't tomorrow.
"""

import datetime as dt
from unittest.mock import patch

from src.market_analyzer import MarketAnalyzer, MarketOverview


def test_phrase_is_mingri_when_next_session_is_tomorrow():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-10", trade_date="2026-06-10")
    with patch("src.market_analyzer.next_trading_session", return_value=dt.date(2026, 6, 11)):
        phrase, note = a._next_session_context(ov)
    assert phrase == "明日"
    assert note == ""


def test_phrase_uses_explicit_date_when_next_session_after_weekend():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-12", trade_date="2026-06-12")  # Friday
    with patch("src.market_analyzer.next_trading_session", return_value=dt.date(2026, 6, 15)):
        phrase, note = a._next_session_context(ov)
    assert "2026-06-15" in phrase and "週一" in phrase
    assert "明日" not in phrase
    assert note and "2026-06-15" in note


def test_fallback_phrase_when_calendar_unavailable():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-12", trade_date="2026-06-12")
    with patch("src.market_analyzer.next_trading_session", return_value=None):
        phrase, note = a._next_session_context(ov)
    assert phrase == "下一交易日"
    assert note == ""


def test_prompt_has_no_bare_mingri_header_before_holiday():
    a = MarketAnalyzer(region="tw")
    ov = MarketOverview(date="2026-06-12", trade_date="2026-06-12")
    with patch("src.market_analyzer.next_trading_session", return_value=dt.date(2026, 6, 15)):
        p = a._build_review_prompt(ov, [])
    # the hardcoded 「明日交易計劃」 / 「明日優先觀察」 headers must be resolved to the next session
    assert "明日交易計劃" not in p
    assert "明日優先觀察" not in p
    assert "下一交易日（2026-06-15 週一）交易計劃" in p


def test_english_review_uses_next_session_phrase():
    a = MarketAnalyzer(region="us")
    ov = MarketOverview(date="2026-06-12", trade_date="2026-06-12")
    with patch.object(a, "_get_review_language", return_value="en"), \
         patch("src.market_analyzer.next_trading_session", return_value=dt.date(2026, 6, 15)):
        phrase, note = a._next_session_context(ov)
    assert "next session (2026-06-15" in phrase
    assert note and "next trading session is 2026-06-15" in note
