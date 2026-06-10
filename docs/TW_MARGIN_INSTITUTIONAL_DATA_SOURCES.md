# 台股「融資融券」「三大法人買賣超」資料來源（TWSE / TPEx）

> 涵蓋**上市(TWSE)＋上櫃(TPEx)** 每日**融資融券餘額**與**三大法人買賣超**的公開資料端點、
> 日期格式、欄位對映、單位與踩雷點。**全部以實測 API 驗證（2026-06）**，免 token、免登入。
>
> 本專案實作位置：`data_provider/twse_openapi.py`（取數 + 解析）、
> `data_provider/base.py::DataFetcherManager.get_tw_stock_chip_flow()`（個股籌碼流動主備策略）、
> `data_provider/finmind_tw_fetcher.py`（FinMind 備援/主源）。

---

## 0. 全域踩雷點（先看這個）

| 項目 | TWSE（上市） | TPEx（上櫃） |
|---|---|---|
| `stat` 成功值 | `"OK"`（**大寫**） | `"ok"`（**小寫**）→ 比對請 `.upper()` |
| 日期格式 | AD 8 碼 `20260610` | ROC `115/06/10` **或** AD `2026/06/10`（兩者皆可，斜線） |
| SSL 憑證 | 正常 | **憑證缺 Subject Key Identifier → 需 `verify=False`／unverified context** |
| 鮮度 | 收盤後即為當日 | **www = T+0 當日**；**openapi = 常 T+1（落後一天）** |
| 單位 | 融資融券＝**張**；法人＝**股**（÷1000＝張） | 同左 |

其他：
- **`_recent_trading_days()` 必須從「今天」起算**，否則盤後當日資料（T86/MI_MARGN）發佈後仍只會取到前一交易日（本專案曾因從「昨天」起算而永遠落後一天，已修正並加回歸測試 `tests/test_recent_trading_days.py`）。
- **TWSE `STOCK_DAY_ALL` 會忽略 `date` 參數**，永遠回最新交易日 → 不可拿來取歷史價。
- 位置式解析：TPEx 多數表本身含重複/無標籤，**易錯位**，務必以「合計＝外資＋投信＋自營」驗證身分。
- 數字含千分位逗號與 `"--"`／`"-"`／空字串，解析前先 `replace(",","")` 並把 `-/--/空` 視為 0/None。

---

## 1. 融資融券餘額

### 1.1 上市 → TWSE www MI_MARGN（T+0）
```
# 全市場：
GET https://www.twse.com.tw/exchangeReport/MI_MARGN?date=YYYYMMDD&selectType=ALL&response=json
# 單檔（本專案實作，較輕量）：
GET https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=YYYYMMDD&selectType=STOCK&stockNo=2330&response=json
```
- 日期 AD 8 碼；`stat == "OK"`。發佈：收盤後（約 18:00–20:00 TW，依授信機構）。
- `tables[*].data` 逐行欄位（每行 ≥14 欄）：

| idx | 欄位 | idx | 欄位 |
|---|---|---|---|
| 0 | 證券代號 | 8 | 融券-買進(回補) |
| 1 | 證券名稱 | 9 | 融券-賣出 |
| 2 | 融資-買進 | 10 | 融券-現券償還 |
| 3 | 融資-賣出 | 11 | 融券-前日餘額 |
| 4 | 融資-現金償還 | 12 | 融券-今日餘額 |
| 5 | 融資-前日餘額 | 13 | 融券-次一營業日限額 |
| 6 | 融資-今日餘額 | 14 | 資券互抵 |
| 7 | 融資-次一營業日限額 | 15 | 註記 |

- `融資變動 = row[6] − row[5]`；`融券變動 = row[12] − row[11]`。`融資使用率 = row[6] / row[7] × 100`。單位**張**。
- 備援：`https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN`（list-of-dict、**無 date 欄位、常 T+1**）。

### 1.2 上櫃 → TPEx www margin/balance（T+0）
```
GET https://www.tpex.org.tw/www/zh-tw/margin/balance?date=ROC&id=&response=json
# 例 date=115/06/10；需 verify=False；stat=="ok"(小寫)
```
- `tables[0].data` 逐行欄位（每行 ≥20 欄）：

| idx | 欄位 | idx | 欄位 |
|---|---|---|---|
| 0 | 代號 | 10 | 券-前日餘額(張) |
| 1 | 名稱 | 11 | **券賣** |
| 2 | 資-前日餘額(張) | 12 | **券買(回補)** |
| 3 | 資買 | 13 | 券償 |
| 4 | 資賣 | 14 | 券-今日餘額 |
| 5 | 資-現償 | 15 | 券-屬證金 |
| 6 | 資-今日餘額(張) | 16 | 券使用率(%) |
| 7 | 資-屬證金 | 17 | 券限額 |
| 8 | 資使用率(%) | 18 | 資券相抵(張) |
| 9 | 資限額 | 19 | 備註 |

> ⚠️ **融券買賣順序與 TWSE 相反**：TPEx 是「券賣[11]、券買[12]」；TWSE 是「券買(回補)[8]、券賣[9]」。實作別錯位。
- `融資變動 = row[6] − row[2]`；`融券變動 = row[14] − row[10]`。單位**張**。
- 備援：`https://openapi.twse.com.tw/v1/exchangeReport/...`／`tpex_mainboard_margin_transactions`（英文 key、常 T+1，且境外常被 302 重定向）。

---

## 2. 三大法人買賣超

### 2.1 上市 → TWSE T86（T+0）
```
GET https://www.twse.com.tw/rwd/zh/fund/T86?date=YYYYMMDD&selectType=ALL&response=json   # 或 csv
```
- 日期 AD 8 碼；`stat == "OK"`；發佈：收盤後（約 15:00+）。
- 欄位 **19 欄**（單位**股**）：

| idx | 欄位 | idx | 欄位 |
|---|---|---|---|
| 0 | 證券代號 | 10 | 投信買賣超 |
| 1 | 證券名稱 | 11 | **自營商買賣超(合計)** |
| 2/3/4 | 外陸資(不含外資自營) 買/賣/**超** | 12/13/14 | 自營商(自行) 買/賣/超 |
| 5/6/7 | 外資自營商 買/賣/**超** | 15/16/17 | 自營商(避險) 買/賣/超 |
| 8/9/10 | 投信 買/賣/**超** | 18 | **三大法人買賣超合計** |

- **外資合計 = [4] 外陸資 + [7] 外資自營商**；自營商取 **[11] 合計**。
- 驗證恆等式：`[4] + [7] + [10] + [11] == [18]`。單位**股**（÷1000＝張）。

### 2.2 上櫃 → TPEx insti/dailyTrade（T+0）
```
GET https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=AL&date=DATE&id=&response=csv   # 或 json
# date 可用 ROC 115/06/10 或 AD 2026/06/10；需 verify=False；stat=="ok"
```
- `tables[0].data`（json）或 CSV 逐行 **24 欄**（欄位重複、每組 3 欄：買/賣/**超**）：

| 群組欄 | 意義 | 買賣超(net) idx |
|---|---|---|
| 0,1 | 代號, 名稱 | — |
| 8,9,10 | **外資及陸資合計** | **10**（已含外資自營） |
| 11,12,13 | **投信** | **13** |
| 20,21,22 | **自營商合計** | **22** |
| 23 | 三大法人合計買賣超 | 23 |

- 取 **外資=[10]、投信=[13]、自營=[22]、合計=[23]**。驗證恆等式：`[10] + [13] + [22] == [23]`。單位**股**。
- ⚠️ 取位置值前**先檢查欄位數**（`len(row) < 24` 就跳過），避免改版錯位。

> 「外資」定義差異：**TWSE 取 [4] 外陸資（不含外資自營）**；**TPEx 取 [10] 外資合計（含自營）**。
> 本專案統一取「外資合計（含自營商自營）」口徑，兩市以「合計＝外資＋投信＋自營」驗證一致。

---

## 3. 本專案實測結果（2026-06-10，盤後）

> 同一交易日，官方（TWSE/TPEx）與 FinMind **值、日期完全一致**（已交叉比對）。

**三大法人買賣超（單位：張；正＝買超）**

| 標的 | 外資 | 投信 | 自營 | 合計 | 日期 | 恆等式 |
|---|---|---|---|---|---|---|
| 2330（上市） | −15,543 | −4 | −731 | **−16,278** | 2026-06-10 | ✓ |
| 6488 環球晶（上櫃） | +373 | −771 | +143 | **−255** | 2026-06-10 | ✓ |

（2330 原始股數：外資 −15,542,862、合計 −16,277,573；6488：外資 +372,974、投信 −771,147、自營 +143,490、合計 −254,683。）

**融資融券餘額（單位：張）**

| 標的 | 融資餘額 | 融資增減 | 融券餘額 | 融資使用率 | 日期 |
|---|---|---|---|---|---|
| 2330（上市） | 28,168 | −182 | 0 | 0.43% | 2026-06-10 |
| 6488（上櫃） | 8,507 | −389 | 111 | 7.11% | 2026-06-10 |

**效能（單次取數，實測）**

| 象限 | 官方 T+0 | FinMind |
|---|---|---|
| 融資融券 上市（www MI_MARGN） | **~71ms** | ~210ms |
| 融資融券 上櫃（www margin/balance） | **~116ms** | ~148ms |
| 三大法人 上市（T86，全市場下載） | ~1,250–1,460ms | **~150ms** |
| 三大法人 上櫃（insti/dailyTrade CSV） | ~725–1,690ms（之後快取） | **~166ms** |

---

## 4. 來源策略（依實測重寫）

實測結論：**四象限的值與日期，官方與 FinMind 完全一致且皆為當日**。差別只在「權威性」與「效能」：
- **融資融券**：官方 www T+0 **既權威又最快（~70–120ms）**，且含前日餘額可算當日增減 → **官方為主**。
- **三大法人**：官方為權威來源但需下載全市場（上市 T86 ~1.3s）；FinMind 為單檔查詢 ~150ms、值一致 → **FinMind 為主、官方為權威備援**（兼顧速度與正確）。

本專案採用的主備（`get_tw_stock_chip_flow`）：

| 指標 | 主來源 | 備援 |
|---|---|---|
| 三大法人（上市/上櫃） | **FinMind**（`TaiwanStockInstitutionalInvestorsBuySell`） | 官方 TWSE T86 / TPEx `insti/dailyTrade` CSV |
| 融資融券（上市） | **官方 TWSE www `MI_MARGN`** | openapi `MI_MARGN`（T+1） |
| 融資融券（上櫃） | **官方 TPEx www `margin/balance`** | FinMind（`TaiwanStockMarginPurchaseShortSale`） |

實作要點：
- **自動市場判別採「逐日交錯」試 TSE→OTC**：避免上櫃個股先空轉 5 次上市來源（端到端由 ~12.5s 降到 ~0.9s/檔）。
- **日期視窗從今日起算**（盤後即命中當日；發佈前自動回退前一交易日）。
- 官方法人為「股」→ 統一轉「張」（÷1000，四捨五入）；FinMind 已為「張」。
- 大量批次或需更快時：可把三大法人也切到官方（權威但較慢），或補 `FINMIND_TOKEN` 提升 FinMind 配額。
- 端到端實測：個股籌碼流動每檔約 **上市 0.4s / 上櫃 0.9s**。

---

## 5. 交叉比對 / 鮮度建議

- **加權指數/成交額**：主用 TWSE `FMTQIK`（`/rwd/zh/afterTrading/FMTQIK?response=json`，T+0）；當日即時可用 MIS（`mis.twse.com.tw`，`tse_t00.tw`）。openapi 鏡像常 T+1。
- **rwd / www / MIS 端點普遍 T+0；openapi 普遍 T+1** — 要當日資料一律走 rwd/www/MIS，openapi 當備援。
- 跨市場（TWSE/TPEx）**發佈時間不同步**；涵蓋多檔時用「最近 N 日 recency window」逐日嘗試，並以**資料自帶的日期欄位**做跨源一致性校驗（避免把不同交易日混判）。

---

## 6. 來源一覽（快查）

| 用途 | 市場 | 端點 | 鮮度 | 日期格式 |
|---|---|---|---|---|
| 融資融券 | 上市 | `twse.com.tw/exchangeReport/MI_MARGN?...selectType=ALL`（或 `rwd/.../marginTrading/MI_MARGN?selectType=STOCK&stockNo=`） | T+0 | AD `20260610` |
| 融資融券 | 上櫃 | `tpex.org.tw/www/zh-tw/margin/balance?date=ROC` | T+0 | ROC `115/06/10` |
| 融資融券 | 上櫃(備) | `tpex.org.tw/openapi/v1/tpex_mainboard_margin_transactions` | T+1 | — |
| 三大法人 | 上市 | `twse.com.tw/rwd/zh/fund/T86?...selectType=ALL` | T+0 | AD |
| 三大法人 | 上櫃 | `tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=AL&date=` | T+0 | ROC 或 AD |
| 三大法人 | 上櫃(備) | `tpex.org.tw/openapi/v1/tpex_3insti_daily_trade` | T+1 | — |
| 個股收盤(上市) | 上市 | `twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL` | T+0 | ⚠️忽略 date |
| 個股收盤(上櫃) | 上櫃 | `tpex.org.tw/www/zh-tw/afterTrading/otc?type=AL&date=ROC` | T+0 | ROC |
| 大盤(指數/成交額) | — | `twse.com.tw/rwd/zh/afterTrading/FMTQIK` | T+0 | AD |
| 加權指數即時 | — | `mis.twse.com.tw/.../getStockInfo.jsp?ex_ch=tse_t00.tw` | 即時/T+0 | AD |

> 所有端點免 token；TPEx 站台需 `verify=False`、`stat` 為小寫；TWSE `stat` 為大寫。
