# 個股分析流程與 AI Prompt 拆解

> 說明個股分析（含「報告概覽」）的資料流程、送進 LLM 的 Prompt 結構，並以 **tw2303 聯電** 當日數據示範填入後的 Prompt。
> 程式真源：`src/core/pipeline.py::analyze_stock`、`src/analyzer.py::GeminiAnalyzer.analyze / _format_prompt / SYSTEM_PROMPT`。

---

## 1. 個股分析流程

入口 `pipeline.analyze_stock()` → `analyzer.analyze()`：

| # | 步驟 | 來源 / 函式 |
|---|---|---|
| 1 | **市場階段**判定（盤前 / 盤中 / 午休 / 收盤競價 / 盤後 / 非交易日 / unknown） | `build_market_phase_context` |
| 2 | **日線 K + 趨勢分析**（均線排列、乖離率、量能、系統評分、買賣訊號） | fetcher + `trend_analyzer.analyze` |
| 3 | **基本面**（財報 / 分紅 / 主力資金流 / 籌碼分布） | `fetcher_manager.get_fundamental_context` |
| 4 | **即時增強**（量比、換手率、PE、PB、60 日漲跌） | realtime quote |
| 5 | **輿情情報**（`search_stock_news` → `format_intel_report`，可加社媒情緒） | `search_service`（新聞**標題去重**在此） |
| 6 | **台股籌碼流動**（三大法人買賣超 + 融資融券，僅台股） | `get_tw_stock_chip_flow`（T+0 來源 + 索引補回） |
| 7 | 組裝 `context` | `db.get_analysis_context` + `_enhance_context` |
| 8 | **AI 分析** | `analyze()`：組 System + User Prompt → 呼叫 LLM（litellm / 原生 Gemini，含重試與模型切換）→ 解析 JSON → `AnalysisResult` → 校驗必填欄位 + 回退補全 |
| 9 | **渲染報告** | 「報告概覽」= `dashboard.*`，由第 8 步那一次 LLM 呼叫產出 |

「報告概覽」(`apps/dsa-web/src/components/report/ReportOverview.tsx`) 渲染的是 `dashboard` 的
`core_conclusion / data_perspective / intelligence / battle_plan / phase_decision`——**全部來自同一個 Prompt**。

---

## 2. AI Prompt 結構

一次呼叫 = **System Prompt + User Prompt** 兩段。

### 2.1 System Prompt（`analyzer.py::SYSTEM_PROMPT`，靜態模板）

角色定位 +`{guidelines}`+`{skills}`+ 四大區塊：

1. **輸出格式**：強制「決策儀表盤 JSON」
   - `dashboard.core_conclusion`：一句話結論、信號燈（🟢🟡🔴⚠️）、時效、分倉建議（空倉 vs 持倉）
   - `dashboard.data_perspective`：趨勢狀態 / 價格位置 / 量能 / 籌碼
   - `dashboard.intelligence`：最新消息 / 風險警報 / 利好催化 / 業績預期 / 情緒
   - `dashboard.battle_plan`：狙擊點位（理想買 / 次優買 / 止損 / 目標）/ 倉位策略 / ✅⚠️❌ 檢查清單
   - `dashboard.phase_decision`：盤中階段七欄位（phase_context / action_window / immediate_action / watch_conditions / next_check_time / confidence_reason / data_limitations）
2. **評分標準**：80-100 強買 / 60-79 買 / 40-59 觀望 / 0-39 賣減
3. **核心原則**：結論先行、分倉建議、精確點位、檢查清單可視化、風險醒目
4. **可操作性與穩定性約束**：
   - 不得因單日漲跌或評分跨線就在買 / 賣間劇烈切換
   - 須同時參考價格位置（支撐 / 壓力）、量能 / 籌碼、主力資金流、風險事件
   - 區間內、資金流不明時優先輸出中性（持有 / 震盪 / 觀望），`decision_type` 維持 `hold`
   - 必須輸出 `phase_decision` 七欄位
   - quote/daily_bars/technical 出現 stale / fallback / missing / fetch_failed / partial / estimated 時，`confidence_level` 不得為「高」

### 2.2 User Prompt（`analyzer.py::_format_prompt`，填入當日數據）

依序注入（無資料的區塊自動略過或標註「數據缺失，無法判斷」，禁止編造）：

1. 股票基礎資訊（代碼 / 名稱 / 分析日期）
2. 市場階段段落
3. **技術面**：行情表（收 / 開 / 高 / 低 / 漲跌幅 / 量 / 額）+ 均線系統（MA5/10/20 + 形態）
4. 即時行情增強（量比 / 換手率 / PE / PB / 總市值 / 60 日漲跌）
5. 財報與分紅（營收 / 歸母淨利 / 經營現金流 / ROE / TTM 股息率）
6. 主力資金流向（主力淨流入 / 5 日 / 10 日 / 資金進出靠前板塊）
7. 籌碼分布（獲利比例 / 平均成本 / 集中度 / 籌碼狀態）
8. **台股籌碼流動**（三大法人買賣超 + 融資融券，僅台股）
9. 技術與結構分析（趨勢 / 均線排列 / 乖離率〔>5% 標警告〕/ 量能 / 系統評分 + 理由）
10. 量價變化（量 / 價較昨日；量能異常 >10 倍降權）
11. **舆情情報**（新聞，含強制時間規則：每條帶日期、超窗 / 時間未知一律忽略）
12. 分析任務 + 輸出要求 + 語言要求（鍵名不譯、`decision_type` 固定 buy/hold/sell、可讀值用中文）

---

## 3. Prompt 範例（tw2303 聯電 · 2026-06-15）

> **台股報價單位為新台幣元（NTD$ / NT$）**；下方範例中的「元」即新台幣元。
> **真實值**：行情（NT$141.5 / +5.99%）、台股籌碼流動（三大法人 / 融資融券）— 當日實測。
> **示例值**（標 `‹示例›`）：均線 / 趨勢 / PE / PB / 新聞 — 實際由 pipeline 當日填入，此處用代表值示意。

### 3.1 System（摘錄關鍵指令，完整見 §2.1）

```text
你是一位台股投资分析师，负责生成专业的【决策仪表盘】分析报告。
…（输出 dashboard JSON：core_conclusion / data_perspective / intelligence /
   battle_plan / phase_decision；评分 80-100/60-79/40-59/0-39；
   不得因单日涨跌跨线乱切买卖，须结合支撑压力 + 量能 + 资金流；
   stale/fallback/missing 时 confidence 不得为“高”；必须输出 phase_decision 七字段）
```

### 3.2 User（填入當日數據）

```markdown
# 决策仪表盘分析请求

## 📊 股票基础信息
| 项目 | 数据 |
|------|------|
| 股票代码 | **2303** |
| 股票名称 | **聯電** |
| 分析日期 | 2026-06-15 |

---
〔市场阶段〕postmarket（盘后复盘）— 依收盘数据复盘  ‹示例阶段›

## 📈 技术面数据
> 💱 本檔為台股，報價與成交額幣別為新台幣（NT$）。

### 收盘行情
| 指标 | 数值 |
|------|------|
| 收盘价 | 141.5 元（NT$） |
| 开盘价 | 134.0 元（NT$） ‹示例› |
| 最高价 | 142.0 元（NT$） ‹示例› |
| 最低价 | 133.5 元（NT$） ‹示例› |
| 涨跌幅 | +5.99% |
| 成交量 | 325,874 张 |
| 成交额 | 457.37 亿 |

### 均线系统（关键判断指标）           ‹以下均线为示例›
| 均线 | 数值 | 说明 |
|------|------|------|
| MA5 | 135.2 | 短期趋势线 |
| MA10 | 132.8 | 中短期趋势线 |
| MA20 | 130.1 | 中期趋势线 |
| 均线形态 | 多头排列 | 多头/空头/缠绕 |

### 实时行情增强数据                    ‹示例›
| 指标 | 数值 | 解读 |
|------|------|------|
| **量比** | **2.3** | 放量 |
| **换手率** | **2.6%** | |
| 市盈率(动态) | 16.8 | |
| 市净率 | 2.1 | |
| 60日涨跌幅 | +18.4% | 中期表现 |

### 个股筹码流动（三大法人 / 融资融券）   ← 真实（2026-06-15）
| 指标 | 数值 | 决策含义 |
|------|------|----------|
| 三大法人合计买卖超（2026-06-15） | -1,156 张 | 正=法人净买入，负=净卖出 |
| ├ 外资 | -24,058 张 | |
| ├ 投信 | +15,859 张 | |
| └ 自营商 | +7,043 张 | |
| 融资余额（2026-06-15） | 235,630 张 (增减 +17,720 张) | 散户杠杆，过高易回压 |
| 融券余额 | 2,840 张 (增减 +275 张) | 空方/避险力量 |
| 融资使用率 | 7.494% | |
> 法人持续净买入且融资未过热时偏多；法人净卖出叠加融资骤增需防杠杆回压。

### 技术与结构分析                      ‹示例›
| 指标 | 数值 | 说明 |
|------|------|------|
| 趋势状态 | 上升趋势 | |
| 均线排列 | 多头排列 | |
| **价格位置(MA5)** | **+4.66%** | ✅ 位置相对可控 |
| 量能状态 | 放量 | 价涨量增 |
| 系统评分 | 72/100 | |

### 量价变化                            ‹示例›
- 成交量较昨日变化：1.8倍
- 价格较昨日变化：+5.99%

---

## 📰 舆情情报                          ‹示例，已去重›
以下是 **聯電(2303)** 近3日的新闻搜索结果，请重点提取：
1. 🚨 风险警报  2. 🎯 利好催化  3. 📊 业绩预期
4. 🕒 时间规则（强制）：每条带 YYYY-MM-DD，超窗/时间未知一律忽略

​```
1. 聯電5月營收年增…法人看好晶圓代工回溫 - 經濟日報（2026-06-13）
   （同题 UDN 版本已被标题去重，仅保留一条）
​```

---

## ✅ 分析任务
请为 **聯電(2303)** 生成【决策仪表盘】，严格按照 JSON 格式输出。
…（重点回答：触发条件 / 入场风险回报 / 量能筹码 / 利空 / 止损观察点；
   latest_news·risk_alerts·positive_catalysts 不得超 3 日或时间未知；
   所有 JSON 键名不变、decision_type ∈ {buy,hold,sell}、可读文本用中文）
```

---

## 4. 一句話總結

報告概覽 = **一次 LLM 呼叫**（System 決策儀表盤規格 + User 當日數據）產出的 `dashboard` JSON。
台股會額外注入「三大法人 + 融資融券」這塊（§3.2 真實段落），其餘技術 / 趨勢 / 新聞由 pipeline 當日填入。

> 範例中標 `‹示例›` 的欄位為代表值；若要 100% 當日真實 Prompt，可跑 pipeline 對 tw2303 分析並於 DEBUG 日誌（`analyzer.py` 完整 Prompt 記錄）取得。
