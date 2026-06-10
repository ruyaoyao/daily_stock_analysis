# -*- coding: utf-8 -*-
"""
离线 pytest 测试 — data_provider/twse_openapi.py

全部 fixture 均为从真实端点采集后裁剪的静态数据（含股票 2330 台积电）。
不发起任何网络请求（通过 unittest.mock 替换模块内 _get_json）。

运行方式:
    python -m pytest tests/test_twse_openapi.py -m "not network"

说明: 为避免触发 data_provider/__init__.py 中的重型依赖（pandas/requests/tenacity 等），
本测试使用 importlib 直接加载目标模块，并在 sys.modules 中注册为
'data_provider.twse_openapi'，使 patch.object 和 patch() 照常工作。
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from typing import Any, Optional
from unittest.mock import patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# 直接加载 twse_openapi，绕过 data_provider/__init__.py 的重型依赖链
# ─────────────────────────────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODULE_PATH = os.path.join(_REPO_ROOT, "data_provider", "twse_openapi.py")


def _load_twse_openapi():
    """按需加载并缓存 twse_openapi 模块，避免通过 data_provider.__init__ 导入。"""
    cached = sys.modules.get("data_provider.twse_openapi")
    if cached is not None:
        return cached

    # 确保 data_provider 包存在于 sys.modules（但不触发真实 __init__.py）
    if "data_provider" not in sys.modules:
        dp_pkg = types.ModuleType("data_provider")
        dp_pkg.__path__ = [os.path.join(_REPO_ROOT, "data_provider")]
        dp_pkg.__package__ = "data_provider"
        sys.modules["data_provider"] = dp_pkg

    spec = importlib.util.spec_from_file_location(
        "data_provider.twse_openapi",
        _MODULE_PATH,
        submodule_search_locations=[],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["data_provider.twse_openapi"] = module
    spec.loader.exec_module(module)
    return module


mod = _load_twse_openapi()

# ─────────────────────────────────────────────────────────────────────────────
# 真实端点采集的 fixture（已裁剪，保留前 2-3 行 + 2330 行）
# ─────────────────────────────────────────────────────────────────────────────

# 来源: https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date=20240105&selectType=ALL
# 采集日期: 2024-01-05（台湾 2024 年第一个交易日）
# fields 共 19 项；data 每行 19 个值；数值含千位逗号；单位: 股
_FIXTURE_T86: dict[str, Any] = {
    "stat": "OK",
    "date": "20240105",
    "title": "113年01月05日 三大法人買賣超日報",
    "hints": "單位：股",
    "fields": [
        "證券代號",
        "證券名稱",
        "外陸資買進股數(不含外資自營商)",
        "外陸資賣出股數(不含外資自營商)",
        "外陸資買賣超股數(不含外資自營商)",
        "外資自營商買進股數",
        "外資自營商賣出股數",
        "外資自營商買賣超股數",
        "投信買進股數",
        "投信賣出股數",
        "投信買賣超股數",
        "自營商買賣超股數",
        "自營商買進股數(自行買賣)",
        "自營商賣出股數(自行買賣)",
        "自營商買賣超股數(自行買賣)",
        "自營商買進股數(避險)",
        "自營商賣出股數(避險)",
        "自營商買賣超股數(避險)",
        "三大法人買賣超股數",
    ],
    "data": [
        # 首行（群创 3481）
        [
            "3481", "群創            ",
            "71,737,948", "32,651,751", "39,086,197",
            "0", "0", "0",
            "200,000", "54,000", "146,000",
            "16,441,213", "10,636,000", "3,215,000", "7,421,000",
            "9,950,213", "930,000", "9,020,213",
            "55,673,410",
        ],
        # 台积电 2330 行
        [
            "2330", "台積電          ",
            "11,746,967", "19,597,425", "-7,850,458",
            "0", "0", "0",
            "106,000", "78,081", "27,919",
            "74,132",
            "128,000", "132,000", "-4,000",
            "123,100", "44,968", "78,132",
            "-7,748,407",
        ],
        # 力积电 6770
        [
            "6770", "力積電          ",
            "63,341,200", "11,629,000", "51,712,200",
            "0", "0", "0",
            "0", "0", "0",
            "1,390,784", "0", "0", "0",
            "1,390,784", "0", "1,390,784",
            "53,102,984",
        ],
    ],
}

# 来源: https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN（2026-06-05 今日数据）
# 字段: 股票代號/名稱/融資買進/賣出/現金償還/前日餘額/今日餘額/限額/
#       融券買進/賣出/現券償還/前日餘額/今日餘額/限額/資券互抵/註記
# 数值单位: 张（1 张 = 1000 股）
_FIXTURE_MI_MARGN_OPENAPI: list[dict[str, Any]] = [
    {
        "股票代號": "1101",
        "股票名稱": "台泥",
        "融資買進": "23",
        "融資賣出": "274",
        "融資現金償還": "14",
        "融資前日餘額": "17,763",
        "融資今日餘額": "17,498",
        "融資限額": "1,887,795",
        "融券買進": "0",
        "融券賣出": "0",
        "融券現券償還": "0",
        "融券前日餘額": "107",
        "融券今日餘額": "107",
        "融券限額": "1,887,795",
        "資券互抵": "0",
        "註記": " ",
    },
    {
        "股票代號": "2330",
        "股票名稱": "台積電",
        "融資買進": "1183",
        "融資賣出": "1590",
        "融資現金償還": "17",
        "融資前日餘額": "28388",
        "融資今日餘額": "27964",
        "融資限額": "6483131",
        "融券買進": "69",
        "融券賣出": "",
        "融券現券償還": "16",
        "融券前日餘額": "86",
        "融券今日餘額": "1",
        "融券限額": "6483131",
        "資券互抵": "",
        "註記": "X ",
    },
]

# 来源: https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN
#       ?response=json&date=20240105&selectType=STOCK&stockNo=2330
# 结构: top-level stat/date/tables（tables[0] 为空，tables[1] 含 fields+data）
# fields 共 16 项（有重复名称，需按位置解析），groups 定义融资/融券段落
# [0]=代号 [1]=名称
# 融资: [2]=买进 [3]=卖出 [4]=现金偿还 [5]=前日余额 [6]=今日余额 [7]=次一限额
# 融券: [8]=买进 [9]=卖出 [10]=现券偿还 [11]=前日余额 [12]=今日余额 [13]=次一限额
# [14]=资券互抵 [15]=注记
# 数值单位: 张
_FIXTURE_MI_MARGN_RWD: dict[str, Any] = {
    "stat": "OK",
    "date": "20240105",
    "tables": [
        {},  # tables[0] 空对象
        {
            "title": "113年01月05日 融資融券彙總 (股票)",
            "fields": [
                "代號", "名稱",
                "買進", "賣出", "現金償還", "前日餘額", "今日餘額", "次一營業日限額",
                "買進", "賣出", "現券償還", "前日餘額", "今日餘額", "次一營業日限額",
                "資券互抵", "註記",
            ],
            "data": [
                # 合计行（代号为空白）
                ["　", "合計", "212,914", "191,674", "3,293", "5,894,049", "5,911,996",
                 "183,231,723", "12,631", "23,324", "479", "255,394", "265,608",
                 "183,231,723", "2,351", "　"],
                # 台泥 1101
                ["1101", "台泥", "23", "274", "14", "17,763", "17,498", "1,887,795",
                 "0", "0", "0", "107", "107", "1,887,795", "0", " "],
                # 台积电 2330
                ["2330", "台積電", "316", "79", "1", "13,655", "13,891", "6,483,017",
                 "40", "14", "0", "138", "112", "6,483,017", "0", " "],
            ],
            "groups": [
                {"title": "股票", "span": 2},
                {"title": "融資", "span": 6},
                {"title": "融券", "span": 6},
                {"title": "", "span": 1},
                {"title": "", "span": 1},
            ],
            "notes": [],
        },
    ],
}

# TPEx 三大法人/融资融券 fixture（模拟端点恢复后的结构，字段名基于文档/社区资料）
# 来源: https://www.tpex.org.tw/openapi/v1/tpex_mainboard_3big_traders_daily
# ⚠ 当前端点在台湾境外被 302 重定向，以下 fixture 仅用于测试解析逻辑。
_FIXTURE_TPEX_3INSTI: list[dict[str, Any]] = [
    {
        "SecuritiesCompanyCode": "6269",
        "CompanyName": "台郡科技",
        "ForeignInvestorsNetBuySell": "1500",
        "InvestmentTrustNetBuySell": "-200",
        "DealersNetBuySell": "300",
        "Total": "1600",
        "Date": "1130105",
    },
    {
        "SecuritiesCompanyCode": "4958",
        "CompanyName": "臻鼎-KY",
        "ForeignInvestorsNetBuySell": "-3000",
        "InvestmentTrustNetBuySell": "500",
        "DealersNetBuySell": "-100",
        "Total": "-2600",
        "Date": "1130105",
    },
]

# TPEx 融资融券 fixture（字段名基于文档/社区资料）
_FIXTURE_TPEX_MARGN: list[dict[str, Any]] = [
    {
        "SecuritiesCompanyCode": "4958",
        "CompanyName": "臻鼎-KY",
        "MarginPurchase": "150",
        "MarginSales": "200",
        "MarginCashPayment": "5",
        "MarginYesterdayBalance": "3000",
        "MarginBalance": "2945",
        "MarginLimit": "500000",
        "ShortSale": "80",
        "ShortCovering": "60",
        "StockPayment": "0",
        "ShortYesterdayBalance": "100",
        "ShortBalance": "120",
        "ShortLimit": "500000",
        "OffsetLots": "0",
        "Remark": "",
        "Date": "1130105",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 辅助：从 T86 data 中找 2330 行并验算期望值
# ─────────────────────────────────────────────────────────────────────────────

def _expected_2330_institutional():
    """根据 fixture 数据预期的 2330 三大法人结果。"""
    row = _FIXTURE_T86["data"][1]  # index 1 = 2330 行
    # foreign_net = col[4] + col[7] = -7,850,458 + 0 = -7,850,458
    # trust_net   = col[10] = 27,919
    # dealer_net  = col[11] = 74,132
    # total_net   = col[18] = -7,748,407
    return {
        "foreign_net": -7850458,
        "trust_net": 27919,
        "dealer_net": 74132,
        "total_net": -7748407,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 测试: _normalize_stock_code
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeStockCode:
    def test_bare_digits(self):
        assert mod._normalize_stock_code("2330") == "2330"

    def test_tw_prefix_upper(self):
        assert mod._normalize_stock_code("TW2330") == "2330"

    def test_tw_prefix_lower(self):
        assert mod._normalize_stock_code("tw2330") == "2330"

    def test_dot_tw_suffix(self):
        assert mod._normalize_stock_code("2330.TW") == "2330"

    def test_dot_two_suffix(self):
        assert mod._normalize_stock_code("4958.TWO") == "4958"

    def test_dot_tw_lower(self):
        assert mod._normalize_stock_code("2330.tw") == "2330"

    def test_strip_whitespace(self):
        assert mod._normalize_stock_code("  2330  ") == "2330"

    def test_non_numeric_code(self):
        # 非纯数字代码（如 ETF）也能正确处理
        assert mod._normalize_stock_code("0050.TW") == "0050"


# ─────────────────────────────────────────────────────────────────────────────
# 测试: _safe_int
# ─────────────────────────────────────────────────────────────────────────────

class TestSafeInt:
    def test_comma_number(self):
        assert mod._safe_int("1,234,567") == 1234567

    def test_negative_comma(self):
        assert mod._safe_int("-7,850,458") == -7850458

    def test_plain_int(self):
        assert mod._safe_int("27919") == 27919

    def test_zero(self):
        assert mod._safe_int("0") == 0

    def test_empty_string(self):
        assert mod._safe_int("") is None

    def test_dash(self):
        assert mod._safe_int("-") is None

    def test_none_input(self):
        assert mod._safe_int(None) is None

    def test_int_input(self):
        assert mod._safe_int(42) == 42

    def test_float_string(self):
        assert mod._safe_int("74132.0") == 74132


# ─────────────────────────────────────────────────────────────────────────────
# 测试: get_institutional_investors（TSE 路径，模拟 T86 响应）
# ─────────────────────────────────────────────────────────────────────────────

class TestGetInstitutionalInvestors:
    def _patch_get_json(self, return_value):
        return patch.object(mod, "_get_json", return_value=return_value)

    def test_tse_2330_returns_correct_values(self):
        """验证 2330 三大法人数据正确解析（foreign_net/trust_net/dealer_net/total_net）。"""
        expected = _expected_2330_institutional()
        with self._patch_get_json(_FIXTURE_T86):
            result = mod.get_institutional_investors("2330", market="TSE", date="20240105")

        assert result is not None
        assert result["stock_code"] == "2330"
        assert result["market"] == "TSE"
        assert result["date"] == "2024-01-05"

        # 类型必须为 int
        assert isinstance(result["foreign_net"], int)
        assert isinstance(result["trust_net"], int)
        assert isinstance(result["dealer_net"], int)
        assert isinstance(result["total_net"], int)

        # 数值与 fixture 一致
        assert result["foreign_net"] == expected["foreign_net"], (
            f"foreign_net: expected {expected['foreign_net']}, got {result['foreign_net']}"
        )
        assert result["trust_net"] == expected["trust_net"]
        assert result["dealer_net"] == expected["dealer_net"]
        assert result["total_net"] == expected["total_net"]

    def test_tw_prefix_normalization(self):
        """TW2330 应等同于 2330。"""
        with self._patch_get_json(_FIXTURE_T86):
            result = mod.get_institutional_investors("TW2330", market="TSE", date="20240105")
        assert result is not None
        assert result["stock_code"] == "2330"

    def test_tw2330_lower_prefix(self):
        """tw2330 应等同于 2330。"""
        with self._patch_get_json(_FIXTURE_T86):
            result = mod.get_institutional_investors("tw2330", market="TSE", date="20240105")
        assert result is not None
        assert result["stock_code"] == "2330"

    def test_dot_tw_suffix_normalization(self):
        """2330.TW 应等同于 2330。"""
        with self._patch_get_json(_FIXTURE_T86):
            result = mod.get_institutional_investors("2330.TW", market="TSE", date="20240105")
        assert result is not None
        assert result["stock_code"] == "2330"

    def test_get_json_returns_none_yields_none(self):
        """_get_json 返回 None 时应优雅地返回 None，不抛异常。"""
        with self._patch_get_json(None):
            result = mod.get_institutional_investors("2330", market="TSE", date="20240105")
        assert result is None

    def test_stat_not_ok_returns_none(self):
        """stat 不为 OK 时应返回 None。"""
        bad_data = {"stat": "很抱歉，沒有符合條件的資料!", "date": None, "data": []}
        with self._patch_get_json(bad_data):
            result = mod.get_institutional_investors("2330", market="TSE", date="20240105")
        assert result is None

    def test_stock_not_in_data_returns_none(self):
        """数据中无此股票时应返回 None。"""
        with self._patch_get_json(_FIXTURE_T86):
            result = mod.get_institutional_investors("9999", market="TSE", date="20240105")
        assert result is None

    def test_tse_foreign_net_sign_correct_for_net_sell(self):
        """2330 当日外资净卖出，foreign_net 应为负值。"""
        with self._patch_get_json(_FIXTURE_T86):
            result = mod.get_institutional_investors("2330", market="TSE", date="20240105")
        assert result is not None
        assert result["foreign_net"] < 0, "2330 外资当日净卖出，应为负值"

    def test_tse_total_net_sign_correct_for_net_sell(self):
        """2330 三大法人合计净卖出，total_net 应为负值。"""
        with self._patch_get_json(_FIXTURE_T86):
            result = mod.get_institutional_investors("2330", market="TSE", date="20240105")
        assert result is not None
        assert result["total_net"] < 0

    def test_auto_market_tries_tse_first(self):
        """market=None 时应先尝试 TSE，若成功则直接返回（不尝试 OTC）。"""
        with self._patch_get_json(_FIXTURE_T86):
            result = mod.get_institutional_investors("2330", date="20240105")
        # TSE fixture 包含 2330，应成功
        assert result is not None
        assert result["market"] == "TSE"

    def test_otc_with_tpex_csv_fixture(self):
        """OTC 路径：解析 TPEx insti/dailyTrade CSV（24 欄；foreign=[10] trust=[13] dealer=[22] total=[23]）。"""
        row = ["4958", "臨時電子",
               "0", "0", "0", "0", "0", "0",      # 2-7
               "0", "0", "-3000",                 # 8-10 外資(含自營)=[10]
               "0", "0", "500",                   # 11-13 投信=[13]
               "0", "0", "0", "0", "0", "0",      # 14-19
               "0", "0", "-100",                  # 20-22 自營合計=[22]
               "-2600"]                           # 23 三大法人合計
        with patch.object(mod, "_fetch_tpex_otc_insti_map", return_value={"4958": row}):
            result = mod.get_institutional_investors("4958", market="OTC")
        assert result is not None
        assert result["market"] == "OTC"
        assert result["foreign_net"] == -3000
        assert result["trust_net"] == 500
        assert result["dealer_net"] == -100
        assert result["total_net"] == -2600

    def test_otc_stock_not_found_returns_none(self):
        """OTC CSV 中无此股票时返回 None。"""
        with patch.object(mod, "_fetch_tpex_otc_insti_map", return_value={"4958": ["4958"] + ["0"] * 23}):
            result = mod.get_institutional_investors("0000", market="OTC")
        assert result is None

    def test_exception_in_get_json_returns_none(self):
        """_get_json 抛出异常时应捕获并返回 None。"""
        with patch.object(mod, "_get_json", side_effect=RuntimeError("network error")):
            result = mod.get_institutional_investors("2330", market="TSE", date="20240105")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 测试: get_margin_balance（TSE 路径）
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMarginBalance:
    def _patch_get_json(self, return_value):
        return patch.object(mod, "_get_json", return_value=return_value)

    def test_tse_2330_openapi_parsing(self):
        """验证 openapi MI_MARGN dict 格式正确解析。"""
        with self._patch_get_json(_FIXTURE_MI_MARGN_OPENAPI):
            result = mod.get_margin_balance("2330", market="TSE")

        assert result is not None
        assert result["stock_code"] == "2330"
        assert result["market"] == "TSE"

        # 类型断言
        assert isinstance(result["margin_buy"], int)
        assert isinstance(result["margin_sell"], int)
        assert isinstance(result["margin_balance"], int)
        assert isinstance(result["short_sell"], (int, type(None)))
        assert isinstance(result["short_cover"], int)
        assert isinstance(result["short_balance"], int)

        # 数值验证（来自 fixture）
        assert result["margin_buy"] == 1183
        assert result["margin_sell"] == 1590
        assert result["margin_balance"] == 27964
        assert result["short_cover"] == 69   # 融券买进（回补）= 融券買進字段
        assert result["short_balance"] == 1

    def test_tse_margin_usage_pct_computed(self):
        """融资使用率应根据余额和限额自动计算。"""
        with self._patch_get_json(_FIXTURE_MI_MARGN_OPENAPI):
            result = mod.get_margin_balance("2330", market="TSE")
        assert result is not None
        assert result["margin_usage_pct"] is not None
        # 27964 / 6483131 * 100 ≈ 0.4314%
        expected_pct = round(27964 / 6483131 * 100, 4)
        assert abs(result["margin_usage_pct"] - expected_pct) < 0.001

    def test_tse_2330_with_date_rwd_parsing(self):
        """验证 rwd tables 格式（指定日期）正确解析。"""
        with self._patch_get_json(_FIXTURE_MI_MARGN_RWD):
            result = mod.get_margin_balance("2330", market="TSE", date="20240105")

        assert result is not None
        assert result["stock_code"] == "2330"
        assert result["market"] == "TSE"
        assert result["date"] == "2024-01-05"

        # rwd fixture: 2330 行 = [316, 79, 1, 13655, 13891, 6483017, 40, 14, 0, 138, 112, 6483017, 0, ' ']
        # [2]=买进=316, [3]=卖出=79, [6]=今日余额=13891, [8]=融券买进=40, [9]=卖出=14, [12]=融券余额=112
        assert result["margin_buy"] == 316
        assert result["margin_sell"] == 79
        assert result["margin_balance"] == 13891
        assert result["short_cover"] == 40   # [8]=融券買進（回补）
        assert result["short_sell"] == 14    # [9]=融券賣出
        assert result["short_balance"] == 112

    def test_rwd_margin_usage_pct_computed(self):
        """rwd 路径融资使用率正确计算。"""
        with self._patch_get_json(_FIXTURE_MI_MARGN_RWD):
            result = mod.get_margin_balance("2330", market="TSE", date="20240105")
        assert result is not None
        assert result["margin_usage_pct"] is not None
        # 13891 / 6483017 * 100
        expected_pct = round(13891 / 6483017 * 100, 4)
        assert abs(result["margin_usage_pct"] - expected_pct) < 0.001

    def test_code_normalization_tw_prefix(self):
        """TW2330 应等同于 2330。"""
        with self._patch_get_json(_FIXTURE_MI_MARGN_OPENAPI):
            result = mod.get_margin_balance("TW2330", market="TSE")
        assert result is not None
        assert result["stock_code"] == "2330"

    def test_code_normalization_dot_tw(self):
        """2330.TW 应等同于 2330。"""
        with self._patch_get_json(_FIXTURE_MI_MARGN_OPENAPI):
            result = mod.get_margin_balance("2330.TW", market="TSE")
        assert result is not None
        assert result["stock_code"] == "2330"

    def test_get_json_returns_none_yields_none(self):
        """_get_json 返回 None 时优雅返回 None。"""
        with self._patch_get_json(None):
            result = mod.get_margin_balance("2330", market="TSE")
        assert result is None

    def test_empty_list_yields_none(self):
        """_get_json 返回空列表时优雅返回 None。"""
        with self._patch_get_json([]):
            result = mod.get_margin_balance("2330", market="TSE")
        assert result is None

    def test_stock_not_in_data_returns_none(self):
        """数据中无此股票时返回 None。"""
        with self._patch_get_json(_FIXTURE_MI_MARGN_OPENAPI):
            result = mod.get_margin_balance("9999", market="TSE")
        assert result is None

    def test_exception_returns_none(self):
        """_get_json 抛出异常时应捕获并返回 None。"""
        with patch.object(mod, "_get_json", side_effect=RuntimeError("network error")):
            result = mod.get_margin_balance("2330", market="TSE")
        assert result is None

    def test_otc_with_tpex_fixture(self):
        """OTC 路径：www T+0 不可用时回退 openapi（list-of-dicts fixture）解析正确。"""
        with patch.object(mod, "_get_tpex_www_json", return_value=None), \
             self._patch_get_json(_FIXTURE_TPEX_MARGN):
            result = mod.get_margin_balance("4958", market="OTC")

        assert result is not None
        assert result["market"] == "OTC"
        assert result["margin_buy"] == 150
        assert result["margin_sell"] == 200
        assert result["margin_balance"] == 2945
        assert result["short_sell"] == 80
        assert result["short_cover"] == 60
        assert result["short_balance"] == 120

    def test_otc_margin_usage_pct(self):
        """OTC 融资使用率正确计算（openapi 回退路径）。"""
        with patch.object(mod, "_get_tpex_www_json", return_value=None), \
             self._patch_get_json(_FIXTURE_TPEX_MARGN):
            result = mod.get_margin_balance("4958", market="OTC")
        assert result is not None
        assert result["margin_usage_pct"] is not None
        expected_pct = round(2945 / 500000 * 100, 4)
        assert abs(result["margin_usage_pct"] - expected_pct) < 0.001

    def test_auto_market_tries_tse_first(self):
        """market=None 时先尝试 TSE。"""
        with self._patch_get_json(_FIXTURE_MI_MARGN_OPENAPI):
            result = mod.get_margin_balance("2330")
        assert result is not None
        assert result["market"] == "TSE"


# ─────────────────────────────────────────────────────────────────────────────
# 测试: _format_date_yyyymmdd
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatDate:
    def test_yyyymmdd(self):
        assert mod._format_date_yyyymmdd("20240105") == "2024-01-05"

    def test_with_dashes(self):
        assert mod._format_date_yyyymmdd("2024-01-05") == "2024-01-05"

    def test_none_input(self):
        assert mod._format_date_yyyymmdd(None) is None

    def test_short_string(self):
        assert mod._format_date_yyyymmdd("20240") is None


# ─────────────────────────────────────────────────────────────────────────────
# 测试: _get_json HTML 响应处理
# ─────────────────────────────────────────────────────────────────────────────

class TestGetJsonHTMLFallback:
    """验证 _get_json 在收到 HTML 响应时返回 None（如 TPEx 重定向场景）。"""

    def test_html_response_returns_none(self):
        """HTML 响应（如 TPEx 重定向）应返回 None，不抛异常。"""
        html_bytes = b"<!DOCTYPE html><html><head><title>302 Found</title></head></html>"

        class FakeResp:
            def read(self):
                return html_bytes
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with patch("data_provider.twse_openapi.urlopen", return_value=FakeResp()):
            result = mod._get_json("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_3big_traders_daily")
        assert result is None

    def test_url_error_returns_none(self):
        """URLError 应返回 None，不抛异常。"""
        from urllib.error import URLError
        with patch("data_provider.twse_openapi.urlopen", side_effect=URLError("timeout")):
            result = mod._get_json("https://example.com/api")
        assert result is None

    def test_http_error_returns_none(self):
        """HTTPError 应返回 None，不抛异常。"""
        from urllib.error import HTTPError
        with patch("data_provider.twse_openapi.urlopen",
                   side_effect=HTTPError("url", 403, "Forbidden", {}, None)):
            result = mod._get_json("https://example.com/api")
        assert result is None
