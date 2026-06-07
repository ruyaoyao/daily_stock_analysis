# -*- coding: utf-8 -*-
"""台股代码路由 / 市场标签 / 交易日历 / 大盘复盘区域 的离线单测。"""

import pytest

from data_provider.base import (
    normalize_stock_code,
    _market_tag,
    is_tw_stock_code,
    _is_hk_market,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("tw2330", "TW2330"),
        ("TW2330", "TW2330"),
        ("tw0050", "TW0050"),
        ("tw00878", "TW00878"),
        ("2330.TW", "TW2330"),
        ("6271.TWO", "TW6271"),
    ],
)
def test_normalize_tw_codes(raw, expected):
    assert normalize_stock_code(raw) == expected


def test_normalize_does_not_break_existing_markets():
    assert normalize_stock_code("SH600519") == "600519"
    assert normalize_stock_code("hk00700") == "HK00700"
    assert normalize_stock_code("AAPL") == "AAPL"  # 美股 ticker 不变
    # 以 TW 开头但非纯数字的美股 ticker 不应被当作台股
    assert normalize_stock_code("TWLO") == "TWLO"


@pytest.mark.parametrize(
    "code,expected",
    [
        ("tw2330", True),
        ("TW00878", True),
        ("2330.TW", True),
        ("6271.TWO", True),
        ("600519", False),  # A 股 6 位
        ("00700", False),   # 港股 5 位
        ("AAPL", False),
        ("TWLO", False),    # 美股 ticker，TW 后非数字
    ],
)
def test_is_tw_stock_code(code, expected):
    assert is_tw_stock_code(code) is expected


def test_market_tag_priority():
    assert _market_tag("TW2330") == "tw"
    assert _market_tag("600519") == "cn"
    assert _market_tag("HK00700") == "hk"
    assert _market_tag("AAPL") == "us"
    # 台股 5 位 ETF 不应被港股 5 位数字规则吞掉（因带 TW 前缀，非纯数字）
    assert _is_hk_market("TW00878") is False


def test_daily_fetcher_support_table_routes_tw_only_to_shioaji():
    from data_provider.base import DataFetcherManager

    support = DataFetcherManager._DAILY_MARKET_FETCHER_SUPPORT
    assert support["ShioajiTwFetcher"] == {"tw"}
    # 既有内建源都不支持 tw（确保 tw 日线只走 Shioaji）
    for name, markets in support.items():
        if name != "ShioajiTwFetcher":
            assert "tw" not in markets


def test_get_market_for_stock_tw():
    from src.core.trading_calendar import get_market_for_stock

    assert get_market_for_stock("tw2330") == "tw"
    assert get_market_for_stock("TW00878") == "tw"
    assert get_market_for_stock("600519") == "cn"
    assert get_market_for_stock("HK00700") == "hk"


def test_compute_effective_region_tw():
    from src.core.trading_calendar import compute_effective_region

    assert compute_effective_region("tw", {"tw", "cn"}) == "tw"
    assert compute_effective_region("tw", {"cn", "us"}) == ""  # tw 未开市则跳过
    # both 仍仅含 cn+hk+us，不静默纳入 tw
    assert "tw" not in compute_effective_region("both", {"cn", "hk", "us", "tw"})


def test_market_review_both_excludes_tw():
    from src.core.market_review import _resolve_market_review_regions

    assert _resolve_market_review_regions("both") == ["cn", "hk", "us"]
    assert _resolve_market_review_regions("tw") == ["tw"]
    assert _resolve_market_review_regions("cn,tw") == ["cn", "tw"]


def test_profile_and_strategy_have_tw():
    from src.core.market_profile import get_profile
    from src.core.market_strategy import get_market_strategy_blueprint

    assert get_profile("tw").region == "tw"
    assert get_profile("tw").mood_index_code == "TWII"
    assert get_market_strategy_blueprint("tw").region == "tw"


def test_config_market_review_region_accepts_tw():
    from src.config import Config

    assert Config._parse_market_review_region("tw") == "tw"
    assert Config._parse_market_review_region("TW") == "tw"
    assert Config._parse_market_review_region("invalid") == "cn"


class _FakeMarketConfig:
    """Minimal stand-in for Config carrying per-market enable flags."""

    def __init__(self, cn=True, hk=True, us=True, tw=True):
        self.market_cn_enabled = cn
        self.market_hk_enabled = hk
        self.market_us_enabled = us
        self.market_tw_enabled = tw


def test_get_enabled_markets():
    from src.core.trading_calendar import get_enabled_markets

    assert get_enabled_markets(_FakeMarketConfig()) == {"cn", "hk", "us", "tw"}
    assert get_enabled_markets(_FakeMarketConfig(cn=False)) == {"hk", "us", "tw"}
    assert get_enabled_markets(_FakeMarketConfig(cn=False, hk=False, us=False, tw=False)) == set()


def test_filter_codes_by_enabled_markets_drops_disabled_keeps_unknown():
    from src.core.trading_calendar import filter_codes_by_enabled_markets

    codes = ["600519", "HK00700", "AAPL", "tw2330", "WEIRD$$"]
    # Disable A-share only
    kept, skipped = filter_codes_by_enabled_markets(codes, _FakeMarketConfig(cn=False))
    assert "600519" in skipped
    assert "HK00700" in kept and "AAPL" in kept and "tw2330" in kept
    # Unknown-market code is kept (fail-open)
    assert "WEIRD$$" in kept


def test_market_review_regions_filtered_by_enabled():
    from src.core.market_review import _resolve_market_review_regions

    # tw disabled -> dropped
    assert _resolve_market_review_regions("tw", enabled_markets={"cn", "hk", "us"}) == []
    # both with cn disabled -> only hk, us
    assert _resolve_market_review_regions("both", enabled_markets={"hk", "us", "tw"}) == ["hk", "us"]
    # no enablement filter -> unchanged
    assert _resolve_market_review_regions("tw") == ["tw"]
