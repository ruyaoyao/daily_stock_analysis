#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print the TWSE 上市 融資融券 Top N ranking (post-market), like the broker
"融資增加排行" view. Keyless (TWSE MI_MARGN), units = 張.

Usage:
    python scripts/tw_margin_ranking.py --top 30
    python scripts/tw_margin_ranking.py --top 20 --sort short_increase
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data_provider.twse_openapi import get_tw_margin_ranking

_TITLES = {
    "margin_increase": "融資增加",
    "margin_decrease": "融資減少",
    "short_increase": "融券增加",
}


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:g}"
    return f"{value:,}"


def main() -> int:
    parser = argparse.ArgumentParser(description="TWSE 上市融資融券 Top N 排行")
    parser.add_argument("--top", type=int, default=30, help="返回前 N 名（默认 30）")
    parser.add_argument(
        "--sort", default="margin_increase", choices=list(_TITLES),
        help="排序依据（默认 margin_increase）",
    )
    args = parser.parse_args()

    rows = get_tw_margin_ranking(args.top, sort_by=args.sort)
    if not rows:
        print("無資料：TWSE 融資融券來源暫不可用（可能盤後尚未結算或來源異常）。")
        return 1

    print(f"TWSE 上市 Top {len(rows)} {_TITLES[args.sort]}排行（單位：張）\n")
    header = (
        f"{'#':>3}  {'代號':<7}{'股票':<10}{'融資增減':>10}{'融資餘額':>11}"
        f"{'融券增減':>10}{'券資比%':>8}{'使用率%':>8}"
    )
    print(header)
    print("-" * len(header))
    for i, x in enumerate(rows, 1):
        print(
            f"{i:>3}  {x['stock_code']:<7}{(x.get('name') or '')[:9]:<10}"
            f"{_fmt(x.get('margin_change')):>10}{_fmt(x.get('margin_balance')):>11}"
            f"{_fmt(x.get('short_change')):>10}{_fmt(x.get('short_margin_ratio')):>8}"
            f"{_fmt(x.get('margin_usage_pct')):>8}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
