# -*- coding: utf-8 -*-
"""
TWSE / TPEx 三大法人與融資融券公開 API 適配器（無需 API Key）。

數據來源:
  TSE（上市）三大法人:
    https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date=YYYYMMDD&selectType=ALL
    stat/date/fields/data 格式。fields 共 19 個欄位（含證券代號/名稱後的18個數值列）：
      [0]  證券代號
      [1]  證券名稱
      [2]  外陸資買進股數(不含外資自營商)
      [3]  外陸資賣出股數(不含外資自營商)
      [4]  外陸資買賣超股數(不含外資自營商)   ← foreign_net 基礎
      [5]  外資自營商買進股數
      [6]  外資自營商賣出股數
      [7]  外資自營商買賣超股數               ← 外資含自營商淨額 = [4]+[7]
      [8]  投信買進股數
      [9]  投信賣出股數
      [10] 投信買賣超股數                     ← trust_net
      [11] 自營商買賣超股數（總計）            ← dealer_net
      [12] 自營商買進股數(自行買賣)
      [13] 自營商賣出股數(自行買賣)
      [14] 自營商買賣超股數(自行買賣)
      [15] 自營商買進股數(避險)
      [16] 自營商賣出股數(避險)
      [17] 自營商買賣超股數(避險)
      [18] 三大法人買賣超股數                 ← total_net

  TSE 融資融券（上市）:
    https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN （今日，無 date 參數）
    返回 list-of-dicts，欄位名（與 rwd 相同含義，位置對齊）：
      股票代號、股票名稱、融資買進、融資賣出、融資現金償還、
      融資前日餘額、融資今日餘額、融資限額、
      融券買進、融券賣出、融券現券償還、融券前日餘額、融券今日餘額、融券限額、
      資券互抵、註記
    備用（指定日期）: https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN
      ?response=json&date=YYYYMMDD&selectType=STOCK&stockNo=XXXX
      返回 tables 數組，tables[1] 包含 fields+data：
        [0]=代號 [1]=名稱
        融資: [2]=買進 [3]=賣出 [4]=現金償還 [5]=前日餘額 [6]=今日餘額 [7]=次一營業日限額
        融券: [8]=買進 [9]=賣出 [10]=現券償還 [11]=前日餘額 [12]=今日餘額 [13]=次一營業日限額
        [14]=資券互抵 [15]=註記

  OTC（上櫃）三大法人:
    https://www.tpex.org.tw/openapi/v1/tpex_mainboard_3big_traders_daily
    ⚠ 注意：此端點在非台灣地區（或某些環境）可能被 302 重定向至首頁，
    屆時本模組將靜默返回 None。若未來端點恢復，list-of-dicts 結構待補充。

  OTC（上櫃）融資融券:
    https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_transactions
    ⚠ 同上，302 重定向時返回 None。

所有函數:
  - 遇到任何異常均返回 None，不向調用方拋出異常。
  - 日誌等級為 WARNING。
  - HTTP 請求攜帶 User-Agent: daily-stock-analysis/1.0，超時 10 秒。
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
# 內部工具函數
# ─────────────────────────────────────────────────────────────────────────────


def _get_json(url: str, params: Optional[dict] = None) -> Any:
    """發起 GET 請求，返回解析後的 JSON 對象；任何失敗均返回 None。"""
    if params:
        from urllib.parse import urlencode
        url = url + ("&" if "?" in url else "?") + urlencode(params)
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read()
            # 若響應是 HTML（如 TPEx 重定向至首頁），直接返回 None
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
    """將各種格式統一為純數字或字母代碼（去除 TW/TWO 後綴及 TW 前綴）。

    例:
      'TW2330'  → '2330'
      'tw2330'  → '2330'
      '2330.TW' → '2330'
      '4958.TWO'→ '4958'
      '2330'    → '2330'
    """
    s = raw.strip()
    # 去除 .TW / .TWO 等證券後綴
    s = re.sub(r"\.(TW|TWO|TW0)$", "", s, flags=re.IGNORECASE)
    # 去除開頭的 TW / tw 前綴（僅當後面是數字時）
    s = re.sub(r"^tw", "", s, flags=re.IGNORECASE)
    return s.strip()


def _safe_int(value: Any) -> Optional[int]:
    """Best-effort 整數轉換（處理逗號分隔的千位格式、空字串等）。"""
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
    """Best-effort 浮點轉換。"""
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
    """返回最近 n 個非週末日期（YYYYMMDD 格式），最新在前。"""
    days: list[str] = []
    d = date.today() - timedelta(days=1)
    while len(days) < n:
        if d.weekday() < 5:  # 0=Mon … 4=Fri
            days.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return days


def _format_date_yyyymmdd(raw_date: Optional[str]) -> Optional[str]:
    """將 TWSE 的 YYYYMMDD 格式日期轉為 YYYY-MM-DD；若已是該格式則直接返回。"""
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
    從 TWSE rwd T86 獲取單隻上市股票的三大法人數據。

    端點: https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date=YYYYMMDD&selectType=ALL
    響應結構:
      stat: 'OK' | '很抱歉...'
      date: 'YYYYMMDD'
      fields: [19 個欄位名稱]
      data: [[...], [...], ...]   # 每行第 0 列為證券代號

    欄位索引（以下均相對於單行 data[i]）:
      [0]  證券代號
      [4]  外陸資買賣超股數(不含外資自營商)  → foreign_net（不含外資自營商）
      [7]  外資自營商買賣超股數              → 加入以合計「外資含自營商」
      [10] 投信買賣超股數                    → trust_net
      [11] 自營商買賣超股數（總計）           → dealer_net
      [18] 三大法人買賣超股數                → total_net
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

            # 索引越界保護
            if len(row) < 19:
                logger.warning(
                    "twse_openapi: T86 row for %s has only %d columns (expected 19)",
                    stock_code,
                    len(row),
                )
                return None

            foreign_excl = _safe_int(row[4])  # 外陸資(不含自營商)
            foreign_dealer = _safe_int(row[7])  # 外資自營商
            trust_net = _safe_int(row[10])
            dealer_net = _safe_int(row[11])
            total_net = _safe_int(row[18])

            # 外資淨額 = 外陸資(不含外資自營商) + 外資自營商
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
# OTC（上櫃）三大法人
# ─────────────────────────────────────────────────────────────────────────────

# TPEx OpenAPI 三大法人欄位說明（若端點恢復可用時）：
# https://www.tpex.org.tw/openapi/v1/tpex_mainboard_3big_traders_daily
# 響應: list-of-dicts，欄位名待確認（端點當前在非台灣環境被 302 重定向至首頁）
# 預期欄位（基於 TPEx 文件）：
#   SecuritiesCompanyCode / CompanyName / ForeignInvestorsNetBuySell /
#   InvestmentTrustNetBuySell / DealersNetBuySell / Total
# 注意: 數值單位為「千股」或「張」，與 TSE 的「股」不同。

_TPEX_3INSTI_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_3big_traders_daily"


def _fetch_otc_institutional(stock_code: str, _date_str: Optional[str]) -> Optional[dict]:
    """
    從 TPEx OpenAPI 獲取單隻上櫃股票的三大法人數據。

    ⚠ 當前已知問題：此端點在台灣境外環境下 302 重定向至首頁，無法取得數據，
    屆時靜默返回 None。
    """
    data = _get_json(_TPEX_3INSTI_URL)
    if not isinstance(data, list) or not data:
        logger.warning(
            "twse_openapi: OTC 三大法人端點不可用（可能被重定向），stock=%s", stock_code
        )
        return None

    # 嘗試常見欄位名稱（TPEx openapi 歷史上曾用過多種命名）
    # 已知欄位候選（按文件/社區資料）：
    #   - 'SecuritiesCompanyCode' or 'Code' or 'StockCode'
    #   - 'ForeignInvestorsNetBuySell' or 'ForeignNetBuySell'
    #   - 'InvestmentTrustNetBuySell' or 'TrustNetBuySell'
    #   - 'DealersNetBuySell' or 'DealerNetBuySell'
    #   - 'Total' or 'TotalNetBuySell'
    first = data[0]
    code_keys = [k for k in first if any(kw in k.lower() for kw in ("code", "no", "股票代", "代號", "securi"))]
    if not code_keys:
        logger.warning("twse_openapi: 無法識別 TPEx 三大法人 code 欄位，keys=%s", list(first.keys()))
        return None

    code_key = code_keys[0]
    for row in data:
        if str(row.get(code_key, "")).strip() != stock_code:
            continue

        # 動態匹配各欄位
        def _pick(keywords: list[str]) -> Optional[int]:
            for k in row:
                if any(kw.lower() in k.lower() for kw in keywords):
                    return _safe_int(row[k])
            return None

        foreign_net = _pick(["foreign", "外資", "外陸", "ForeignInvestors", "ForeignNet"])
        trust_net = _pick(["trust", "投信", "InvestmentTrust", "TrustNet"])
        dealer_net = _pick(["dealer", "自營", "Dealer", "DealerNet"])
        total_net = _pick(["total", "Total", "三大", "合計"])

        # 嘗試從響應欄位中獲取日期
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
# TSE（上市）融資融券
# ─────────────────────────────────────────────────────────────────────────────

# TWSE openapi.twse.com.tw 融資融券欄位（list-of-dicts，今日數據，無日期參數）:
#   '股票代號' '股票名稱' '融資買進' '融資賣出' '融資現金償還'
#   '融資前日餘額' '融資今日餘額' '融資限額'
#   '融券買進' '融券賣出' '融券現券償還' '融券前日餘額' '融券今日餘額' '融券限額'
#   '資券互抵' '註記'
# 數值單位：張（1 張 = 1000 股）

_TSE_MARGN_OPENAPI_URL = "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN"

# TWSE rwd 融資融券（支持歷史日期，tables[1] 位置索引）:
#   [0]=代號 [1]=名稱
#   融資: [2]=買進 [3]=賣出 [4]=現金償還 [5]=前日餘額 [6]=今日餘額 [7]=次一限額
#   融券: [8]=買進 [9]=賣出 [10]=現券償還 [11]=前日餘額 [12]=今日餘額 [13]=次一限額
#   [14]=資券互抵 [15]=註記
# 數值單位：張（1 張 = 1000 股）
_TSE_MARGN_RWD_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"


def _parse_tse_margin_from_openapi_row(stock_code: str, row: dict, report_date: Optional[str]) -> dict:
    """將 openapi MI_MARGN 的單行 dict 解析為標準化輸出。"""
    margin_buy = _safe_int(row.get("融資買進"))
    margin_sell = _safe_int(row.get("融資賣出"))
    margin_balance = _safe_int(row.get("融資今日餘額"))
    short_sell = _safe_int(row.get("融券賣出"))
    short_cover = _safe_int(row.get("融券買進"))
    short_balance = _safe_int(row.get("融券今日餘額"))
    margin_limit = _safe_int(row.get("融資限額"))

    # 融資使用率 = 融資餘額 / 融資限額 * 100（若可計算）
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
    從 TWSE 獲取上市股票融資融券餘額。

    優先使用 openapi.twse.com.tw（今日數據，無日期參數）；
    若指定 date 參數則使用 rwd 歷史端點。
    數值單位：張（1 張 = 1000 股）。
    """
    # 若指定日期，使用 rwd 歷史端點
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

    # 默認：使用 openapi（今日數據）
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
# OTC（上櫃）融資融券
# ─────────────────────────────────────────────────────────────────────────────

# TPEx OpenAPI 融資融券欄位說明（若端點恢復可用時）：
# https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_transactions
# 響應: list-of-dicts
# 預期欄位（基於 TPEx 官方說明）：
#   SecuritiesCompanyCode / CompanyName
#   MarginPurchase / MarginSales / MarginCashPayment / MarginYesterdayBalance / MarginBalance / MarginLimit
#   ShortSale / ShortCovering / StockPayment / ShortYesterdayBalance / ShortBalance / ShortLimit
#   OffsetLots / Remark
# 注意：數值單位為「張/千股」，與 TSE 一致。
# 當前已知：端點在非台灣環境被 302 重定向，屆時返回 None。

_TPEX_MARGN_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_transactions"


def _fetch_otc_margin(stock_code: str, _date_str: Optional[str]) -> Optional[dict]:
    """
    從 TPEx OpenAPI 獲取上櫃股票融資融券餘額。

    ⚠ 當前已知問題：此端點在台灣境外環境下 302 重定向至首頁，無法取得數據，
    屆時靜默返回 None。
    數值單位：張（1 張 = 1000 股）。
    """
    data = _get_json(_TPEX_MARGN_URL)
    if not isinstance(data, list) or not data:
        logger.warning(
            "twse_openapi: OTC 融資融券端點不可用（可能被重定向），stock=%s", stock_code
        )
        return None

    first = data[0]
    code_keys = [
        k for k in first
        if any(kw.lower() in k.lower() for kw in ("code", "no", "股票代", "代號", "securi"))
    ]
    if not code_keys:
        logger.warning("twse_openapi: 無法識別 TPEx 融資融券 code 欄位，keys=%s", list(first.keys()))
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

    logger.warning("twse_openapi: TPEx 融資融券未找到 stock=%s", stock_code)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 公開介面
# ─────────────────────────────────────────────────────────────────────────────


def get_institutional_investors(
    stock_code: str,
    *,
    market: Optional[str] = None,
    date: Optional[str] = None,
) -> Optional[dict]:
    """三大法人買賣超（單一個股）。

    market: 'TSE'|'OTC'|None（自動先試上市再試上櫃）。
    date: 'YYYYMMDD'|None（最近交易日）。

    返回 dict 或 None：
      {
        'stock_code': str, 'market': 'TSE'|'OTC', 'date': 'YYYY-MM-DD',
        'foreign_net': int,   # 外資及陸資買賣超股數（淨，含外資自營商）
        'trust_net': int,     # 投信買賣超股數（淨）
        'dealer_net': int,    # 自營商買賣超股數（淨，含自行買賣+避險）
        'total_net': int,     # 三大法人買賣超合計股數
      }
    數值單位為「股」（TSE）。無法取得任一來源時返回 None，不拋異常。
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

        # 自動順序：先試 TSE，再試 OTC
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
    """融資融券餘額（單一個股）。

    market: 'TSE'|'OTC'|None（自動先試上市再試上櫃）。
    date: 'YYYYMMDD'|None（最近交易日）。

    返回 dict 或 None：
      {
        'stock_code': str, 'market': 'TSE'|'OTC', 'date': 'YYYY-MM-DD',
        'margin_buy': int,        # 融資買進（張）
        'margin_sell': int,       # 融資賣出（張）
        'margin_balance': int,    # 融資今日餘額（張）
        'short_sell': int,        # 融券賣出（張）
        'short_cover': int,       # 融券買進（回補）（張）
        'short_balance': int,     # 融券今日餘額（張）
        'margin_usage_pct': Optional[float],  # 融資使用率(%)，無則 None
      }
    數值單位：張（TSE openapi）或張（TPEx openapi），1 張 ≈ 1000 股。
    無法取得返回 None，不拋異常。
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

        # 自動順序：先試 TSE，再試 OTC
        result = _fetch_tse_margin(code, date)
        if result is not None:
            return result
        return _fetch_otc_margin(code, date)
    except Exception as exc:
        logger.warning(
            "twse_openapi: get_margin_balance unexpected error for %s: %s", stock_code, exc
        )
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 大盤統計：漲跌家數 / 成交額 / 類股漲跌幅（TWSE 上市，無需 API Key）
# ─────────────────────────────────────────────────────────────────────────────

_TWSE_FMTQIK_URL = "https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK"
_TWSE_MI_INDEX_URL = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"
_TWSE_STOCK_DAY_ALL_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"


def get_tw_market_stats() -> Optional[dict]:
    """TWSE（上市）大盤統計：漲跌家數 + 估算漲跌停家數 + 成交額(億元) + 加權指數。

    來源（均無需 Key）：
      - STOCK_DAY_ALL：逐檔個股，依 Change 正負統計漲/跌/平；以漲跌幅≈±10% 估算漲跌停。
      - FMTQIK：每日市場成交資訊，TradeValue=成交金額(元)、TAIEX=加權指數、Change=指數漲跌點。
    任意來源失敗均優雅降級（預設對應欄位）；全部失敗返回 None。
    """
    stats: dict = {}

    rows = _get_json(_TWSE_STOCK_DAY_ALL_URL)
    if isinstance(rows, list) and rows:
        up = down = flat = limit_up = limit_down = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            change = _safe_float(row.get("Change"))
            if change is None:
                continue
            if change > 0:
                up += 1
            elif change < 0:
                down += 1
            else:
                flat += 1
            close = _safe_float(row.get("ClosingPrice"))
            if close is not None:
                prev = close - change
                if prev > 0:
                    pct = change / prev * 100
                    if pct >= 9.8:
                        limit_up += 1
                    elif pct <= -9.8:
                        limit_down += 1
        stats.update(
            {
                "up_count": up,
                "down_count": down,
                "flat_count": flat,
                "limit_up_count": limit_up,
                "limit_down_count": limit_down,
            }
        )

    fmt = _get_json(_TWSE_FMTQIK_URL)
    if isinstance(fmt, list) and fmt:
        last = fmt[-1] if isinstance(fmt[-1], dict) else {}
        trade_value = _safe_float(last.get("TradeValue"))
        if trade_value is not None:
            stats["total_amount"] = round(trade_value / 1e8, 2)  # 元 → 億元
        taiex = _safe_float(last.get("TAIEX"))
        if taiex is not None:
            stats["index_close"] = taiex
        idx_change = _safe_float(last.get("Change"))
        if idx_change is not None:
            stats["index_change"] = idx_change

    return stats or None


def get_tw_sector_rankings(n: int = 5) -> Optional[tuple]:
    """TWSE（上市）類股漲跌榜：自 MI_INDEX 取各『類指數』漲跌幅，排序取領漲/領跌各 n。

    返回 (top_sectors, bottom_sectors)，元素為 {'name','change_pct'}；失敗返回 None。
    """
    rows = _get_json(_TWSE_MI_INDEX_URL)
    if not isinstance(rows, list) or not rows:
        return None

    sectors: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = (row.get("指數") or "").strip()
        # 僅保留產業類股指數，排除加權/未含/報酬等衍生指數
        if "類" not in name or any(
            x in name for x in ("未含", "報酬", "加權", "寶島", "反向", "正向", "槓桿", "兩倍", "單日")
        ):
            continue
        pct = _safe_float(row.get("漲跌百分比"))
        if pct is None:
            continue
        sign = (row.get("漲跌") or "").strip()
        if sign in ("-", "－", "—") and pct > 0:  # 防禦：百分比若為無符號幅度則按漲跌列定號
            pct = -pct
        display = name.replace("類指數", "").replace("類", "") or name
        sectors.append({"name": display, "change_pct": round(pct, 2)})

    if not sectors:
        return None

    sectors.sort(key=lambda s: s["change_pct"], reverse=True)
    top = sectors[:n]
    bottom = list(reversed(sectors[-n:]))
    return top, bottom


# ─────────────────────────────────────────────────────────────────────────────
# 櫃買指數（TPEx 上柜指数）— TPEx OpenAPI（无需 Key）
# yfinance ^TWOII 数据常滞后/不准，改用此权威来源。
# ─────────────────────────────────────────────────────────────────────────────

_TPEX_INDEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_index"
_TPEX_DAILY_TRADING_INDEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_daily_trading_index"
_TWSE_FMTQIK_TURNOVER_URL = "https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK"


def _tpex_latest_turnover_and_volume() -> tuple[Optional[float], Optional[float]]:
    """TPEx（上柜）最新成交金额(元)与成交量(股)，取自 tpex_daily_trading_index。"""
    rows = _get_json(_TPEX_DAILY_TRADING_INDEX_URL)
    if not isinstance(rows, list) or not rows:
        return None, None
    for row in reversed(rows):
        if isinstance(row, dict) and _safe_float(row.get("TradeAmount")) is not None:
            return _safe_float(row.get("TradeAmount")), _safe_float(row.get("TradeVolume"))
    return None, None


def get_twse_total_turnover() -> Optional[float]:
    """TWSE（上市）最新成交金额(元)，取自 FMTQIK TradeValue。失败返回 None。"""
    rows = _get_json(_TWSE_FMTQIK_TURNOVER_URL)
    if not isinstance(rows, list) or not rows:
        return None
    for row in reversed(rows):
        if isinstance(row, dict):
            tv = _safe_float(row.get("TradeValue"))
            if tv is not None:
                return tv
    return None


def get_tw_otc_index() -> Optional[dict]:
    """櫃買指數最新行情，取自 TPEx OpenAPI；返回与 yfinance 指数项同构的 dict。

    OHLC 取自 tpex_index；成交额/成交量取自 tpex_daily_trading_index（同为当日）。
    字段: code/name/current/change/change_pct/open/high/low/prev_close/
    volume/amount/amplitude。任何失败返回 None（调用方可回退 yfinance）。
    """
    rows = _get_json(_TPEX_INDEX_URL)
    if not isinstance(rows, list) or not rows:
        return None

    last = None
    for row in reversed(rows):
        if isinstance(row, dict) and _safe_float(row.get("Close")) is not None:
            last = row
            break
    if last is None:
        return None

    close = _safe_float(last.get("Close"))
    change = _safe_float(last.get("Change")) or 0.0
    open_ = _safe_float(last.get("Open")) or 0.0
    high = _safe_float(last.get("High")) or 0.0
    low = _safe_float(last.get("Low")) or 0.0
    prev_close = round(close - change, 4)
    change_pct = (change / prev_close * 100) if prev_close else 0.0
    amplitude = ((high - low) / prev_close * 100) if prev_close else 0.0
    amount, volume = _tpex_latest_turnover_and_volume()

    return {
        "code": "TWOII",
        "name": "櫃買指數",
        "current": close,
        "change": change,
        "change_pct": round(change_pct, 4),
        "open": open_,
        "high": high,
        "low": low,
        "prev_close": prev_close,
        "volume": volume or 0.0,
        "amount": amount or 0.0,
        "amplitude": round(amplitude, 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 加權指數（TAIEX）
# yfinance ^TWII 数据常滞后/缺漏/失真（缺当日、与官方收盘差距甚大 → 涨跌幅错误）。
# 优先 TWSE MIS 即时 API（含「当日」OHLC + 昨收，与櫃買 TPEx 口径同步）；
# MIS 不可用（如非台湾 IP 被限）时回退 openapi 日线 MI_5MINS_HIST（权威但可能滞后一日）。
# 成交额/量取自 FMTQIK，且仅在其日期与指数日期相符时采用（避免把昨日成交额贴到今日）。
# ─────────────────────────────────────────────────────────────────────────────

_TWSE_TAIEX_OHLC_URL = "https://openapi.twse.com.tw/v1/exchangeReport/MI_5MINS_HIST"
_TWSE_MIS_TAIEX_URL = (
    "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0"
)


def _roc_to_ad_yyyymmdd(roc: Any) -> Optional[str]:
    """ROC 日期（如 '1150610'）转西元 'YYYYMMDD'；非 7 位数字返回 None。"""
    s = str(roc or "").strip()
    if len(s) == 7 and s.isdigit():
        return f"{int(s[:3]) + 1911}{s[3:]}"
    return None


def _fmtqik_turnover_for_date(ad_date: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    """FMTQIK 最末一笔成交额(元)/量(股)，仅当其日期与 ad_date('YYYYMMDD') 相符时返回。

    ad_date 为 None 时不做日期校验（直接取最末一笔）。日期不符返回 (None, None)，
    避免把上一交易日的成交额错贴到当日指数上。
    """
    rows = _get_json(_TWSE_FMTQIK_URL)
    if not isinstance(rows, list) or not rows:
        return None, None
    last = rows[-1] if isinstance(rows[-1], dict) else {}
    if ad_date is not None and _roc_to_ad_yyyymmdd(last.get("Date")) != ad_date:
        return None, None
    return _safe_float(last.get("TradeValue")), _safe_float(last.get("TradeVolume"))


def _taiex_from_mis() -> Optional[dict]:
    """加權指數当日行情，取自 TWSE MIS 即时 API（含 6/10 当日）。失败返回 None。"""
    data = _get_json(_TWSE_MIS_TAIEX_URL)
    if not isinstance(data, dict):
        return None
    arr = data.get("msgArray")
    if not isinstance(arr, list) or not arr or not isinstance(arr[0], dict):
        return None
    a = arr[0]
    close = _safe_float(a.get("z"))         # 最新/收盘指数
    prev_close = _safe_float(a.get("y"))    # 昨收
    if close is None or not prev_close:
        return None
    open_ = _safe_float(a.get("o")) or 0.0
    high = _safe_float(a.get("h")) or 0.0
    low = _safe_float(a.get("l")) or 0.0
    ad_date = str(a.get("d") or "").strip() or None  # MIS 已是西元 YYYYMMDD
    change = round(close - prev_close, 4)
    amount, volume = _fmtqik_turnover_for_date(ad_date)
    return {
        "code": "TWII",
        "name": "加權指數",
        "current": close,
        "change": change,
        "change_pct": round(change / prev_close * 100, 4),
        "open": open_,
        "high": high,
        "low": low,
        "prev_close": prev_close,
        "volume": volume or 0.0,
        "amount": amount or 0.0,
        "amplitude": round((high - low) / prev_close * 100, 4) if prev_close else 0.0,
    }


def _taiex_from_mi5mins_hist() -> Optional[dict]:
    """加權指數行情，取自 openapi 日线 MI_5MINS_HIST（权威但可能滞后一日）。失败返回 None。"""
    rows = _get_json(_TWSE_TAIEX_OHLC_URL)
    if not isinstance(rows, list) or not rows:
        return None
    valid = [
        r for r in rows
        if isinstance(r, dict) and _safe_float(r.get("ClosingIndex")) is not None
    ]
    if len(valid) < 2:
        return None
    last, prev = valid[-1], valid[-2]
    close = _safe_float(last.get("ClosingIndex"))
    prev_close = _safe_float(prev.get("ClosingIndex"))
    if close is None or not prev_close:
        return None
    open_ = _safe_float(last.get("OpeningIndex")) or 0.0
    high = _safe_float(last.get("HighestIndex")) or 0.0
    low = _safe_float(last.get("LowestIndex")) or 0.0
    change = round(close - prev_close, 4)
    ad_date = _roc_to_ad_yyyymmdd(last.get("Date"))
    amount, volume = _fmtqik_turnover_for_date(ad_date)
    return {
        "code": "TWII",
        "name": "加權指數",
        "current": close,
        "change": change,
        "change_pct": round(change / prev_close * 100, 4),
        "open": open_,
        "high": high,
        "low": low,
        "prev_close": prev_close,
        "volume": volume or 0.0,
        "amount": amount or 0.0,
        "amplitude": round((high - low) / prev_close * 100, 4) if prev_close else 0.0,
    }


def get_tw_taiex_index() -> Optional[dict]:
    """加權指數（TAIEX）最新行情；返回与 yfinance 指数项同构的 dict。

    优先 TWSE MIS 即时 API（含「当日」资料，与櫃買 TPEx 同步）；MIS 不可用时回退
    openapi 日线 MI_5MINS_HIST。两者皆不可得返回 None（调用方可再回退 yfinance）。
    字段: code/name/current/change/change_pct/open/high/low/prev_close/volume/amount/amplitude。
    """
    return _taiex_from_mis() or _taiex_from_mi5mins_hist()


# ─────────────────────────────────────────────────────────────────────────────
# 全市场融资增加 Top N 排行（上市 TSE）— TWSE MI_MARGN（无需 Key）
# 单位：张（1 张 = 1000 股）。融資增加 = 融資今日餘額 - 融資前日餘額。
# ─────────────────────────────────────────────────────────────────────────────

_MARGIN_RANKING_SORTS = {
    "margin_increase": ("margin_change", False),   # 融资增加（默认）
    "margin_decrease": ("margin_change", True),    # 融资减少
    "short_increase": ("short_change", False),     # 融券增加
}


def get_tw_margin_ranking(top_n: int = 50, *, sort_by: str = "margin_increase") -> Optional[list]:
    """上市（TSE）融资融券排行（默认按融資增加降序），取自 TWSE MI_MARGN。

    一次取得全市场（含 融資/融券 昨餘/今餘），逐档计算当日增减与券资比；
    sort_by ∈ {margin_increase, margin_decrease, short_increase}。失败返回 None。
    单位：张。返回元素字段：stock_code/name/margin_balance/margin_prev/
    margin_change/short_balance/short_prev/short_change/offset/
    margin_usage_pct/short_margin_ratio。
    """
    rows = _get_json(_TSE_MARGN_OPENAPI_URL)
    if not isinstance(rows, list) or not rows:
        return None

    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("股票代號") or "").strip()
        if not code:
            continue
        m_prev = _safe_int(row.get("融資前日餘額"))
        m_today = _safe_int(row.get("融資今日餘額"))
        s_prev = _safe_int(row.get("融券前日餘額"))
        s_today = _safe_int(row.get("融券今日餘額"))
        if m_today is None and s_today is None:
            continue
        m_change = (m_today - m_prev) if (m_today is not None and m_prev is not None) else None
        s_change = (s_today - s_prev) if (s_today is not None and s_prev is not None) else None
        m_limit = _safe_int(row.get("融資限額"))
        usage = round(m_today / m_limit * 100, 2) if (m_today and m_limit and m_limit > 0) else None
        ratio = round(s_today / m_today * 100, 2) if (s_today is not None and m_today) else None
        out.append({
            "stock_code": code,
            "name": str(row.get("股票名稱") or "").strip(),
            "margin_balance": m_today,
            "margin_prev": m_prev,
            "margin_change": m_change,
            "short_balance": s_today,
            "short_prev": s_prev,
            "short_change": s_change,
            "offset": _safe_int(row.get("資券互抵")),
            "margin_usage_pct": usage,       # 融資使用率(%)
            "short_margin_ratio": ratio,     # 券資比(%) = 融券今餘 / 融資今餘
        })

    field, _desc_neg = _MARGIN_RANKING_SORTS.get(sort_by, _MARGIN_RANKING_SORTS["margin_increase"])
    negate = sort_by == "margin_decrease"

    def _key(r: dict) -> float:
        v = r.get(field)
        if v is None:
            return float("-inf")
        return -v if negate else v

    out.sort(key=_key, reverse=True)
    return out[: max(1, top_n)]


# ─────────────────────────────────────────────────────────────────────────────
# 大盤層級籌碼面：三大法人買賣超合計 + 融資融券餘額（全市場，供大盤覆盤使用）
# 來源均為 TWSE RWD JSON（無需 Key）。
# ─────────────────────────────────────────────────────────────────────────────

_TWSE_BFI82U_URL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json"
_TWSE_MARGIN_SUMMARY_URL = (
    "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=json&selectType=MS"
)


def get_tw_institutional_total() -> Optional[dict]:
    """TWSE（上市）三大法人買賣超『全市場合計』（單位：億元）。

    來源（無需 Key）：BFI82U 三大法人買賣金額統計表，
      回傳 {date, fields:[單位名稱,買進金額,賣出金額,買賣差額], data:[...]}，金額單位為元。
    彙整：外資（外資及陸資 + 外資自營商）、投信、自營商（自行買賣 + 避險）、合計 之買賣超。
    任何來源失敗或欄位缺失均優雅降級（返回 None 或對應欄位為 None）。
    """
    data = _get_json(_TWSE_BFI82U_URL)
    if not isinstance(data, dict):
        return None
    rows = data.get("data")
    if not isinstance(rows, list) or not rows:
        return None

    def _net_yi(raw: Any) -> Optional[float]:
        v = _safe_float(raw)
        return round(v / 1e8, 2) if v is not None else None

    trust = total = None
    foreign_acc = 0.0
    foreign_seen = False
    dealer_acc = 0.0
    dealer_seen = False
    for row in rows:
        if not isinstance(row, list) or len(row) < 4:
            continue
        name = str(row[0] or "").strip()
        net = _net_yi(row[3])
        if net is None:
            continue
        if name == "投信":
            trust = net
        elif name == "合計":
            total = net
        elif name.startswith("外資"):
            foreign_acc += net
            foreign_seen = True
        elif name.startswith("自營商"):
            dealer_acc += net
            dealer_seen = True

    result = {
        "foreign_net": round(foreign_acc, 2) if foreign_seen else None,
        "trust_net": trust,
        "dealer_net": round(dealer_acc, 2) if dealer_seen else None,
        "total_net": total,
        "unit": "億元",
        "trade_date": _format_date_yyyymmdd(str(data.get("date"))) if data.get("date") else None,
    }
    if all(result.get(k) is None for k in ("foreign_net", "trust_net", "dealer_net", "total_net")):
        return None
    return result


def get_tw_margin_total() -> Optional[dict]:
    """TWSE（上市）融資融券餘額『全市場合計』。

    來源（無需 Key）：MI_MARGN selectType=MS『信用交易統計』表，
      tables[0].fields = [項目,買進,賣出,現金(券)償還,前日餘額,今日餘額]，
      其中『融資金額(仟元)』為金額(仟元)、『融資(交易單位)』『融券(交易單位)』為張數。
    返回：融資餘額(億元) 與融券餘額(張) 之今日/前日/增減。任何失敗均返回 None。
    """
    data = _get_json(_TWSE_MARGIN_SUMMARY_URL)
    if not isinstance(data, dict):
        return None
    tables = data.get("tables")
    if not isinstance(tables, list) or not tables:
        return None
    summary = tables[0] if isinstance(tables[0], dict) else {}
    srows = summary.get("data")
    if not isinstance(srows, list) or not srows:
        return None

    by_item: dict[str, list] = {}
    for row in srows:
        if isinstance(row, list) and len(row) >= 6:
            by_item[str(row[0] or "").strip()] = row

    def _col(item: str, idx: int) -> Optional[int]:
        row = by_item.get(item)
        return _safe_int(row[idx]) if row else None

    # 融資金額(仟元) → 億元：仟元 / 1e5
    m_amt_today_k = _col("融資金額(仟元)", 5)
    m_amt_prev_k = _col("融資金額(仟元)", 4)
    margin_balance_yi = round(m_amt_today_k / 1e5, 2) if m_amt_today_k is not None else None
    margin_prev_yi = round(m_amt_prev_k / 1e5, 2) if m_amt_prev_k is not None else None
    margin_change_yi = (
        round(margin_balance_yi - margin_prev_yi, 2)
        if (margin_balance_yi is not None and margin_prev_yi is not None)
        else None
    )

    # 融券(交易單位) → 張
    s_today = _col("融券(交易單位)", 5)
    s_prev = _col("融券(交易單位)", 4)
    short_change = (s_today - s_prev) if (s_today is not None and s_prev is not None) else None

    result = {
        "margin_balance_yi": margin_balance_yi,   # 融資餘額（億元）
        "margin_prev_yi": margin_prev_yi,
        "margin_change_yi": margin_change_yi,
        "short_balance_lots": s_today,            # 融券餘額（張）
        "short_prev_lots": s_prev,
        "short_change_lots": short_change,
        "trade_date": _format_date_yyyymmdd(str(data.get("date"))) if data.get("date") else None,
    }
    if margin_balance_yi is None and s_today is None:
        return None
    return result


def get_tse_margin_trade_date() -> Optional[str]:
    """上市融資融券資料的『資料日期』（YYYY-MM-DD），取自 MI_MARGN 信用交易統計表。

    openapi 的 MI_MARGN（融資融券排行用）不含日期欄位，故另取 RWD MS 端點的權威日期。
    失敗返回 None，不拋異常。
    """
    data = _get_json(_TWSE_MARGIN_SUMMARY_URL)
    if isinstance(data, dict) and data.get("date"):
        return _format_date_yyyymmdd(str(data.get("date")))
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 個股估值（本益比 / 股價淨值比 / 殖利率）— TWSE BWIBBU_ALL（上市，無需 Key）
# 供個股分析補齊 PE/PB（台股實時快照來源 Shioaji 不含估值欄位）。
# ─────────────────────────────────────────────────────────────────────────────

_TWSE_BWIBBU_ALL_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
# 全市場估值表單檔即含逾千檔，以「資料日期」為鍵做極簡記憶體快取，避免一次分析重複下載。
_tw_valuation_cache: dict = {"date": None, "map": None}


def _normalize_tw_valuation_code(stock_code: str) -> str:
    """將 'tw2330' / 'TW2330' / '2330' 統一為 BWIBBU 的證券代號 '2330'（保留字母如 00631L）。"""
    code = str(stock_code or "").strip().upper()
    if code.startswith("TW"):
        code = code[2:]
    return code.strip()


def _load_tw_valuation_map() -> Optional[dict]:
    """下載並解析 BWIBBU_ALL 為 {證券代號: {pe_ratio, pb_ratio, dividend_yield}}；附當日快取。"""
    today = date.today().isoformat()
    if _tw_valuation_cache.get("date") == today and _tw_valuation_cache.get("map"):
        return _tw_valuation_cache["map"]

    rows = _get_json(_TWSE_BWIBBU_ALL_URL)
    if not isinstance(rows, list) or not rows:
        return None
    out: dict = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("Code") or "").strip().upper()
        if not code:
            continue
        out[code] = {
            "pe_ratio": _safe_float(row.get("PEratio")),
            "pb_ratio": _safe_float(row.get("PBratio")),
            "dividend_yield": _safe_float(row.get("DividendYield")),
        }
    if not out:
        return None
    _tw_valuation_cache["date"] = today
    _tw_valuation_cache["map"] = out
    return out


def get_tw_valuation(stock_code: str) -> Optional[dict]:
    """上市個股估值：{pe_ratio, pb_ratio, dividend_yield}，取自 TWSE BWIBBU_ALL（無需 Key）。

    虧損股 PEratio 可能為空 → pe_ratio 為 None；找不到代號或來源失敗返回 None。
    """
    code = _normalize_tw_valuation_code(stock_code)
    if not code:
        return None
    vmap = _load_tw_valuation_map()
    if not vmap:
        return None
    row = vmap.get(code)
    if not row:
        return None
    if row.get("pe_ratio") is None and row.get("pb_ratio") is None:
        return None
    return dict(row)
