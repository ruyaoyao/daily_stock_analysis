# 台股支持说明（Shioaji + TWSE/TPEx OpenAPI）

本文件说明本系统对台湾股市（上市 TSE / 上柜 OTC）的支持范围、配置方式与已知限制。

> 数据来源分工：行情（日线 K 线、即时快照、个股名称）来自永丰金 **Shioaji**；
> 三大法人买卖超、融资融券余额来自 **TWSE / TPEx OpenAPI**（公开资料，无需金钥）；
> 大盘指数（加权 / 柜买）来自 **yfinance**（^TWII / ^TWOII）。

---

## 1. 代码格式

台股代码与 A 股（6 位）/ 港股（5 位）纯数字格式重叠，因此**必须带显式 `tw` 前缀**或 `.TW` / `.TWO` 后缀，系统才会路由到台股数据源：

| 输入 | 归一化 | 说明 |
| --- | --- | --- |
| `tw2330` | `TW2330` | 上市个股（台积电） |
| `tw6271` | `TW6271` | 上柜个股 |
| `tw0050` / `tw00878` | `TW0050` / `TW00878` | ETF |
| `2330.TW` | `TW2330` | 后缀写法（上市） |
| `6271.TWO` | `TW6271` | 后缀写法（上柜） |

纯数字（如 `2330`、`600519`）不会被识别为台股，避免与 A 股 / 港股冲突。

自选股示例：

```bash
STOCK_LIST=tw2330,tw2454,tw0050
```

---

## 2. 申请 Shioaji API

1. 于**永丰金证券**开立证券户（线上或临柜）。
2. 登入永丰金证券网站，进入 API 服务，**线上签署 API 使用同意书**。
3. 建立 **API Key / Secret Key**。
4. （可选）下载 **CA 凭证**（`Sinopac.pfx`）。查询行情**不需要** CA 凭证，仅下单需要。

官方文档：
- Shioaji 文档：https://sinotrade.github.io/
- 使用限制：https://sinotrade.github.io/tutor/limit/ （同一 person_id 最多 5 条连线、行情查询 50 次 / 5 秒等）

---

## 3. 环境变量配置

在 `.env` 中配置（仅在同时设置 API Key 与 Secret Key 时才会启用台股数据源）：

```bash
SHIOAJI_API_KEY=          # 永丰金 API Key
SHIOAJI_SECRET_KEY=       # 永丰金 Secret Key
SHIOAJI_PERSON_ID=        # 身份证字号（仅 CA 凭证启用时需要）
SHIOAJI_CA_PATH=          # CA 凭证路径（可选，查询行情不需要）
SHIOAJI_CA_PASSWORD=      # CA 凭证密码（可选）
SHIOAJI_SIMULATION=false  # true=模拟环境（测试用）

# 大盘复盘台股区域（加权 ^TWII / 柜买 ^TWOII）
MARKET_REVIEW_REGION=tw
```

依赖安装：

```bash
pip install shioaji          # 已加入 requirements.txt
```

未安装 `shioaji` 或未配置金钥时，系统不会实例化台股数据源；台股代码将报告“无可用数据源”，不影响 A 股 / 港股 / 美股流程。

---

## 4. 支持的功能与对应数据源

| 功能 | 台股对应 | 数据来源 |
| --- | --- | --- |
| 日线 K 线 | `api.kbars()`（1 分钟 K 重采样为日线 OHLCV） | Shioaji |
| 即时报价 | `api.snapshots()` | Shioaji |
| 个股名称 / 交易所归属 | contract 属性 | Shioaji |
| 主力资金流（→ 三大法人买卖超） | 外资 / 投信 / 自营商 买卖超 | TWSE T86（上市）/ TPEx OpenAPI（上柜） |
| 融资融券 | 融资融券余额 | TWSE MI_MARGN（上市）/ TPEx OpenAPI（上柜） |
| 大盘指数 | 加权指数 ^TWII、柜买指数 ^TWOII | yfinance |

### 上市（TSE）vs 上柜（OTC）

- 合约解析顺序：先 `api.Contracts.Stocks[code]`（统一查询），找不到再依次试 `TSE` / `OTC`。
- 三大法人 / 融资融券会依 Shioaji 合约的交易所自动选择 TWSE（上市）或 TPEx（上柜）OpenAPI。

### 台股财经新闻（TaiwanRSS，免 API Key）

台股个股 / 大盘复盘的新闻情报由内置 RSS 新闻源 `TaiwanRSS` 提供，**免费、免 API Key、默认启用**：

- 默认聚合三个繁中财经 RSS 源：Yahoo 股市（个股新闻，常含「名称(代码)」）、中央社财经（总经）、鉅亨网头条（广度）。
- 按查询中的**个股名称**与 **4 位台股代码**过滤；**纯英文查询（美股/港股）会自动跳过**，不污染其他市场结果。
- 多 feed 抓取结果在 TTL 内共享缓存（默认 5 分钟），整轮自选股分析复用同一批解析结果；**单一 feed 失败会被跳过**，不影响主分析流程。
- 与其他搜索源（Tavily / Brave / Bocha / SerpAPI / SearXNG 等）共用统一的新闻时效窗口、关联度排序与 fallback 逻辑；当配置了有 key 的源时，`TaiwanRSS` 作为免费兜底参与排序。
- 相关配置：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `TW_RSS_NEWS_ENABLED` | `true` | 是否启用台股 RSS 新闻源；设为 `false` 关闭 |
| `TW_RSS_FEED_URLS` | 空（用内置默认源） | 逗号分隔的自定义 RSS feed 列表，覆盖默认源 |

### 首页个股搜索下拉中的台股

- 下拉候选来自静态索引 `stocks.index.json`，与 `MARKET_TW_ENABLED` 无关（后者只控制抓取/分析/大盘复盘）。
- 仓库已内置一份精选台股清单（常用 ETF + 权值股，见 `data/stock_list_tw.csv`），其条目带 `tw` 前缀（如 `tw2330`、`tw0050`），选中即提交可路由代码；输入纯数字（如 `2330`）也可命中。
- 扩充清单：编辑 `data/stock_list_tw.csv` 后执行 `python scripts/generate_index_from_csv.py --merge-tw`，会保留其他市场条目、幂等替换台股条目，并同步 `apps/dsa-web/public` / `static` / `data/cache` 三处索引。
- 即使某代码不在下拉清单中，仍可直接输入 `tw<代码>` 并回车触发分析（后端识别 `tw` 前缀 / `.TW` 后缀经 Shioaji 取数）。
- 本地若不希望 48 小时远端刷新用上游（无台股）索引覆盖本地缓存，可设 `STOCK_INDEX_REMOTE_UPDATE_ENABLED=false`。

---

## 5. 已知限制 / 台股暂不支持

以下能力在台股**暂不支持**，调用时优雅降级（返回 `None` / 空），不会抛异常中断整体流程：

- **筹码分布**（A 股 `ChipDistribution`）：台股无对应免密钥来源，返回 `None` 并记录 warning。
- **板块 / 概念涨跌榜、市场涨跌家数（breadth）**：台股大盘复盘的 `has_market_stats` / `has_sector_rankings` 为 `False`，仅做指数级复盘。
- **三大法人 / 融资融券尚未接入个股 LLM 分析层**：数据方法（`ShioajiTwFetcher.get_institutional_investors` / `get_margin_balance`）已可用并有单测覆盖，但暂未注入个股分析报告（保持与现有分析层契约一致，避免越界改动）。
- **兴柜股票、期货 / 选择权**：不支持。
- 历史资料可查询区间受 Shioaji 限制（个股自 2020-03-02 起）。

---

## 6. 行为说明

- 数据质量：TWSE/TPEx 三大法人与融资融券为盘后日资料（约 15:00 后更新）；盘中查询返回上一交易日。
- 稳定性：单一来源（Shioaji 连线、某个 OpenAPI endpoint）失败不应拖垮分析主流程；行情类失败返回 `None`，日线失败由上层 failover 处理。
- 大盘复盘 `both` 仍仅含 cn+hk+us（历史别名）；台股需以 `MARKET_REVIEW_REGION=tw` 显式选取，或使用逗号组合如 `cn,tw`。
