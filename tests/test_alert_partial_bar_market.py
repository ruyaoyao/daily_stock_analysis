# -*- coding: utf-8 -*-
"""Market-aware partial-bar cutoff in alert indicator normalization.

Regression for the timezone-naive 16:00 cutoff: the "is today a closed bar"
decision must use each market's local close time (TW closes 13:30 Taipei).
"""

from datetime import datetime

import pandas as pd

from src.services.alert_indicators import _drop_partial_today, normalize_ohlcv

TODAY = "2026-06-08"


def _df(last_date: str = TODAY) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-06-04", "2026-06-05", last_date]),
            "close": [100.0, 101.0, 102.0],
        }
    )


def test_tw_keeps_today_after_local_close():
    # 14:00 Taipei is after the 13:30 TW close -> today's bar is closed -> kept.
    out = _drop_partial_today(_df(), now=datetime(2026, 6, 8, 14, 0), market="tw")
    assert len(out) == 3


def test_tw_drops_today_before_local_close():
    # 13:00 Taipei is before the 13:30 TW close -> today's bar is partial -> dropped.
    out = _drop_partial_today(_df(), now=datetime(2026, 6, 8, 13, 0), market="tw")
    assert len(out) == 2
    assert out["date"].iloc[-1].strftime("%Y-%m-%d") == "2026-06-05"


def test_cn_close_time_differs_from_tw():
    # 14:00 is after TW close (kept) but before CN 15:00 close (dropped).
    assert len(_drop_partial_today(_df(), now=datetime(2026, 6, 8, 14, 0), market="cn")) == 2
    assert len(_drop_partial_today(_df(), now=datetime(2026, 6, 8, 14, 0), market="tw")) == 3


def test_default_market_keeps_legacy_1600_cutoff():
    # No market -> legacy 16:00 cutoff preserved.
    assert len(_drop_partial_today(_df(), now=datetime(2026, 6, 8, 16, 30))) == 3
    assert len(_drop_partial_today(_df(), now=datetime(2026, 6, 8, 15, 0))) == 2


def test_normalize_ohlcv_threads_market():
    out = normalize_ohlcv(
        _df(), required_columns=("close",), now=datetime(2026, 6, 8, 14, 0), market="tw"
    )
    assert len(out) == 3  # TW closed by 14:00, today's bar retained
