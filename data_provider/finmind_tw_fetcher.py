# -*- coding: utf-8 -*-
"""
FinMind / TDCC Taiwan chip distribution fetcher.

Uses TDCC open data (集保戶股權分散表) for holder concentration and FinMind or
yfinance for price-based avg_cost / profit_ratio proxies.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple

import pandas as pd
import requests

from .base import BaseFetcher, DataFetchError, _is_tw_market
from .realtime_types import ChipDistribution
from .tdcc_opendata import (
    compute_chip_metrics_from_tiers,
    get_shareholding_tiers,
    normalize_tdcc_stock_code,
)

logger = logging.getLogger(__name__)

_FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"


class FinMindTwFetcher(BaseFetcher):
    """Taiwan chip distribution via TDCC (+ optional FinMind price history)."""

    name = "FinMindTwFetcher"
    priority = int(os.getenv("FINMIND_TW_PRIORITY", "2"))

    def __init__(self) -> None:
        from src.config import get_config

        config = get_config()
        self._token = (getattr(config, "finmind_token", None) or os.getenv("FINMIND_TOKEN") or "").strip()

    def is_available_for_request(self, capability: str = "") -> bool:
        return True

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise DataFetchError(f"[{self.name}] daily data is not supported; use ShioajiTwFetcher")

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        raise DataFetchError(f"[{self.name}] daily data is not supported; use ShioajiTwFetcher")

    def get_chip_distribution(self, stock_code: str) -> Optional[ChipDistribution]:
        if not _is_tw_market(stock_code):
            return None

        bare_code = normalize_tdcc_stock_code(stock_code)
        distribution = get_shareholding_tiers(bare_code)
        if not distribution:
            return None

        current_price, avg_cost = self._fetch_price_stats(bare_code)
        if current_price <= 0 or avg_cost <= 0:
            logger.warning("[FinMindTwFetcher] %s 缺少有效价格，无法计算筹码成本", bare_code)
            return None

        metrics = compute_chip_metrics_from_tiers(
            distribution["tiers"],
            current_price=current_price,
            avg_cost=avg_cost,
        )
        (
            profit_ratio,
            avg_cost_value,
            cost_90_low,
            cost_90_high,
            concentration_90,
            cost_70_low,
            cost_70_high,
            concentration_70,
        ) = metrics

        source = "tdcc+finmind" if self._token else "tdcc+yfinance"
        chip = ChipDistribution(
            code=f"TW{bare_code}",
            date=distribution.get("date") or "",
            source=source,
            profit_ratio=profit_ratio,
            avg_cost=avg_cost_value,
            cost_90_low=cost_90_low,
            cost_90_high=cost_90_high,
            concentration_90=concentration_90,
            cost_70_low=cost_70_low,
            cost_70_high=cost_70_high,
            concentration_70=concentration_70,
        )
        logger.info(
            "[筹码分布] TW%s 日期=%s: 获利比例=%.1%%, 平均成本=%.2f, 90%%集中度=%.2%%, 来源=%s",
            bare_code,
            chip.date,
            chip.profit_ratio,
            chip.avg_cost,
            chip.concentration_90,
            chip.source,
        )
        return chip

    def _fetch_price_stats(self, bare_code: str) -> Tuple[float, float]:
        if self._token:
            stats = self._fetch_finmind_price_stats(bare_code)
            if stats is not None:
                return stats
        return self._fetch_yfinance_price_stats(bare_code)

    def _fetch_finmind_price_stats(self, bare_code: str) -> Optional[Tuple[float, float]]:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
        try:
            response = requests.get(
                _FINMIND_API_URL,
                params={
                    "dataset": "TaiwanStockPrice",
                    "data_id": bare_code,
                    "start_date": start_date,
                    "end_date": end_date,
                },
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.info("[FinMindTwFetcher] FinMind 价格查询失败 %s: %s", bare_code, exc)
            return None

        rows = payload.get("data") or []
        if not rows:
            return None

        closes = []
        volumes = []
        for row in rows:
            close = row.get("close")
            volume = row.get("Trading_Volume")
            try:
                close_value = float(close)
                volume_value = float(volume)
            except (TypeError, ValueError):
                continue
            if close_value <= 0 or volume_value <= 0:
                continue
            closes.append(close_value)
            volumes.append(volume_value)

        if not closes:
            return None

        current_price = closes[-1]
        total_volume = sum(volumes)
        avg_cost = sum(c * v for c, v in zip(closes, volumes)) / total_volume if total_volume else current_price
        return current_price, avg_cost

    def _fetch_yfinance_price_stats(self, bare_code: str) -> Tuple[float, float]:
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("[FinMindTwFetcher] 未安装 yfinance，无法估算台股筹码成本")
            return 0.0, 0.0

        symbol = f"{bare_code}.TW"
        try:
            history = yf.Ticker(symbol).history(period="3mo")
        except Exception as exc:
            logger.info("[FinMindTwFetcher] yfinance 查询失败 %s: %s", symbol, exc)
            return 0.0, 0.0

        if history is None or history.empty:
            return 0.0, 0.0

        closes = history["Close"].astype(float)
        volumes = history["Volume"].astype(float)
        valid = (closes > 0) & (volumes > 0)
        closes = closes[valid]
        volumes = volumes[valid]
        if closes.empty:
            return 0.0, 0.0

        current_price = float(closes.iloc[-1])
        total_volume = float(volumes.sum())
        avg_cost = float((closes * volumes).sum() / total_volume) if total_volume else current_price
        return current_price, avg_cost
