# -*- coding: utf-8 -*-
"""Regression guard: per-stock TWSE/TPEx date window must try TODAY first.

History: _recent_trading_days() started from `today - 1`, so per-stock 三大法人 /
融資融券 never tried today and were permanently >=1 day stale even after the
post-close publish. It must start from today (and fall back before publish).
"""

import datetime as _dt
from unittest.mock import patch

from data_provider import twse_openapi as tw


def _patch_today(y, m, d):
    class _FixedDate(_dt.date):
        @classmethod
        def today(cls):
            return cls(y, m, d)
    return patch.object(tw, "date", _FixedDate)


def test_recent_trading_days_includes_today_first_on_weekday():
    # 2026-06-10 is a Wednesday -> today must be the first candidate.
    with _patch_today(2026, 6, 10):
        days = tw._recent_trading_days(3)
    assert days[0] == "20260610", "must try TODAY first (never regress to yesterday-only)"
    assert days == ["20260610", "20260609", "20260608"]


def test_recent_trading_days_skips_weekend_to_friday():
    # 2026-06-13 is a Saturday -> latest trading day is Friday 06-12.
    with _patch_today(2026, 6, 13):
        days = tw._recent_trading_days(2)
    assert days[0] == "20260612"
    assert "20260613" not in days and "20260614" not in days
