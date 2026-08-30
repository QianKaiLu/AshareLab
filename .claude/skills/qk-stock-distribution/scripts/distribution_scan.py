"""批量出货识别：对一批股票跑 S1~S5 探测，输出分层结果。

输入方式（三选一）：
    python distribution_scan.py --codes 600016,300251,300528
    python distribution_scan.py --file b1_results/2026-08-28.md   # 从 B1 存档/任意文本提取 6 位代码
    python distribution_scan.py --pool hs300                      # hs300 / csi500 / all

输出：高危（20 个交易日内有信号）/ 观察（20~60 日）/ 无信号 三档，
每股一行带形态、严重度、量化细节。--json 输出机器可读。
"""
import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, "/Users/qianqian/stock/AshareLab")

from datas.query_stock import (  # noqa: E402
    get_stock_info_by_code,
    query_bars_by_days,
)
from hunter.distribution_signals import (  # noqa: E402
    cap_tier,
    float_cap_yi,
    scan_signals,
    summarize,
)

BARS = 300


def codes_from_text(text: str) -> list[str]:
    """从任意文本提取 6 位股票代码（去重保序）。"""
    seen: dict[str, None] = {}
    for m in re.finditer(r"(?<![\d.])([0368]\d{5})(?![\d.])", text):
        seen[m.group(1)] = None
    return list(seen)


def scan_one(code: str, to_date: str | None) -> dict:
    df = query_bars_by_days(code, days=BARS, to_date=to_date)
    if df.empty or len(df) < 120:
        return {"code": code, "error": "数据不足"}
    info = get_stock_info_by_code(code)
    name = info["name"].values[0] if not info.empty else ""
    signals = scan_signals(df, code=code, name=name)
    summary = summarize(signals, df)
    if summary is None:
        return {"code": code, "name": name, "status": "无信号"}
    cap = float_cap_yi(df)
    return {
        "code": code,
        "name": name,
        "status": "失效(换庄)" if summary["invalidated"] else summary["tier"],
        "verdict": summary["verdict"],
        "newest_age": summary["newest_age"],
        "kinds": summary["kinds"],
        "composite": summary["composite"],
        "cap_yi": cap,
        "cap_tier": cap_tier(cap),
        "signals": [
            {"date": s.date, "kind": s.kind, "grade": s.grade,
             "age": s.age, **s.metrics}
            for s in sorted(summary["signals"], key=lambda x: x.age)[:6]
        ],
    }


def fmt_row(r: dict) -> str:
    sig = "; ".join(f"{s['date']} {s['kind']}[{s['grade']}]"
                    for s in r["signals"][:3])
    comp = " 综合" if r["composite"] else ""
    return (f"{r['code']} {r['name']:<6} [{r['verdict']}{comp}] "
            f"age={r['newest_age']:>2} {'/'.join(r['kinds']):<12} "
            f"{r['cap_tier']} {r['cap_yi']}亿 | {sig}")


def main():
    ap = argparse.ArgumentParser(description="批量出货形态识别")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--codes", help="逗号分隔的 6 位代码")
    src.add_argument("--file", help="从文件（如 b1_results/*.md）提取代码")
    src.add_argument("--pool", choices=["hs300", "csi500", "all"], help="指数池")
    ap.add_argument("--to-date", help="评估日 YYYYMMDD，默认最新")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    if args.codes:
        codes = codes_from_text(args.codes)
    elif args.file:
        codes = codes_from_text(Path(args.file).read_text(encoding="utf-8"))
    else:
        if args.pool == "hs300":
            from datas.stock_index_list import hs300_code_list
            codes = hs300_code_list().tolist()
        elif args.pool == "csi500":
            from datas.stock_index_list import csi500_code_list
            codes = csi500_code_list().tolist()
        else:
            from datas.query_stock import query_all_stock_code_list
            codes = query_all_stock_code_list().tolist()

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(scan_one, c, args.to_date): c for c in codes}
        for f in as_completed(futs):
            results.append(f.result())

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return

    order = {"高危": 0, "观察": 1, "失效(换庄)": 2, "无信号": 3, None: 4}
    results.sort(key=lambda r: (order.get(r.get("status"), 4),
                                r.get("newest_age", 999)))
    groups: dict[str, list[dict]] = {}
    for r in results:
        groups.setdefault(r.get("status") or "error", []).append(r)

    print(f"共 {len(results)} 只\n")
    for status in ("高危", "观察", "失效(换庄)"):
        rows = groups.get(status, [])
        if not rows:
            continue
        print(f"== {status}（{len(rows)} 只）==")
        for r in rows:
            print("  " + fmt_row(r))
        print("  代码列表：" + " ".join(r["code"] for r in rows))
        print()
    none_rows = groups.get("无信号", [])
    print(f"== 无信号（{len(none_rows)} 只）==")
    if none_rows:
        print("  " + " ".join(f"{r['code']} {r['name']}" for r in none_rows))


if __name__ == "__main__":
    main()
