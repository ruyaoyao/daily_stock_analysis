# -*- coding: utf-8 -*-
"""Cross-source date-consistency guard + region-aware turnover labels (market review)."""

import pytest

from src.market_analyzer import MarketAnalyzer, MarketOverview


@pytest.fixture
def tw():
    return MarketAnalyzer(region="tw")


@pytest.fixture
def cn():
    return MarketAnalyzer(region="cn")


# --- date-consistency guard ---

def test_resolve_consistent_dates_anchors_on_index(tw):
    ov = MarketOverview(date="2026-06-10")
    ov.source_dates = {"index": "2026-06-10", "breadth": "2026-06-10", "margin": "2026-06-10"}
    tw._resolve_trade_date_consistency(ov)
    assert ov.trade_date == "2026-06-10"
    assert ov.data_date_inconsistent is False
    assert tw._build_data_date_note(ov) == "資料日期：2026-06-10"


def test_resolve_flags_divergent_dates(tw):
    ov = MarketOverview(date="2026-06-10")
    ov.source_dates = {"index": "2026-06-10", "breadth": "2026-06-09", "margin": "2026-06-10"}
    tw._resolve_trade_date_consistency(ov)
    assert ov.trade_date == "2026-06-10"          # anchored on index
    assert ov.data_date_inconsistent is True
    note = tw._build_data_date_note(ov)
    assert "不一致" in note and "breadth=2026-06-09" in note


def test_resolve_noop_without_dates(tw):
    ov = MarketOverview(date="2026-06-10")
    tw._resolve_trade_date_consistency(ov)
    assert ov.trade_date is None and ov.data_date_inconsistent is False
    assert tw._build_data_date_note(ov) == ""


# --- region-aware turnover label + activity descriptor ---

def test_turnover_label_region_aware(tw, cn):
    assert tw._get_turnover_total_label() == "上市成交額"   # TW: not 兩市, and TWSE-only scope
    assert cn._get_turnover_total_label() == "兩市成交額"


def test_describe_turnover_region_thresholds(tw, cn):
    # 14,241 億 on a crash day -> 高活躍度 for TW, but only 中等活躍 under A-share thresholds
    assert tw._describe_turnover(14241) == "高活躍度"
    assert cn._describe_turnover(14241) == "中等活躍"
    assert tw._describe_turnover(0) == "暫無數據"
