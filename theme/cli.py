#!/usr/bin/env python
"""主题/主线工具命令行入口。

用法:
    conda run --live-stream -n stock python -m theme.cli snapshot [date]   # 抓当日快照存档
    conda run --live-stream -n stock python -m theme.cli report [date]    # 分析报告
    conda run --live-stream -n stock python -m theme.cli history          # 已有快照列表
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from theme import analyze, fetch

DEFAULT_DATE = ""  # 由各命令解释为「今天」或「最新快照」


def cmd_snapshot(args) -> int:
    day = args.date or __import__("datetime").date.today().strftime("%Y%m%d")
    print(f"抓取 {day} 快照…")
    snap = fetch.fetch_snapshot(day)
    path = fetch.save_snapshot(snap)
    ok = [k for k in ("market", "limit_up", "broken", "industry_ths", "concept_sina")
          if k in snap]
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


def cmd_history(args) -> int:
    hist = fetch.load_history()
    if not hist:
        print("history/ 为空。先跑 `python -m theme.cli snapshot`。")
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

    h = sub.add_parser("history", help="列出已有快照")
    h.set_defaults(func=cmd_history)

    args = ap.parse_args()
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
