# 「盤前展望」模組 — Scope / 計畫

> 狀態:**v0 + v1 已實作**(opt-in,預設關閉)。決策已拍板:輸出形式 **A(大盤復盤報告新增段)**、
> **要做無 Shioaji 降級版**、**opt-in**;台指期帳號權限**不確定**→以降級路徑保護(無夜盤資料時僅憑美股盤後 + ADR)。
> v1 已加:**台積電 ADR 溢價、開盤前定調(偏多/偏空/中性)、盤前時段閘控、隔夜資料標註**。
> 背景決策見 memory `tw-market-intl-context`:台指期**不**放進大盤復盤的「國際情勢背景」block,
> 因兩者**時間粒度不同**——backdrop 是日級慢變數,盤前展望是「美股盤後 → 台股開盤」的隔夜前瞻。

---

## 1. 目標與定位

- **要解的問題**:相關性研究顯示,台股與美系指標**同日相關≈0、隔夜領先≈0.5+**(SOX 0.56、SPX 0.52)。
  也就是「**昨晚美股/台指期夜盤** → **今早台股開盤**」這道隔夜缺口,是目前系統沒覆蓋的。
- **盤前展望** = 在台股開盤前,綜合「台指期夜盤 + 美股盤後 + 既有國際背景」給出**今日開盤前的方向預判與關注點**。
- **定位**:盤前時段(premarket)觸發的**前瞻**輸出;與「盤後大盤復盤」是兩個不同時間點、不同用途的東西。

---

## 2. 資料來源(候選)

| 訊號 | 來源 | 狀態 | 備註 |
|---|---|---|---|
| **台指期夜盤**(TXF 收盤、漲跌、未平倉) | **Shioaji**(`shioaji_tw_fetcher.py` 已整合,但目前無期貨取數) | 需新增 | 夜盤 ~15:00–次日05:00;yfinance 覆蓋差,故走 Shioaji |
| 美股盤後/收盤(SPX、Nasdaq、SOX) | yfinance(已用於 backdrop) | 已有 | 直接複用 `get_global_macro_indicators` 同套取數 |
| 台積電 ADR 溢價(可選) | yfinance `TSM` vs 2330 | 可選 | ADR 相對溢/折價是開盤強弱的領先指標 |
| 國際背景(DXY/VIX/US10Y) | 既有 backdrop | 已有 | 共用 |

**關鍵相依**:台指期夜盤需 **Shioaji 連線(登入/憑證)**。無 Shioaji 時要能**優雅降級**(僅用美股盤後 + backdrop 給出較弱版本,或不輸出)。

---

## 3. 觸發時機

- 走既有 `src/core/trading_calendar.py` 的 `MarketPhase.PREMARKET`(已存在 premarket 概念)。
- 台股盤前約 **07:00–08:45**(08:45 期貨開盤、09:00 現貨開盤)觸發。
- 與既有 scheduler 整合;**僅交易日盤前**執行,非交易日跳過。

---

## 4. 輸出形式(**待你決定**,影響最大)

| 選項 | 說明 | 取捨 |
|---|---|---|
| A. 大盤復盤報告新增「盤前展望」段 | 復用現有報告管線,盤前時段在報告頂部加一段 | 改動小;但和「盤後復盤」混在同一份報告,語意略雜 |
| B. 獨立盤前推送(通知渠道) | 早上開盤前單獨發一則(Telegram/Bot 等) | 最貼近使用情境;需接通知管線與排程 |
| C. Web/API 新卡片 | 前端新增「盤前展望」卡片 | 改動面最大(API+Web);適合常駐看板 |

---

## 5. Fail-safe / 護欄(沿用專案慣例)

- 單一訊號(台指期/美股/ADR)失敗 → 跳過該訊號,不中斷;全失敗 → 不輸出盤前展望。
- Shioaji 不可用 → 降級為「美股盤後 + 國際背景」弱版,或明確標示「夜盤資料不可用」。
- 開關化:`PREMARKET_OUTLOOK_ENABLED`(預設?待定),`.env.example` + config_registry 同步。
- **不對個股**:盤前展望是大盤層級前瞻,不逐檔。

---

## 6. 決策結果（已拍板）

1. **輸出形式**:**A — 大盤復盤報告新增「盤前展望」段**(注入 zh 模板頂部,日期之後、主要指數之前)。
2. **Shioaji 期貨取數**:帳號是否可取夜盤 TXF **不確定** → **已做降級版**:取不到夜盤(無 Shioaji / 無期貨權限 / 快照失敗)時,自動退為「僅美股盤後」,並在報告標註「夜盤資料不可用」。
3. **預設開關**:**opt-in**,`PREMARKET_OUTLOOK_ENABLED=false` 預設關閉。
4. **訊號範圍**:v0 = 台指期夜盤 + 美股盤後(復用國際背景的 SOX/SPX/Nasdaq/VIX);ADR 溢價列入 v1。
5. **方向預判**:v0 只給「數據 + 一句定位」,由 LLM 解讀;明確偏多/偏空定調列入 v1。

## 7. v0 已實作內容

- `data_provider/shioaji_tw_fetcher.py`:`_ShioajiSession.resolve_futures_front_month("TXF")`(R1 連續近月優先,否則挑交割日最近實體合約)+ `ShioajiTwFetcher.get_tx_night_quote()`(快照近月,全 try/except 守護)。
- `data_provider/base.py`:`DataFetcherManager.get_tx_night_quote()` 委派(不可用回 None)。
- `src/market_analyzer.py`:`MarketOverview.premarket_outlook` 欄位;`get_market_overview` step 4.6(**僅 region=tw + opt-in** 觸發);`_get_premarket_outlook`(fail-safe + 降級);`_build_premarket_outlook_block`(完整/降級/空);注入 zh 模板頂部。
- `src/config.py` / `config_registry.py` / `.env.example`:`PREMARKET_OUTLOOK_ENABLED`(opt-in)。
- `tests/test_premarket_outlook.py`:13 項(取數/委派/fail-safe/降級/渲染/config 預設)。

**已知限制 / 待驗證**:台指期夜盤需 Shioaji 帳號具**期貨行情權限**(本機未實連驗證,靠降級路徑保護);ADR 溢價/方向定調為**啟發式**,需以實盤命中率回測校準(v2)。

## 8. v1 已實作內容

- `data_provider/yfinance_fetcher.py`:`get_tsmc_adr_premium()`(TSM × USDTWD ÷ 5 vs 2330 收盤;免 Shioaji)。
- `data_provider/base.py`:`DataFetcherManager.get_tsmc_adr_premium()` 委派。
- `src/market_analyzer.py`:
  - `_is_premarket_window()` 走 `trading_calendar.infer_market_phase("tw")`,盤中/午休/收盤競價/盤後不掛盤前展望;盤前/非交易日/無法判定則放行。
  - `_compute_premarket_bias()` 由台指期夜盤(權重2)+ SOX + ADR 溢價 + VIX 飆升合成**偏多/偏空/中性**(透明、附依據)。
  - `_get_premarket_outlook` 增取 ADR + 定調;`_build_premarket_outlook_block` 渲染定調行、ADR 行、隔夜資料標註。
- `tests/test_premarket_outlook.py`:擴充至 19 項(含 ADR 計算、bias 多空、phase 閘控、渲染)。

## 9. 後續分期

- **v2**:Web/API 卡片、歷史留存、**命中率回測**(校準 bias 權重與 ADR 閾值)、方向定調的信心分數。
