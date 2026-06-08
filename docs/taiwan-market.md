# 台股支持說明（Shioaji + TWSE/TPEx OpenAPI）

本文件說明本系統對台灣股市（上市 TSE / 上櫃 OTC）的支持範圍、配置方式與已知限制。

> 數據來源分工：行情（日線 K 線、即時快照、個股名稱）來自永豐金 **Shioaji**；
> 三大法人買賣超、融資融券餘額來自 **TWSE / TPEx OpenAPI**（公開資料，無需金鑰）；
> 大盤指數（加權 / 櫃買）來自 **yfinance**（^TWII / ^TWOII）。

---

## 1. 代碼格式

台股代碼與 A 股（6 位）/ 港股（5 位）純數位格式重疊，因此**必須帶顯式 `tw` 前綴**或 `.TW` / `.TWO` 後綴，系統才會路由到台股數據源：

| 輸入 | 歸一化 | 說明 |
| --- | --- | --- |
| `tw2330` | `TW2330` | 上市個股（台積電） |
| `tw6271` | `TW6271` | 上櫃個股 |
| `tw0050` / `tw00878` | `TW0050` / `TW00878` | ETF |
| `2330.TW` | `TW2330` | 後綴寫法（上市） |
| `6271.TWO` | `TW6271` | 後綴寫法（上櫃） |

純數位（如 `2330`、`600519`）不會被識別為台股，避免與 A 股 / 港股衝突。

自選股範例：

```bash
STOCK_LIST=tw2330,tw2454,tw0050
```

---

## 2. 申請 Shioaji API

1. 於**永豐金證券**開立證券戶（線上或臨櫃）。
2. 登入永豐金證券網站，進入 API 服務，**線上簽署 API 使用同意書**。
3. 建立 **API Key / Secret Key**。
4. （可選）下載 **CA 憑證**（`Sinopac.pfx`）。查詢行情**不需要** CA 憑證，僅下單需要。

官方文件：
- Shioaji 文件：https://sinotrade.github.io/
- 使用限制：https://sinotrade.github.io/tutor/limit/ （同一 person_id 最多 5 條連線、行情查詢 50 次 / 5 秒等）

---

## 3. 環境變數配置

在 `.env` 中配置（僅在同時設置 API Key 與 Secret Key 時才會啟用台股數據源）：

```bash
SHIOAJI_API_KEY=          # 永豐金 API Key
SHIOAJI_SECRET_KEY=       # 永豐金 Secret Key
SHIOAJI_PERSON_ID=        # 身份證字號（僅 CA 憑證啟用時需要）
SHIOAJI_CA_PATH=          # CA 憑證路徑（可選，查詢行情不需要）
SHIOAJI_CA_PASSWORD=      # CA 憑證密碼（可選）
SHIOAJI_SIMULATION=false  # true=模擬環境（測試用）

# 大盤復盤台股區域（加權 ^TWII / 櫃買 ^TWOII）
MARKET_REVIEW_REGION=tw
```

依賴安裝：

```bash
pip install shioaji          # 已加入 requirements.txt
```

未安裝 `shioaji` 或未配置金鑰時，系統不會實例化台股數據源；台股代碼將報告“無可用數據源”，不影響 A 股 / 港股 / 美股流程。

---

## 4. 支持的功能與對應數據源

| 功能 | 台股對應 | 數據來源 |
| --- | --- | --- |
| 日線 K 線 | `api.kbars()`（1 分鐘 K 重採樣為日線 OHLCV） | Shioaji |
| 即時報價 | `api.snapshots()` | Shioaji |
| 個股名稱 / 交易所歸屬 | contract 屬性 | Shioaji |
| 主力資金流（→ 三大法人買賣超） | 外資 / 投信 / 自營商 買賣超 | TWSE T86（上市）/ TPEx OpenAPI（上櫃） |
| 融資融券 | 融資融券餘額 | TWSE MI_MARGN（上市）/ TPEx OpenAPI（上櫃） |
| 大盤指數 | 加權指數 ^TWII、櫃買指數 ^TWOII | yfinance |

### 上市（TSE）vs 上櫃（OTC）

- 合約解析順序：先 `api.Contracts.Stocks[code]`（統一查詢），找不到再依次試 `TSE` / `OTC`。
- 三大法人 / 融資融券會依 Shioaji 合約的交易所自動選擇 TWSE（上市）或 TPEx（上櫃）OpenAPI。

### 台股財經新聞（TaiwanRSS，免 API Key）

台股個股 / 大盤復盤的新聞情報由內建 RSS 新聞源 `TaiwanRSS` 提供，**免費、免 API Key、預設啟用**：

- 默認聚合三個繁中財經 **大盤/頭條** RSS 源（Yahoo 股市新聞、中央社財經、鉅亨網頭條）。
- 查詢含 4 位台股代碼時，額外拉取四套**個股向**來源（均已在 TTL 內快取，單一源失敗跳過）：
  - **Yahoo 個股 RSS**：`https://tw.stock.yahoo.com/rss?s=代碼`
  - **Google News RSS**：`https://news.google.com/rss/search?q=...&hl=zh-TW&gl=TW`
  - **FinMind TaiwanStockNews**：`dataset=TaiwanStockNews`（免 Token 可用，配置 `FINMIND_TOKEN` 可提升配額）
- 按查詢中的**個股名稱**與 **4 位台股代碼**過濾宏觀 RSS；**個股向來源不再做二次 token 過濾**。**純英文查詢（美股/港股）會自動跳過**，不汙染其他市場結果。
- 多 feed 抓取結果在 TTL 內共享快取（默認 5 分鐘），整輪自選股分析復用同一批解析結果；**單一 feed 失敗會被跳過**，不影響主分析流程。
- 與其他搜索源（Tavily / Brave / Bocha / SerpAPI / SearXNG 等）共用統一的新聞時效窗口、關聯度排序與 fallback 邏輯；當配置了有 key 的源時，`TaiwanRSS` 作為免費兜底參與排序。
- 相關配置：

| 變數 | 默認 | 說明 |
| --- | --- | --- |
| `TW_RSS_NEWS_ENABLED` | `true` | 是否啟用台股 RSS 新聞源；設為 `false` 關閉 |
| `TW_RSS_FEED_URLS` | 空（用內建默認源） | 逗號分隔的自訂 RSS feed 列表，覆蓋默認宏觀源 |
| `TW_RSS_GOOGLE_NEWS_ENABLED` | `true` | 是否啟用 Google News RSS 個股檢索 |
| `TW_RSS_FINMIND_NEWS_ENABLED` | `true` | 是否啟用 FinMind `TaiwanStockNews` |
| `FINMIND_TOKEN` | 空 | FinMind API Token（可選；新聞與籌碼分布共用） |

### 首頁個股搜索下拉中的台股

- 下拉候選來自靜態索引 `stocks.index.json`，與 `MARKET_TW_ENABLED` 無關（後者只控制抓取/分析/大盤復盤）。
- 默認可用 `python scripts/generate_index_from_csv.py --merge-tw-listed` 從 TWSE Open API 拉取**所有上市證券**（約 1300+ 檔，含 ETF）並寫入索引；亦可用 `--merge-tw` 僅合併 `data/stock_list_tw.csv` 精選清單。條目帶 `tw` 前綴（如 `tw2330`、`tw2344`），輸入純數位（如 `2344`）也可命中。
- 擴充清單：編輯 `data/stock_list_tw.csv` 後執行 `python scripts/generate_index_from_csv.py --merge-tw`，會保留其他市場條目、冪等替換台股條目，並同步 `apps/dsa-web/public` / `static` / `data/cache` 三處索引。
- 即使某代碼不在下拉清單中，仍可直接輸入 `tw<代碼>` 並回車觸發分析（後端識別 `tw` 前綴 / `.TW` 後綴經 Shioaji 取數）。
- 本地若不希望 48 小時遠端刷新用上游（無台股）索引覆蓋本地快取，可設 `STOCK_INDEX_REMOTE_UPDATE_ENABLED=false`。

---

## 5. 已知限制 / 台股暫不支持

以下能力在台股**暫不支持**，調用時優雅降級（返回 `None` / 空），不會拋異常中斷整體流程：

- **籌碼分布**（A 股 `ChipDistribution`）：台股經 TDCC 股權分散表（Open Data）映射大戶集中度，並結合 FinMind（可選 `FINMIND_TOKEN`）或 yfinance 估算 VWAP 作為平均成本；Akshare `stock_cyq_em` 不會用於台股代碼。
- **板塊 / 概念漲跌榜、市場漲跌家數（breadth）**：台股大盤復盤的 `has_market_stats` / `has_sector_rankings` 為 `False`，僅做指數級復盤。
- **三大法人 / 融資融券尚未接入個股 LLM 分析層**：數據方法（`ShioajiTwFetcher.get_institutional_investors` / `get_margin_balance`）已可用並有單測覆蓋，但暫未注入個股分析報告（保持與現有分析層契約一致，避免越界改動）。
- **興櫃股票、期貨 / 選擇權**：不支持。
- 歷史資料可查詢區間受 Shioaji 限制（個股自 2020-03-02 起）。

---

## 6. 行為說明

- 數據質量：TWSE/TPEx 三大法人與融資融券為盤後日資料（約 15:00 後更新）；盤中查詢返回上一交易日。
- 穩定性：單一來源（Shioaji 連線、某個 OpenAPI endpoint）失敗不應拖垮分析主流程；行情類失敗返回 `None`，日線失敗由上層 failover 處理。
- 大盤復盤 `both` 仍僅含 cn+hk+us（歷史別名）；台股需以 `MARKET_REVIEW_REGION=tw` 顯式選取，或使用逗號組合如 `cn,tw`。
