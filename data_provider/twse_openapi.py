# -*- coding: utf-8 -*-
"""
TWSE / TPEx 三大法人与融资融券公开 API 适配器（无需 API Key）。

数据来源:
  TSE（上市）三大法人:
    https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date=YYYYMMDD&selectType=ALL
    stat/date/fields/data 格式。fields 共 19 个字段（含证券代号/名称后的18个数值列）：
      [0]  证券代号
      [1]  证券名称
      [2]  外陆资买进股数(不含外资自营商)
      [3]  外陆资卖出股数(不含外资自营商)
      [4]  外陆资买卖超股数(不含外资自营商)   ← foreign_net 基础
      [5]  外资自营商买进股数
      [6]  外资自营商卖出股数
      [7]  外资自营商买卖超股数               ← 外资含自营商净额 = [4]+[7]
      [8]  投信买进股数
      [9]  投信卖出股数
      [10] 投信买卖超股数                     ← trust_net
      [11] 自营商买卖超股数（总计）            ← dealer_net
      [12] 自营商买进股数(自行买卖)
      [13] 自营商卖出股数(自行买卖)
      [14] 自营商买卖超股数(自行买卖)
      [15] 自营商买进股数(避险)
      [16] 自营商卖出股数(避险)
      [17] 自营商买卖超股数(避险)
      [18] 三大法人买卖超股数                 ← total_net

  TSE 融资融券（上市）:
    https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN （今日，无 date 参数）
    返回 list-of-dicts，字段名（与 rwd 相同含义，位置对齐）：
      股票代號、股票名称、融资买进、融资卖出、融资现金偿还、
      融资前日余额、融资今日余额、融资限额、
      融券买进、融券卖出、融券现券偿还、融券前日余额、融券今日余额、融券限额、
      资券互抵、注记
    备用（指定日期）: https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN
      ?response=json&date=YYYYMMDD&selectType=STOCK&stockNo=XXXX
      返回 tables 数组，tables[1] 包含 fields+data：
        [0]=代号 [1]=名称
        融资: [2]=买进 [3]=卖出 [4]=现金偿还 [5]=前日余额 [6]=今日余额 [7]=次一营业日限额
        融券: [8]=买进 [9]=卖出 [10]=现券偿还 [11]=前日余额 [12]=今日余额 [13]=次一营业日限额
        [14]=资券互抵 [15]=注记

  OTC（上柜）三大法人:
    https://www.tpex.org.tw/openapi/v1/tpex_mainboard_3big_traders_daily
    ⚠ 注意：此端点在非台湾地区（或某些环境）可能被 302 重定向至首页，
    届时本模块将静默返回 None。若未来端点恢复，list-of-dicts 结构待补充。

  OTC（上柜）融资融券:
    https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_transactions
    ⚠ 同上，302 重定向时返回 None。

所有函数:
  - 遇到任何异常均返回 None，不向调用方抛出异常。
  - 日志等级为 WARNING。
  - HTTP 请求携带 User-Agent: daily-stock-analysis/1.0，超时 10 秒。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_USER_AGENT = "daily-stock-analysis/1.0"
_TIMEOUT = 10  # seconds

# ─────────────────────────────────────────────────────────────────────────────
# 内部工具函数
# ─────────────────────────────────────────────────────────────────────────────


def _get_json(url: str, params: Optional[dict] = None) -> Any:
    """发起 GET 请求，返回解析后的 JSON 对象；任何失败均返回 None。"""
    if params:
        from urllib.parse import urlencode
        url = url + ("&" if "?" in url else "?") + urlencode(params)
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read()
            # 若响应是 HTML（如 TPEx 重定向至首页），直接返回 None
            stripped = raw.lstrip()
            if stripped[:1] not in (b"[", b"{"):
                logger.warning("twse_openapi: non-JSON response from %s (likely redirect)", url)
                return None
            return json.loads(raw.decode("utf-8"))
    except (HTTPError, URLError) as exc:
        logger.warning("twse_openapi: HTTP/URL error for %s: %s", url, exc)
    except Exception as exc:
        logger.warning("twse_openapi: unexpected error for %s: %s", url, exc)
    return None


def _normalize_stock_code(raw: str) -> str:
    """将各种格式统一为纯数字或字母代码（去除 TW/TWO 后缀及 TW 前缀）。

    例:
      'TW2330'  → '2330'
      'tw2330'  → '2330'
      '2330.TW' → '2330'
      '4958.TWO'→ '4958'
      '2330'    → '2330'
    """
    s = raw.strip()
    # 去除 .TW / .TWO 等证券后缀
    s = re.sub(r"\.(TW|TWO|TW0)$", "", s, flags=re.IGNORECASE)
    # 去除开头的 TW / tw 前缀（仅当后面是数字时）
    s = re.sub(r"^tw", "", s, flags=re.IGNORECASE)
    return s.strip()


def _safe_int(value: Any) -> Optional[int]:
    """Best-effort 整数转换（处理逗号分隔的千位格式、空字符串等）。"""
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace(" ", "")
    if not s or s in ("-", "－", "—"):
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    """Best-effort 浮点转换。"""
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace("%", "").replace(" ", "")
    if not s or s in ("-", "－", "—"):
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _recent_trading_days(n: int = 5) -> list[str]:
    """返回最近 n 个非周末日期（YYYYMMDD 格式），最新在前。"""
    days: list[str] = []
    d = date.today() - timedelta(days=1)
    while len(days) < n:
        if d.weekday() < 5:  # 0=Mon … 4=Fri
            days.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return days


def _format_date_yyyymmdd(raw_date: Optional[str]) -> Optional[str]:
    """将 TWSE 的 YYYYMMDD 格式日期转为 YYYY-MM-DD；若已是该格式则直接返回。"""
    if raw_date is None:
        return None
    s = str(raw_date).strip().replace("-", "").replace("/", "")
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# TSE（上市）三大法人
# ─────────────────────────────────────────────────────────────────────────────


def _fetch_tse_institutional(stock_code: str, date_str: Optional[str]) -> Optional[dict]:
    """
    从 TWSE rwd T86 获取单只上市股票的三大法人数据。

    端点: https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date=YYYYMMDD&selectType=ALL
    响应结构:
      stat: 'OK' | '很抱歉...'
      date: 'YYYYMMDD'
      fields: [19 个字段名称]
      data: [[...], [...], ...]   # 每行第 0 列为证券代号

    字段索引（以下均相对于单行 data[i]）:
      [0]  证券代号
      [4]  外陆资买卖超股数(不含外资自营商)  → foreign_net（不含外资自营商）
      [7]  外资自营商买卖超股数              → 加入以合计「外资含自营商」
      [10] 投信买卖超股数                    → trust_net
      [11] 自营商买卖超股数（总计）           → dealer_net
      [18] 三大法人买卖超股数                → total_net
    """
    base_url = "https://www.twse.com.tw/rwd/zh/fund/T86"

    dates_to_try: list[str]
    if date_str:
        dates_to_try = [date_str]
    else:
        dates_to_try = _recent_trading_days(5)

    for try_date in dates_to_try:
        data = _get_json(base_url, {"response": "json", "date": try_date, "selectType": "ALL"})
        if not data or data.get("stat") != "OK":
            continue
        rows = data.get("data") or []
        if not rows:
            continue

        for row in rows:
            if not row or str(row[0]).strip() != stock_code:
                continue

            # 索引越界保护
            if len(row) < 19:
                logger.warning(
                    "twse_openapi: T86 row for %s has only %d columns (expected 19)",
                    stock_code,
                    len(row),
                )
                return None

            foreign_excl = _safe_int(row[4])  # 外陆资(不含自营商)
            foreign_dealer = _safe_int(row[7])  # 外资自营商
            trust_net = _safe_int(row[10])
            dealer_net = _safe_int(row[11])
            total_net = _safe_int(row[18])

            # 外资净额 = 外陆资(不含外资自营商) + 外资自营商
            if foreign_excl is not None and foreign_dealer is not None:
                foreign_net = foreign_excl + foreign_dealer
            elif foreign_excl is not None:
                foreign_net = foreign_excl
            else:
                foreign_net = foreign_dealer

            report_date = _format_date_yyyymmdd(data.get("date"))

            return {
                "stock_code": stock_code,
                "market": "TSE",
                "date": report_date,
                "foreign_net": foreign_net,
                "trust_net": trust_net,
                "dealer_net": dealer_net,
                "total_net": total_net,
            }

    logger.warning(
        "twse_openapi: no TSE institutional data found for %s (tried dates: %s)",
        stock_code,
        dates_to_try,
    )
    return None


# ─────────────────────────────────────────────────────────────────────────────
# OTC（上柜）三大法人
# ─────────────────────────────────────────────────────────────────────────────

# TPEx OpenAPI 三大法人字段说明（若端点恢复可用时）：
# https://www.tpex.org.tw/openapi/v1/tpex_mainboard_3big_traders_daily
# 响应: list-of-dicts，字段名待确认（端点当前在非台湾环境被 302 重定向至首页）
# 预期字段（基于 TPEx 文档）：
#   SecuritiesCompanyCode / CompanyName / ForeignInvestorsNetBuySell /
#   InvestmentTrustNetBuySell / DealersNetBuySell / Total
# 注意: 数值单位为「千股」或「张」，与 TSE 的「股」不同。

_TPEX_3INSTI_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_3big_traders_daily"


def _fetch_otc_institutional(stock_code: str, _date_str: Optional[str]) -> Optional[dict]:
    """
    从 TPEx OpenAPI 获取单只上柜股票的三大法人数据。

    ⚠ 当前已知问题：此端点在台湾境外环境下 302 重定向至首页，无法取得数据，
    届时静默返回 None。
    """
    data = _get_json(_TPEX_3INSTI_URL)
    if not isinstance(data, list) or not data:
        logger.warning(
            "twse_openapi: OTC 三大法人端点不可用（可能被重定向），stock=%s", stock_code
        )
        return None

    # 尝试常见字段名称（TPEx openapi 历史上曾用过多种命名）
    # 已知字段候选（按文档/社区资料）：
    #   - 'SecuritiesCompanyCode' or 'Code' or 'StockCode'
    #   - 'ForeignInvestorsNetBuySell' or 'ForeignNetBuySell'
    #   - 'InvestmentTrustNetBuySell' or 'TrustNetBuySell'
    #   - 'DealersNetBuySell' or 'DealerNetBuySell'
    #   - 'Total' or 'TotalNetBuySell'
    first = data[0]
    code_keys = [k for k in first if any(kw in k.lower() for kw in ("code", "no", "股票代", "代號", "securi"))]
    if not code_keys:
        logger.warning("twse_openapi: 无法识别 TPEx 三大法人 code 字段，keys=%s", list(first.keys()))
        return None

    code_key = code_keys[0]
    for row in data:
        if str(row.get(code_key, "")).strip() != stock_code:
            continue

        # 动态匹配各字段
        def _pick(keywords: list[str]) -> Optional[int]:
            for k in row:
                if any(kw.lower() in k.lower() for kw in keywords):
                    return _safe_int(row[k])
            return None

        foreign_net = _pick(["foreign", "外資", "外陸", "ForeignInvestors", "ForeignNet"])
        trust_net = _pick(["trust", "投信", "InvestmentTrust", "TrustNet"])
        dealer_net = _pick(["dealer", "自營", "Dealer", "DealerNet"])
        total_net = _pick(["total", "Total", "三大", "合計"])

        # 尝试从响应字段中获取日期
        report_date = None
        for k in row:
            if any(kw.lower() in k.lower() for kw in ("date", "日期", "時間")):
                report_date = _format_date_yyyymmdd(str(row[k]).replace("/", ""))
                break

        return {
            "stock_code": stock_code,
            "market": "OTC",
            "date": report_date,
            "foreign_net": foreign_net,
            "trust_net": trust_net,
            "dealer_net": dealer_net,
            "total_net": total_net,
        }

    logger.warning("twse_openapi: TPEx 三大法人未找到 stock=%s", stock_code)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# TSE（上市）融资融券
# ─────────────────────────────────────────────────────────────────────────────

# TWSE openapi.twse.com.tw 融资融券字段（list-of-dicts，今日数据，无日期参数）:
#   '股票代號' '股票名稱' '融資買進' '融資賣出' '融資現金償還'
#   '融資前日餘額' '融資今日餘額' '融資限額'
#   '融券買進' '融券賣出' '融券現券償還' '融券前日餘額' '融券今日餘額' '融券限額'
#   '資券互抵' '註記'
# 数值单位：张（1 张 = 1000 股）

_TSE_MARGN_OPENAPI_URL = "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN"

# TWSE rwd 融资融券（支持历史日期，tables[1] 位置索引）:
#   [0]=代号 [1]=名称
#   融资: [2]=买进 [3]=卖出 [4]=现金偿还 [5]=前日余额 [6]=今日余额 [7]=次一限额
#   融券: [8]=买进 [9]=卖出 [10]=现券偿还 [11]=前日余额 [12]=今日余额 [13]=次一限额
#   [14]=资券互抵 [15]=注记
# 数值单位：张（1 张 = 1000 股）
_TSE_MARGN_RWD_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"


def _parse_tse_margin_from_openapi_row(stock_code: str, row: dict, report_date: Optional[str]) -> dict:
    """将 openapi MI_MARGN 的单行 dict 解析为标准化输出。"""
    margin_buy = _safe_int(row.get("融資買進"))
    margin_sell = _safe_int(row.get("融資賣出"))
    margin_balance = _safe_int(row.get("融資今日餘額"))
    short_sell = _safe_int(row.get("融券賣出"))
    short_cover = _safe_int(row.get("融券買進"))
    short_balance = _safe_int(row.get("融券今日餘額"))
    margin_limit = _safe_int(row.get("融資限額"))

    # 融资使用率 = 融资余额 / 融资限额 * 100（若可计算）
    margin_usage_pct: Optional[float] = None
    if margin_balance is not None and margin_limit and margin_limit > 0:
        margin_usage_pct = round(margin_balance / margin_limit * 100, 4)

    return {
        "stock_code": stock_code,
        "market": "TSE",
        "date": report_date,
        "margin_buy": margin_buy,
        "margin_sell": margin_sell,
        "margin_balance": margin_balance,
        "short_sell": short_sell,
        "short_cover": short_cover,
        "short_balance": short_balance,
        "margin_usage_pct": margin_usage_pct,
    }


def _fetch_tse_margin(stock_code: str, date_str: Optional[str]) -> Optional[dict]:
    """
    从 TWSE 获取上市股票融资融券余额。

    优先使用 openapi.twse.com.tw（今日数据，无日期参数）；
    若指定 date 参数则使用 rwd 历史端点。
    数值单位：张（1 张 = 1000 股）。
    """
    # 若指定日期，使用 rwd 历史端点
    if date_str:
        data = _get_json(
            _TSE_MARGN_RWD_URL,
            {"response": "json", "date": date_str, "selectType": "STOCK", "stockNo": stock_code},
        )
        if not data or data.get("stat") != "OK":
            logger.warning(
                "twse_openapi: TSE margin rwd returned no data for %s date=%s", stock_code, date_str
            )
            return None

        tables = data.get("tables") or []
        table = next((t for t in tables if t.get("data")), None)
        if not table:
            return None

        rows = table.get("data") or []
        report_date = _format_date_yyyymmdd(data.get("date"))

        for row in rows:
            if len(row) < 14 or str(row[0]).strip() != stock_code:
                continue
            margin_buy = _safe_int(row[2])
            margin_sell = _safe_int(row[3])
            margin_balance = _safe_int(row[6])
            short_sell = _safe_int(row[9])
            short_cover = _safe_int(row[8])
            short_balance = _safe_int(row[12])
            margin_limit = _safe_int(row[7])

            margin_usage_pct: Optional[float] = None
            if margin_balance is not None and margin_limit and margin_limit > 0:
                margin_usage_pct = round(margin_balance / margin_limit * 100, 4)

            return {
                "stock_code": stock_code,
                "market": "TSE",
                "date": report_date,
                "margin_buy": margin_buy,
                "margin_sell": margin_sell,
                "margin_balance": margin_balance,
                "short_sell": short_sell,
                "short_cover": short_cover,
                "short_balance": short_balance,
                "margin_usage_pct": margin_usage_pct,
            }

        logger.warning(
            "twse_openapi: TSE margin rwd: stock %s not found for date=%s", stock_code, date_str
        )
        return None

    # 默认：使用 openapi（今日数据）
    data = _get_json(_TSE_MARGN_OPENAPI_URL)
    if not isinstance(data, list):
        logger.warning("twse_openapi: TSE margin openapi returned non-list for %s", stock_code)
        return None

    for row in data:
        if str(row.get("股票代號", "")).strip() == stock_code:
            return _parse_tse_margin_from_openapi_row(stock_code, row, report_date=None)

    logger.warning("twse_openapi: TSE margin: stock %s not found in openapi response", stock_code)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# OTC（上柜）融资融券
# ─────────────────────────────────────────────────────────────────────────────

# TPEx OpenAPI 融资融券字段说明（若端点恢复可用时）：
# https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_transactions
# 响应: list-of-dicts
# 预期字段（基于 TPEx 官方说明）：
#   SecuritiesCompanyCode / CompanyName
#   MarginPurchase / MarginSales / MarginCashPayment / MarginYesterdayBalance / MarginBalance / MarginLimit
#   ShortSale / ShortCovering / StockPayment / ShortYesterdayBalance / ShortBalance / ShortLimit
#   OffsetLots / Remark
# 注意：数值单位为「张/千股」，与 TSE 一致。
# 当前已知：端点在非台湾环境被 302 重定向，届时返回 None。

_TPEX_MARGN_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_transactions"


def _fetch_otc_margin(stock_code: str, _date_str: Optional[str]) -> Optional[dict]:
    """
    从 TPEx OpenAPI 获取上柜股票融资融券余额。

    ⚠ 当前已知问题：此端点在台湾境外环境下 302 重定向至首页，无法取得数据，
    届时静默返回 None。
    数值单位：张（1 张 = 1000 股）。
    """
    data = _get_json(_TPEX_MARGN_URL)
    if not isinstance(data, list) or not data:
        logger.warning(
            "twse_openapi: OTC 融资融券端点不可用（可能被重定向），stock=%s", stock_code
        )
        return None

    first = data[0]
    code_keys = [
        k for k in first
        if any(kw.lower() in k.lower() for kw in ("code", "no", "股票代", "代號", "securi"))
    ]
    if not code_keys:
        logger.warning("twse_openapi: 无法识别 TPEx 融资融券 code 字段，keys=%s", list(first.keys()))
        return None

    code_key = code_keys[0]
    for row in data:
        if str(row.get(code_key, "")).strip() != stock_code:
            continue

        def _pick(keywords: list[str]) -> Optional[int]:
            for k in row:
                kl = k.lower()
                if any(kw.lower() in kl for kw in keywords):
                    return _safe_int(row[k])
            return None

        margin_buy = _pick(["MarginPurchase", "融資買進", "marginpurchase"])
        margin_sell = _pick(["MarginSales", "融資賣出", "marginsales"])
        margin_balance = _pick(["MarginBalance", "融資今日餘額", "marginbalance"])
        short_sell = _pick(["ShortSale", "融券賣出", "shortsale"])
        short_cover = _pick(["ShortCovering", "融券買進", "shortcovering"])
        short_balance = _pick(["ShortBalance", "融券今日餘額", "shortbalance"])
        margin_limit = _pick(["MarginLimit", "融資限額", "marginlimit"])

        margin_usage_pct: Optional[float] = None
        if margin_balance is not None and margin_limit and margin_limit > 0:
            margin_usage_pct = round(margin_balance / margin_limit * 100, 4)

        report_date = None
        for k in row:
            if any(kw.lower() in k.lower() for kw in ("date", "日期")):
                report_date = _format_date_yyyymmdd(str(row[k]).replace("/", ""))
                break

        return {
            "stock_code": stock_code,
            "market": "OTC",
            "date": report_date,
            "margin_buy": margin_buy,
            "margin_sell": margin_sell,
            "margin_balance": margin_balance,
            "short_sell": short_sell,
            "short_cover": short_cover,
            "short_balance": short_balance,
            "margin_usage_pct": margin_usage_pct,
        }

    logger.warning("twse_openapi: TPEx 融资融券未找到 stock=%s", stock_code)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 公开接口
# ─────────────────────────────────────────────────────────────────────────────


def get_institutional_investors(
    stock_code: str,
    *,
    market: Optional[str] = None,
    date: Optional[str] = None,
) -> Optional[dict]:
    """三大法人买卖超（单一个股）。

    market: 'TSE'|'OTC'|None（自动先试上市再试上柜）。
    date: 'YYYYMMDD'|None（最近交易日）。

    返回 dict 或 None：
      {
        'stock_code': str, 'market': 'TSE'|'OTC', 'date': 'YYYY-MM-DD',
        'foreign_net': int,   # 外资及陆资买卖超股数（净，含外资自营商）
        'trust_net': int,     # 投信买卖超股数（净）
        'dealer_net': int,    # 自营商买卖超股数（净，含自行买卖+避险）
        'total_net': int,     # 三大法人买卖超合计股数
      }
    数值单位为「股」（TSE）。无法取得任一来源时返回 None，不抛异常。
    """
    try:
        code = _normalize_stock_code(stock_code)
    except Exception as exc:
        logger.warning("twse_openapi: get_institutional_investors normalize error: %s", exc)
        return None

    try:
        if market == "TSE":
            return _fetch_tse_institutional(code, date)
        if market == "OTC":
            return _fetch_otc_institutional(code, date)

        # 自动顺序：先试 TSE，再试 OTC
        result = _fetch_tse_institutional(code, date)
        if result is not None:
            return result
        return _fetch_otc_institutional(code, date)
    except Exception as exc:
        logger.warning(
            "twse_openapi: get_institutional_investors unexpected error for %s: %s", stock_code, exc
        )
        return None


def get_margin_balance(
    stock_code: str,
    *,
    market: Optional[str] = None,
    date: Optional[str] = None,
) -> Optional[dict]:
    """融资融券余额（单一个股）。

    market: 'TSE'|'OTC'|None（自动先试上市再试上柜）。
    date: 'YYYYMMDD'|None（最近交易日）。

    返回 dict 或 None：
      {
        'stock_code': str, 'market': 'TSE'|'OTC', 'date': 'YYYY-MM-DD',
        'margin_buy': int,        # 融资买进（张）
        'margin_sell': int,       # 融资卖出（张）
        'margin_balance': int,    # 融资今日余额（张）
        'short_sell': int,        # 融券卖出（张）
        'short_cover': int,       # 融券买进（回补）（张）
        'short_balance': int,     # 融券今日余额（张）
        'margin_usage_pct': Optional[float],  # 融资使用率(%)，无则 None
      }
    数值单位：张（TSE openapi）或张（TPEx openapi），1 张 ≈ 1000 股。
    无法取得返回 None，不抛异常。
    """
    try:
        code = _normalize_stock_code(stock_code)
    except Exception as exc:
        logger.warning("twse_openapi: get_margin_balance normalize error: %s", exc)
        return None

    try:
        if market == "TSE":
            return _fetch_tse_margin(code, date)
        if market == "OTC":
            return _fetch_otc_margin(code, date)

        # 自动顺序：先试 TSE，再试 OTC
        result = _fetch_tse_margin(code, date)
        if result is not None:
            return result
        return _fetch_otc_margin(code, date)
    except Exception as exc:
        logger.warning(
            "twse_openapi: get_margin_balance unexpected error for %s: %s", stock_code, exc
        )
        return None
