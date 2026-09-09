#!/usr/bin/env python
"""市场环境分析命令行入口。

用法:
    conda run --live-stream -n stock python -m market.cli snapshot [date]   # 抓当日快照存档
    conda run --live-stream -n stock python -m market.cli report [date]    # 分析报告
    conda run --live-stream -n stock python -m market.cli history          # 已有快照列表
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from market import analyze, fetch

DEFAULT_DATE = ""  # 由各命令解释为「今天」或「最新快照」


def cmd_snapshot(args) -> int:
    day = args.date or __import__("datetime").date.today().strftime("%Y%m%d")
    print(f"抓取 {day} 快照…")
    snap = fetch.fetch_snapshot(day)
    path = fetch.save_snapshot(snap)
    ok = [k for k in snap if k not in ("date", "errors") and not k.startswith("_")]
    print(f"✓ 已存 {path}")
    print(f"  模块完成：{'、'.join(ok)}")
    if snap["errors"]:
        print("  ⚠ 部分失败：")
        for e in snap["errors"]:
            print(f"    - {e}")
    return 0 if not snap["errors"] else 1


def cmd_report(args) -> int:
    a = analyze.analyze(args.date, days=args.days)
    text = analyze.render(a)
    print(text)
    if args.json:
        print(json.dumps(a, ensure_ascii=False, indent=1))
    return 0 if not a.get("error") else 1


def cmd_backfill(args) -> int:
    """回溯补抓历史快照。

    涨停池/赚钱效应/大小票分歧都支持历史日期，可一次补齐——状态机的环比判断
    与持续性统计都要多日数据，否则退潮/启动分支永远不触发。
    """
    import sqlite3

    from market.fetch import DB_PATH

    if not DB_PATH.exists():
        print(f"✗ 找不到行情库 {DB_PATH}，无法取交易日历")
        return 1
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "select distinct date from stock_bars_daily_qfq order by date desc limit ?",
            (args.days,),
        ).fetchall()
    finally:
        conn.close()
    days = [str(r[0]).replace("-", "") for r in rows][::-1]
    if not days:
        print("✗ 行情库无数据")
        return 1

    todo = [d for d in days if args.force or not fetch.history_path(d).exists()]
    print(f"交易日 {len(days)} 个（{days[0]} ~ {days[-1]}），待抓 {len(todo)} 个")
    if not todo:
        print("已全部存在，加 --force 可重抓。")
        return 0

    failed = []
    for i, d in enumerate(todo, 1):
        snap = fetch.fetch_snapshot(d)
        fetch.save_snapshot(snap)
        n = len(snap.get("limit_up") or [])
        me = snap.get("money_effect") or {}
        nh = snap.get("newhigh") or {}
        mark = "⚠" if snap["errors"] else "✓"
        print(f"  {mark} [{i}/{len(todo)}] {d}  涨停 {n:>3}  "
              f"晋级 {me.get('promote_rate', '-')}%  "
              f"大小票 {nh.get('lean', '-')}")
        if snap["errors"]:
            failed.append((d, snap["errors"]))

    if failed:
        print(f"\n⚠ {len(failed)} 天有失败项：")
        for d, errs in failed[:5]:
            print(f"  {d}: {errs[0]}")
    print(f"\n✓ 完成，history/ 现有 {len(fetch.load_history())} 天")
    return 0


def cmd_history(args) -> int:
    hist = fetch.load_history()
    if not hist:
        print("history/ 为空。先跑 `python -m market.cli snapshot`。")
        return 0
    for d in sorted(hist):
        snap = hist[d]
        m = snap.get("market", {})
        nzt = len(snap.get("limit_up", []))
        errs = f"  ⚠{len(snap['errors'])}个失败" if snap.get("errors") else ""
        extra = f"  涨停 {nzt}" if nzt else ""
        print(f"{d}{extra}{errs}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="主题/主线板块观察工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("snapshot", help="抓当日快照并存档")
    s.add_argument("date", nargs="?", help="YYYYMMDD，缺省今天")
    s.set_defaults(func=cmd_snapshot)

    r = sub.add_parser("report", help="分析报告（基于历史快照）")
    r.add_argument("date", nargs="?", help="YYYYMMDD，缺省最新快照")
    r.add_argument("--days", type=int, default=5, help="持续性窗口（默认 5 日）")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_report)

    b = sub.add_parser("backfill", help="回溯补抓历史快照（状态机环比数据）")
    b.add_argument("--days", type=int, default=30, help="回溯多少个交易日（默认 30）")
    b.add_argument("--force", action="store_true", help="已存在也重抓")
    b.set_defaults(func=cmd_backfill)

    h = sub.add_parser("history", help="列出已有快照")
    h.set_defaults(func=cmd_history)

    args = ap.parse_args()
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
