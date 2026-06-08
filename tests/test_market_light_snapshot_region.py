# -*- coding: utf-8 -*-
"""MarketLightSnapshot must accept the Taiwan region.

Regression: TW market review (MARKET_REVIEW_REGION=tw) builds
MarketLightSnapshot(region='tw'); the schema previously only allowed
cn/hk/us, so review crashed with "大盘复盘未返回可持久化报告".
"""

import pytest
from pydantic import ValidationError

from src.schemas.market_light import (
    MarketLightDimension,
    MarketLightDimensions,
    MarketLightSnapshot,
)


def _dims() -> MarketLightDimensions:
    d = MarketLightDimension(score=50, available=True)
    return MarketLightDimensions(breadth=d, index=d, limit=d)


def _snapshot(region: str) -> MarketLightSnapshot:
    return MarketLightSnapshot(
        region=region,
        trade_date="2026-06-08",
        status="yellow",
        score=55,
        label="偏多",
        temperature_label="温和",
        reasons=["指数走强"],
        guidance="谨慎偏多",
        dimensions=_dims(),
        data_quality="partial",
    )


@pytest.mark.parametrize("region", ["cn", "hk", "us", "tw"])
def test_supported_regions_validate(region):
    assert _snapshot(region).region == region


def test_unknown_region_rejected():
    with pytest.raises(ValidationError):
        _snapshot("jp")
