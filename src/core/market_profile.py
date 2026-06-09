# -*- coding: utf-8 -*-
"""
大盘复盘市场区域配置

定义各市场区域的指数、新闻搜索词、Prompt 提示等元数据，
供 MarketAnalyzer 按 region 切换 A 股/美股复盘行为。
"""

from dataclasses import dataclass
from typing import List


@dataclass
class MarketProfile:
    """大盘复盘市场区域配置"""

    region: str  # "cn" | "us"
    # 用于判断整体走势的指数代码，cn 用上证 000001，us 用标普 SPX
    mood_index_code: str
    # 新闻搜索关键词
    news_queries: List[str]
    # 指数点评 Prompt 提示语
    prompt_index_hint: str
    # 市场概况是否包含涨跌家数、涨停跌停（A 股有，美股无）
    has_market_stats: bool
    # 市场概况是否包含板块涨跌（A 股有，美股暂无）
    has_sector_rankings: bool
    # 是否提供大盘层级筹码面（三大法人买卖超合计 + 融资融券余额）；目前仅台股
    has_chip_stats: bool = False


CN_PROFILE = MarketProfile(
    region="cn",
    mood_index_code="000001",
    news_queries=[
        "A股 大盘 复盘",
        "股市 行情 分析",
        "A股 市场 热点 板块",
    ],
    prompt_index_hint="分析上证、深证、创业板等各指数走势特点",
    has_market_stats=True,
    has_sector_rankings=True,
)

US_PROFILE = MarketProfile(
    region="us",
    mood_index_code="SPX",
    news_queries=[
        "美股 大盘",
        "US stock market",
        "S&P 500 NASDAQ",
    ],
    prompt_index_hint="分析标普500、纳斯达克、道指等各指数走势特点",
    has_market_stats=False,
    has_sector_rankings=False,
)

HK_PROFILE = MarketProfile(
    region="hk",
    mood_index_code="HSI",
    news_queries=[
        "港股 大盘 复盘",
        "Hong Kong stock market",
        "恒生指数 行情",
    ],
    prompt_index_hint="分析恒生指数、恒生科技指数、国企指数等各指数走势特点",
    has_market_stats=False,
    has_sector_rankings=False,
)


TW_PROFILE = MarketProfile(
    region="tw",
    mood_index_code="TWII",
    news_queries=[
        "台股 加權指數 行情",
        "台灣 集中市場 法人 買賣超",
        "Taiwan TAIEX stock market",
    ],
    prompt_index_hint="分析加權指數（TAIEX）、櫃買指數等台股各指數走勢特點",
    # 台股涨跌家数/成交额/类股涨跌幅经 TWSE OpenAPI（无需密钥）取得（上市 TWSE 口径）
    has_market_stats=True,
    has_sector_rankings=True,
    # 台股大盘筹码面：三大法人买卖超合计 + 融资融券余额（TWSE RWD，无需密钥）
    has_chip_stats=True,
)


def get_profile(region: str) -> MarketProfile:
    """根据 region 返回对应的 MarketProfile"""
    if region == "us":
        return US_PROFILE
    if region == "hk":
        return HK_PROFILE
    if region == "tw":
        return TW_PROFILE
    return CN_PROFILE
