# 國際情勢／宏觀背景指標組合 — 演算法與來源規格（可攜版）

> 一個**最小、可攜、免 API key** 的「市場風險偏好（risk-on / risk-off）背景」指標組合,
> 用 4 個指標、走 yfinance（Yahoo Finance）即可組出,適合放進任何「大盤/市場每日復盤」場景。
> 本文件自帶參考實作,可直接複製到其他專案使用,**不依賴本專案內部類別**。
>
> 設計定位:**日級、粗粒度、設定基調用**——不是盤中訊號、不是進出場工具、不對個股逐檔注入。

---

## 1. 指標組合（4 個,各佔一條不重複的「軸」）

| 指標 | Yahoo 代碼 | 衡量的「軸」 | 解讀方向 |
|---|---|---|---|
| **SOX** 費城半導體指數 | `^SOX` | 半導體景氣（科技多頭/出口需求） | ↑＝科技 risk-on;對半導體權重高的市場（如台股）最關鍵 |
| **DXY** 美元指數 | `DX-Y.NYB` | 美元強弱 / 全球資金面 | ↑＝美元走強、資金回流美元、對新興市場與出口偏空 |
| **VIX** 波動率指數 | `^VIX` | 風險偏好溫度計 | ↑＝避險升溫（risk-off);低檔＝風險偏好高 |
| **US10Y** 美債10年期殖利率 | `^TNX` | 利率環境 | ↑＝利率走升、評價面壓力（成長股尤甚） |

**為什麼是這 4 個（而不是更多）**:每個指標對應一條**獨立的敘事軸**(半導體 / 美元 / 風險 / 利率)。
追加指標的唯一理由是「開出新軸」,不是「看起來更完整」。詳見 §5 的篩選實證。

---

## 2. 取數演算法

對每個指標,取對應交易日與其前一交易日的收盤價,算當日漲跌幅:

```
hist        = 日線（含收盤 Close）
price       = 對應交易日收盤
prev_close  = 前一交易日收盤（僅取到 1 列時 = 同一列 → 漲跌幅 0%）
change      = price - prev_close
change_pct  = change / prev_close * 100      # prev_close 為 0 時取 0
```

**日期對齊（`before_date`）**:亞股覆盤（tw/cn/hk/jp/kr）的隔夜美系背景,必須鎖定到
「覆盤交易日**之前**最後一個美股收盤交易日」（＝昨夜美股,見下方跨時區說明),而非依
工作執行的牆鐘時間抓「最新」一根。實作上 `_fetch_yf_ticker_data(before_date=覆盤日)`
取較長區間（`period='1mo'`）後,挑出 index 日期 `< before_date` 的最後一筆作為對應交易日,
其前一筆作為 `prev_close`。如此**不論工作何時執行**（準點 18:00、深夜美股已開盤後、事後
重跑/補跑),6/25 的台股覆盤都會對到 6/24 的費半,而不是當下最新值。`before_date=None`
（美股覆盤本身即當日美系,或一般行情查詢）則沿用「最近 2 日」取最新一根的原行為。

注意事項:
- `^TNX` 是**殖利率水位**（例如 4.53 代表 ~4.53%）,非價格;漲跌幅仍可比較方向,但語意是「殖利率變動」。
- `before_date=None` 時,收盤後若 2 日窗只回 1 列,`change_pct` 會是 0%（盤中/盤後正常顯示）——屬資料窗口特性,非錯誤。
- **跨時區**:美系指標（SOX/DXY/VIX/US10Y）在亞洲收盤後才交易;若用於亞洲市場,當日同步相關性≈0,**真正有意義的是「昨日美系 → 今日亞股」的隔夜領先關係**（見 §5）。這正是 `before_date` 對齊要鎖定「前一個美股交易日」的原因。

---

## 3. 風險偏好（risk-on / off）啟發式判讀

指標本身是「資料」,定調交給下游（人或 LLM）。若需要一個**輕量啟發式標籤**,可用 VIX 水位為主、其餘為輔:

| 條件 | 定調 |
|---|---|
| VIX < 15 且 SOX 收紅 | **risk-on**（風險偏好高、科技多頭） |
| VIX > 25 或 SOX 大跌(< −2%) | **risk-off**（避險升溫） |
| 15 ≤ VIX ≤ 25 | **neutral / 震盪**（看 DXY、US10Y 方向微調） |

輔助規則:
- DXY ↑ + US10Y ↑ 同向走升 → 資金面/評價面雙重壓力,偏 risk-off。
- 給 LLM 用時,**建議只丟原始數值 + 各指標代表的軸**,讓模型判讀,避免把啟發式標籤寫死造成誤判。

---

## 4. 設計原則（移植時請保留）

1. **僅市場/大盤層級,不對個股逐檔注入**:個股逐檔注入會 O(N) 放大成本,且易讓模型把個股漲跌牽強歸因到宏觀。
2. **完全 fail-safe**:單一指標抓取失敗→跳過該指標;全部失敗→不輸出此區塊;**都不可中斷主流程**。
3. **開關化**:用一個環境變數（如 `MARKET_INTL_CONTEXT_ENABLED`）控制,預設啟用、可關閉。
4. **精簡**:整組 4–6 個為宜;超過會稀釋敘事、增加 token、提高過擬合風險。
5. **可溯源**:優先用可程式化、可溯源、免 key 的結構化來源（yfinance）;**避免用第三方 AI 二手摘要站**（無 API/RSS、不可溯源、ToS 不明、會放大幻覺）。

---

## 5. 指標篩選的實證依據（2.1 年日報酬相關性研究）

521 個交易日（≈2.1 年）的日報酬相關性,用來決定「加什麼、不加什麼」:

**冗餘度（候選 vs 這 4 個,同日 |ρ|>0.7 視為冗餘）**
- **Nasdaq**：max|ρ|=**0.87**（vs SOX 0.87、VIX −0.78）→ 冗餘,**不加**。
- **SPX**：max|ρ|=**0.83**（且 Nasdaq↔SPX=0.97）→ 冗餘,**不加**。
- USD/TWD、上證、Gold、Oil：與這 4 個 |ρ| ≤ 0.35 → 各為**獨立新軸**。

**對台股的關聯（隔夜領先 corr(TAIEX_t, X_{t−1})）**
- **SOX 0.56（最強）**、VIX −0.41 → 扛起「每日 risk-on/off」訊號。
- DXY −0.12、US10Y 0.02 → 每日預測力弱,但屬**結構性慢變數軸**（匯率/利率水位）,保留作背景。
- Nasdaq 0.53、SPX 0.52 → 雖強,但已被 SOX 涵蓋（與 SOX 同軸）→ 加了重複。

**結論**:這 4 個是「精簡且不冗餘」的組合。要再擴 1 條軸時,**上證（中國需求/供應鏈,同日 ρ 0.18、非冗餘）最有理由**,其餘（Nasdaq/SPX/Gold/Oil）邊際價值不足。

**移植到其他市場時**:把「對 TAIEX」換成「對你的目標指數」重跑一次相關性 + 消融測試（含/不含候選各跑一次,看結論是否實質改變),用數據決定指標集,不要照搬。

---

## 6. 參考實作（純 stdlib + yfinance,可直接複製）

```python
# pip install yfinance
import yfinance as yf

# (Yahoo 代碼, 顯示名, 軸說明)
MACRO = [
    ("^SOX",     "SOX 費城半導體",  "半導體景氣"),
    ("DX-Y.NYB", "DXY 美元指數",    "美元/資金面"),
    ("^VIX",     "VIX 波動率",      "風險偏好"),
    ("^TNX",     "US10Y 美債殖利率", "利率環境"),
]

def fetch_one(symbol: str):
    """取最近 2 日,回 (price, change_pct);失敗回 None。"""
    try:
        hist = yf.Ticker(symbol).history(period="2d")
        if hist.empty:
            return None
        price = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
        pct = (price - prev) / prev * 100 if prev else 0.0
        return price, pct
    except Exception:
        return None   # fail-safe:單一指標失敗不影響其餘

def build_backdrop():
    """回一段可注入報告/prompt 的文字;全失敗回空字串。"""
    lines = []
    for symbol, name, axis in MACRO:
        r = fetch_one(symbol)
        if r is None:
            continue
        price, pct = r
        arrow = "↑" if pct > 0 else "↓" if pct < 0 else "-"
        lines.append(f"- {name}: {price:,.2f} ({arrow}{abs(pct):.2f}%)  // {axis}")
    if not lines:
        return ""
    note = "（SOX＝半導體景氣、DXY＝美元、VIX＝風險偏好、US10Y＝利率;僅作 risk-on/off 背景定調）"
    return "## 國際情勢（宏觀背景）\n" + "\n".join(lines) + "\n" + note

if __name__ == "__main__":
    print(build_backdrop() or "(no data)")
```

**不想依賴 yfinance 時**的等價來源:可改用 Yahoo `query1.finance.yahoo.com/v8/finance/chart/<symbol>` 的 JSON、Stooq CSV、或各自的官方/交易所端點;演算法（取近 2 日收盤算漲跌幅 + fail-safe）不變。

---

## 7. 一句話總結

> **SOX + DXY + VIX + US10Y**,各佔一條不重複的軸(半導體/美元/風險/利率),取近 2 日收盤算漲跌幅、
> 全程 fail-safe、僅大盤層級、可開關——這是一個經相關性實證篩選過的「最小可用」國際情勢背景組合。
