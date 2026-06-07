# -*- coding: utf-8 -*-
"""ShioajiTwFetcher 离线单测：以假 session 替换真实 Shioaji 连线，不触网、不依赖 shioaji 套件。"""

import pandas as pd
import pytest

from data_provider.shioaji_tw_fetcher import ShioajiTwFetcher, _strip_tw_code
from data_provider.realtime_types import RealtimeSource


class _FakeContract:
    def __init__(self, name="台積電", exchange="TSE"):
        self.name = name
        self.exchange = exchange


class _FakeSnapshot:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeApi:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    def snapshots(self, contracts):
        return [self._snapshot]


class _FakeSession:
    def __init__(self, contract=None, api=None):
        self._contract = contract
        self._api = api

    def resolve_contract(self, bare_code):
        return self._contract

    def get_api(self):
        return self._api


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("tw2330", "2330"),
        ("TW2330", "2330"),
        ("2330.TW", "2330"),
        ("tw00878", "00878"),
        ("6271.TWO", "6271"),
        ("2330", "2330"),
    ],
)
def test_strip_tw_code(raw, expected):
    assert _strip_tw_code(raw) == expected


def test_normalize_data_resamples_minute_kbars_to_daily():
    fetcher = ShioajiTwFetcher()
    # 两个交易日，各两根 1 分钟 K（验证 open=first/high=max/low=min/close=last/volume=sum）
    ts = [
        pd.Timestamp("2024-01-15 09:00:00").value,
        pd.Timestamp("2024-01-15 09:01:00").value,
        pd.Timestamp("2024-01-16 09:00:00").value,
        pd.Timestamp("2024-01-16 09:01:00").value,
    ]
    raw = pd.DataFrame(
        {
            "ts": ts,
            "Open": [100.0, 101.0, 110.0, 111.0],
            "High": [102.0, 103.0, 112.0, 113.0],
            "Low": [99.0, 100.5, 109.0, 110.5],
            "Close": [101.0, 102.0, 111.0, 112.5],
            "Volume": [10, 20, 30, 40],
        }
    )
    out = fetcher._normalize_data(raw, "TW2330")
    assert list(out["date"].dt.strftime("%Y-%m-%d")) == ["2024-01-15", "2024-01-16"]
    day1 = out.iloc[0]
    assert day1["open"] == 100.0
    assert day1["high"] == 103.0
    assert day1["low"] == 99.0
    assert day1["close"] == 102.0
    assert day1["volume"] == 30
    day2 = out.iloc[1]
    assert day2["open"] == 110.0 and day2["close"] == 112.5 and day2["volume"] == 70


def test_get_realtime_quote_maps_snapshot_fields():
    snap = _FakeSnapshot(
        close=580.0,
        change_price=5.0,
        change_rate=0.87,
        total_volume=30000,
        total_amount=17_400_000.0,
        open=575.0,
        high=582.0,
        low=574.0,
    )
    fetcher = ShioajiTwFetcher()
    fetcher._session = _FakeSession(contract=_FakeContract(), api=_FakeApi(snap))

    quote = fetcher.get_realtime_quote("tw2330")
    assert quote is not None
    assert quote.code == "TW2330"
    assert quote.name == "台積電"
    assert quote.source == RealtimeSource.SHIOAJI
    assert quote.price == 580.0
    assert quote.change_amount == 5.0
    assert quote.change_pct == 0.87
    assert quote.pre_close == 575.0
    assert quote.volume == 30000
    assert quote.open_price == 575.0


def test_get_realtime_quote_returns_none_when_no_contract():
    fetcher = ShioajiTwFetcher()
    fetcher._session = _FakeSession(contract=None, api=None)
    assert fetcher.get_realtime_quote("tw9999") is None


def test_get_stock_name_from_contract():
    fetcher = ShioajiTwFetcher()
    fetcher._session = _FakeSession(contract=_FakeContract(name="聯發科"))
    assert fetcher.get_stock_name("tw2454") == "聯發科"


def test_get_main_indices_not_provided_by_fetcher():
    # 台股大盘指数由 yfinance ^TWII/^TWOII 提供，本 fetcher 返回 None
    assert ShioajiTwFetcher().get_main_indices(region="tw") is None
