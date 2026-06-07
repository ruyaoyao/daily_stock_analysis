# -*- coding: utf-8 -*-
"""
===================================
台股数据源 - 永丰金 Shioaji
===================================

职责：
1. 通过 Shioaji（永丰金 sinopac-shioaji）获取台股行情：
   - 日线 K 线（由 1 分钟 kbars 重采样为日线）
   - 实时快照（snapshot）
   - 个股名称 / 交易所归属（上市 TSE / 上柜 OTC）
2. 通过 TWSE / TPEx OpenAPI 提供三大法人买卖超与融资融券余额（见 twse_openapi）

设计要点：
- `shioaji` 为可选依赖：本模块顶层不导入 shioaji，登录所需的导入全部延迟到方法内部，
  以便在未安装 shioaji 时仍可安全 import 本模块（data_provider/__init__ 会顶层导入它）。
- 仅在配置了 SHIOAJI_API_KEY / SHIOAJI_SECRET_KEY 时由 DataFetcherManager 实例化，
  并采用懒登录：首次需要行情时才建立连线，连线在进程内复用（单一 person_id 最多 5 条连线）。
- 单一数据源失败不应中断整体流程：实时/名称类查询失败返回 None，日线失败抛出由上层捕获。

代码路由：输入需带显式 `TW` 前缀（如 `tw2330`、`tw00878`），归一化为 `TW2330`，
本 fetcher 去除前缀后用裸代码（`2330`）向 Shioaji 查询合约。
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from .base import BaseFetcher, DataFetchError
from .realtime_types import RealtimeSource, UnifiedRealtimeQuote

logger = logging.getLogger(__name__)


def _strip_tw_code(stock_code: str) -> str:
    """将 `TW2330` / `tw2330` / `2330.TW` 等归一化为裸代码 `2330`。"""
    code = (stock_code or "").strip().upper()
    if code.endswith(".TWO"):
        code = code[:-4]
    elif code.endswith(".TW"):
        code = code[:-3]
    if code.startswith("TW"):
        candidate = code[2:]
        if candidate.isdigit():
            return candidate
    return code


class _ShioajiSession:
    """进程内单例 Shioaji 连线管理器（懒登录 + 复用 + 线程安全）。"""

    _instance: Optional["_ShioajiSession"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._api = None
        self._login_lock = threading.RLock()
        self._login_failed = False

    @classmethod
    def instance(cls) -> "_ShioajiSession":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_api(self):
        """返回已登录的 Shioaji api 实例；未登录则懒登录。失败返回 None。"""
        if self._api is not None:
            return self._api
        with self._login_lock:
            if self._api is not None:
                return self._api
            if self._login_failed:
                return None
            api = self._do_login()
            if api is None:
                # 标记失败，避免每次查询都重复尝试登录（耗时且消耗每日登录额度）
                self._login_failed = True
            self._api = api
            return api

    def _do_login(self):
        from src.config import get_config

        config = get_config()
        api_key = (getattr(config, "shioaji_api_key", None) or "").strip()
        secret_key = (getattr(config, "shioaji_secret_key", None) or "").strip()
        if not api_key or not secret_key:
            logger.warning("[ShioajiTwFetcher] 未配置 SHIOAJI_API_KEY / SHIOAJI_SECRET_KEY，跳过登录")
            return None

        simulation = bool(getattr(config, "shioaji_simulation", False))

        try:
            import shioaji as sj
        except ImportError:
            logger.warning(
                "[ShioajiTwFetcher] 未安装 shioaji，无法获取台股行情。请执行 pip install shioaji"
            )
            return None

        try:
            api = sj.Shioaji(simulation=simulation)
            api.login(api_key=api_key, secret_key=secret_key)
            logger.info("[ShioajiTwFetcher] 登录成功 (simulation=%s)", simulation)
        except Exception as e:
            logger.warning("[ShioajiTwFetcher] 登录失败: %s", e)
            return None

        # CA 凭证为可选项：仅下单需要，查询行情不需要。配置了则尝试启用，失败不阻断查询。
        ca_path = (getattr(config, "shioaji_ca_path", None) or "").strip()
        ca_passwd = (getattr(config, "shioaji_ca_password", None) or "").strip()
        person_id = (getattr(config, "shioaji_person_id", None) or "").strip()
        if ca_path and ca_passwd:
            try:
                kwargs = {"ca_path": ca_path, "ca_passwd": ca_passwd}
                if person_id:
                    kwargs["person_id"] = person_id
                api.activate_ca(**kwargs)
                logger.info("[ShioajiTwFetcher] CA 凭证已启用")
            except Exception as e:
                logger.warning("[ShioajiTwFetcher] CA 凭证启用失败（不影响行情查询）: %s", e)

        return api

    def resolve_contract(self, bare_code: str):
        """解析合约：先试统一查询，再依次试 TSE / OTC。失败返回 None。"""
        api = self.get_api()
        if api is None:
            return None
        try:
            contract = api.Contracts.Stocks[bare_code]
            if contract is not None:
                return contract
        except Exception:
            pass
        for board in ("TSE", "OTC"):
            try:
                store = getattr(api.Contracts.Stocks, board, None)
                if store is None:
                    continue
                contract = store[bare_code]
                if contract is not None:
                    return contract
            except Exception:
                continue
        return None


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    f = _to_float(value)
    return int(f) if f is not None else None


class ShioajiTwFetcher(BaseFetcher):
    """永丰金 Shioaji 台股数据源。"""

    name: str = "ShioajiTwFetcher"
    priority: int = 6  # 低于美股/港股专用源，仅服务 tw 市场

    def __init__(self) -> None:
        self._session = _ShioajiSession.instance()

    # ------------------------------------------------------------------
    # 可用性探测：仅在配置了 Shioaji 凭据时认为可用（避免无效探测）
    # ------------------------------------------------------------------
    def is_available_for_request(self, capability: str = "") -> bool:
        try:
            from src.config import get_config

            config = get_config()
        except Exception:
            return False
        api_key = (getattr(config, "shioaji_api_key", None) or "").strip()
        secret_key = (getattr(config, "shioaji_secret_key", None) or "").strip()
        return bool(api_key and secret_key)

    # ------------------------------------------------------------------
    # 日线：Shioaji 提供 1 分钟 kbars，重采样为日线 OHLCV
    # ------------------------------------------------------------------
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        bare = _strip_tw_code(stock_code)
        contract = self._session.resolve_contract(bare)
        if contract is None:
            raise DataFetchError(f"[{self.name}] 未找到台股合约: {bare}")
        api = self._session.get_api()
        if api is None:
            raise DataFetchError(f"[{self.name}] Shioaji 未登录")

        kbars = api.kbars(contract, start=start_date, end=end_date)
        try:
            raw = pd.DataFrame({**kbars})
        except Exception as e:
            raise DataFetchError(f"[{self.name}] kbars 解析失败: {e}") from e
        if raw is None or raw.empty:
            raise DataFetchError(f"[{self.name}] {bare} kbars 为空")
        return raw

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """将 1 分钟 kbars 重采样为日线：date/open/high/low/close/volume。"""
        if df is None or df.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

        work = df.copy()
        # ts 为纳秒级时间戳
        if "ts" not in work.columns:
            raise DataFetchError(f"[{self.name}] kbars 缺少 ts 列")
        work["datetime"] = pd.to_datetime(work["ts"], unit="ns")
        work["date"] = work["datetime"].dt.normalize()

        agg = (
            work.groupby("date")
            .agg(
                open=("Open", "first"),
                high=("High", "max"),
                low=("Low", "min"),
                close=("Close", "last"),
                volume=("Volume", "sum"),
            )
            .reset_index()
        )
        agg = agg.sort_values("date").reset_index(drop=True)
        return agg

    # ------------------------------------------------------------------
    # 实时快照
    # ------------------------------------------------------------------
    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        bare = _strip_tw_code(stock_code)
        try:
            contract = self._session.resolve_contract(bare)
            if contract is None:
                logger.info("[ShioajiTwFetcher] 未找到合约: %s", bare)
                return None
            api = self._session.get_api()
            if api is None:
                return None
            snapshots = api.snapshots([contract])
        except Exception as e:
            logger.info("[ShioajiTwFetcher] 快照获取失败 %s: %s", bare, e)
            return None

        if not snapshots:
            return None
        snap = snapshots[0]

        close = _to_float(getattr(snap, "close", None))
        change_amount = _to_float(getattr(snap, "change_price", None))
        change_pct = _to_float(getattr(snap, "change_rate", None))
        pre_close = None
        if close is not None and change_amount is not None:
            pre_close = round(close - change_amount, 4)

        quote = UnifiedRealtimeQuote(
            code=f"TW{bare}",
            name=str(getattr(contract, "name", "") or ""),
            source=RealtimeSource.SHIOAJI,
            price=close,
            change_pct=change_pct,
            change_amount=change_amount,
            volume=_to_int(getattr(snap, "total_volume", None)),
            amount=_to_float(getattr(snap, "total_amount", None)),
            open_price=_to_float(getattr(snap, "open", None)),
            high=_to_float(getattr(snap, "high", None)),
            low=_to_float(getattr(snap, "low", None)),
            pre_close=pre_close,
        )
        return quote if quote.has_basic_data() else None

    # ------------------------------------------------------------------
    # 个股名称
    # ------------------------------------------------------------------
    def get_stock_name(self, stock_code: str) -> Optional[str]:
        bare = _strip_tw_code(stock_code)
        try:
            contract = self._session.resolve_contract(bare)
            if contract is None:
                return None
            name = getattr(contract, "name", None)
            return str(name) if name else None
        except Exception as e:
            logger.debug("[ShioajiTwFetcher] 获取名称失败 %s: %s", bare, e)
            return None

    # ------------------------------------------------------------------
    # 大盘指数：台股大盘（加权 / 柜买）由 yfinance ^TWII/^TWOII 提供，本源不实现
    # ------------------------------------------------------------------
    def get_main_indices(self, region: str = "cn") -> Optional[List[Dict[str, Any]]]:
        return None

    # ------------------------------------------------------------------
    # 三大法人买卖超 / 融资融券余额：经 TWSE / TPEx OpenAPI（无需 Shioaji 凭据）
    # ------------------------------------------------------------------
    def _market_hint(self, bare_code: str) -> Optional[str]:
        """由 Shioaji 合约的交易所推断 OpenAPI 市场（TSE=上市 / OTC=上柜）。"""
        try:
            contract = self._session.resolve_contract(bare_code)
            exchange = str(getattr(contract, "exchange", "") or "").upper()
            if "OTC" in exchange:
                return "OTC"
            if "TSE" in exchange:
                return "TSE"
        except Exception:
            pass
        return None

    def get_institutional_investors(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """三大法人（外资/投信/自营商）买卖超。失败返回 None，不中断主流程。"""
        bare = _strip_tw_code(stock_code)
        try:
            from .twse_openapi import get_institutional_investors as _fn
        except Exception as e:
            logger.debug("[ShioajiTwFetcher] twse_openapi 不可用: %s", e)
            return None
        try:
            return _fn(bare, market=self._market_hint(bare))
        except Exception as e:
            logger.info("[ShioajiTwFetcher] 三大法人查询失败 %s: %s", bare, e)
            return None

    def get_margin_balance(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """融资融券余额。失败返回 None，不中断主流程。"""
        bare = _strip_tw_code(stock_code)
        try:
            from .twse_openapi import get_margin_balance as _fn
        except Exception as e:
            logger.debug("[ShioajiTwFetcher] twse_openapi 不可用: %s", e)
            return None
        try:
            return _fn(bare, market=self._market_hint(bare))
        except Exception as e:
            logger.info("[ShioajiTwFetcher] 融资融券查询失败 %s: %s", bare, e)
            return None
