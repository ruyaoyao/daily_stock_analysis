# -*- coding: utf-8 -*-
"""诊断 Shioaji 台指期（TXF）夜盘行情是否可取（权限 + 时段 + 取数路径）。

用途：「盘前展望」依赖台指期夜盘，需 Shioaji 账号具期货行情权限。本脚本逐段
拆解失败模式（凭证 / 登录 / 期货合约 / 快照），并提示当下是否为夜盘时段。

跑法（需先在 .env 配好 SHIOAJI_API_KEY / SHIOAJI_SECRET_KEY）：
    python scripts/diagnose_shioaji_futures.py

注意：会消耗一次 Shioaji 每日登录额度；建议**夜盘时段（约 15:00–次日 05:00 台北）**
跑一次以确认能取到真实夜盘价，非夜盘时段取到的是最近收盘价（仍能验证权限）。
本脚本为诊断工具，可保留或自行删除。
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# 允许从仓库根目录导入 src / data_provider（直接 python scripts/xxx.py 时 sys.path 只含 scripts/）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _now_tpe():
    return datetime.now(ZoneInfo("Asia/Taipei"))


def _session_hint(now):
    t = now.hour + now.minute / 60
    if 8.75 <= t < 13.5:
        return "日盘（08:45–13:45）→ 取到日盘价"
    if 15.0 <= t or t < 5.0:
        return "夜盘（15:00–次日05:00）→ 可验证真实夜盘价"
    return "非交易时段 → 取到最近一次收盘价（仍可验证权限）"


def main() -> int:
    print(f"[0] 台北时间 {_now_tpe():%Y-%m-%d %H:%M}　{_session_hint(_now_tpe())}\n")

    # 1) 凭证
    from src.config import get_config
    cfg = get_config()
    api_key = (getattr(cfg, "shioaji_api_key", None) or "").strip()
    secret = (getattr(cfg, "shioaji_secret_key", None) or "").strip()
    sim = bool(getattr(cfg, "shioaji_simulation", False))
    print(f"[1] 凭证：API_KEY={'已设' if api_key else '缺'}　SECRET={'已设' if secret else '缺'}　simulation={sim}")
    if not (api_key and secret):
        print("    ✗ 未配置 SHIOAJI_API_KEY / SHIOAJI_SECRET_KEY → 盘前展望会走降级版（仅美股盘后 + ADR）。")
        return 1
    if sim:
        print("    ⚠ simulation=True：模拟环境期货行情通常受限/为样本，建议用正式环境验证权限。")

    # 2) 登录
    from data_provider.shioaji_tw_fetcher import ShioajiTwFetcher, _ShioajiSession
    sess = _ShioajiSession.instance()
    api = sess.get_api()
    if api is None:
        print("[2] 登录：✗ 失败（凭证错误 / 超出每日登录额度 / 未安装 shioaji）。看上方日志。")
        return 2
    print("[2] 登录：✓ 成功")

    # 3) 期货合约解析（关键：能不能看到 TXF 合约 = 是否有期货行情权限）
    contract = sess.resolve_futures_front_month("TXF")
    if contract is None:
        print("[3] 期货合约：✗ 取不到 TXF 近月合约")
        print("    多半是：账号无期货行情权限 / 未开期货户 / 合约档未下载。")
        print("    → 盘前展望会自动降级（仅美股盘后 + ADR），不影响主流程。")
        # 附加：列出可见的期货类别，帮助判断是否完全没有期货权限
        try:
            cats = [a for a in dir(api.Contracts.Futures) if not a.startswith("_")][:15]
            print(f"    （可见期货类别样本：{cats or '无'}）")
        except Exception as e:
            print(f"    （无法列出期货类别：{e}）")
        return 3
    print(f"[3] 期货合约：✓ {getattr(contract, 'code', '?')}　{getattr(contract, 'name', '')}"
          f"　交割日={getattr(contract, 'delivery_date', '?')}")

    # 4) 快照（实际取数路径，与盘前展望一致）
    f = ShioajiTwFetcher()
    quote = f.get_tx_night_quote()
    if not quote:
        print("[4] 快照：✗ 取不到（快照为空 / 无该合约的行情数据权限）。")
        return 4
    print("[4] 快照：✓ 取数成功")
    print(f"    台指期近月 {quote['code']}：价 {quote['price']:,.0f}"
          f"　涨跌 {quote.get('change_pct')}%　量 {quote.get('volume')}")
    print("\n✅ 结论：Shioaji 期货行情权限可用，盘前展望可取到台指期夜盘数据。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"✗ 诊断异常：{type(e).__name__}: {e}")
        sys.exit(9)
