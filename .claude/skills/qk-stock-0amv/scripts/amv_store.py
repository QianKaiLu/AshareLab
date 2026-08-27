#!/usr/bin/env python3
"""0AMV（指南针「活跃市值」）手工录入存储。

指南针平台特有指标，无公开数据接口，走势靠人工从客户端读出。
解析各种输入形态（表格 / 截图 / JSON / 口述）由调用方负责，本脚本只做
校验与落盘：查错、去重、排序、写 CSV。

默认只预览不落盘，加 --commit 才真正写入。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

FIELDS = ["date", "open", "high", "low", "close", "change_pct"]
PRICE_FIELDS = ["open", "high", "low", "close"]

# 涨跌幅自算值与录入值的容差（百分点）。指南针显示两位小数，留一点余量。
PCT_TOLERANCE = 0.06
# 相邻两日收盘的倍数上限，用来抓单位写错（亿 / 万亿混用）或多打一位数。
MAGNITUDE_RATIO = 3.0


def repo_root() -> Path:
    # scripts / qk-stock-0amv / skills / .claude / <repo>
    return Path(__file__).resolve().parents[4]


def default_csv() -> Path:
    return repo_root() / "manual_data" / "0AMV.csv"


def parse_date(raw: str) -> str:
    """把常见日期写法归一成 YYYY-MM-DD。"""
    s = str(raw).strip().replace("/", "-").replace(".", "-")
    for ch in ("年", "月"):
        s = s.replace(ch, "-")
    s = s.replace("日", "").strip().rstrip("-")

    for fmt in ("%Y-%m-%d", "%y-%m-%d", "%Y%m%d", "%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if fmt == "%m-%d":
            # 无年份：按今年补，若落在未来则算上一年
            today = date.today()
            dt = dt.replace(year=today.year)
            if dt.date() > today:
                dt = dt.replace(year=today.year - 1)
        return dt.strftime("%Y-%m-%d")
    raise ValueError(f"无法识别的日期: {raw!r}")


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        rows = []
        for r in csv.DictReader(f):
            if not r.get("date"):
                continue
            row = {"date": r["date"]}
            for k in PRICE_FIELDS:
                row[k] = float(r[k])
            pct = r.get("change_pct")
            row["change_pct"] = float(pct) if pct not in (None, "") else None
            rows.append(row)
    rows.sort(key=lambda r: r["date"])
    return rows


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in sorted(rows, key=lambda x: x["date"]):
            out = dict(r)
            if out.get("change_pct") is None:
                out["change_pct"] = ""
            w.writerow(out)
    tmp.replace(path)


def normalize(rec: dict) -> dict:
    """把一条原始 record 归一成标准字段，缺 OHLC 中某项则报错。"""
    out = {"date": parse_date(rec["date"])}
    for k in PRICE_FIELDS:
        if rec.get(k) in (None, ""):
            raise ValueError(f"{out['date']} 缺少字段 {k}")
        out[k] = round(float(rec[k]), 4)
    pct = rec.get("change_pct")
    out["change_pct"] = round(float(pct), 4) if pct not in (None, "") else None
    return out


def check_record(rec: dict, prev: dict | None) -> list[str]:
    """返回这条记录的问题清单。空列表 = 干净。"""
    problems: list[str] = []
    o, h, l, c = (rec[k] for k in PRICE_FIELDS)

    if h < l:
        problems.append(f"最高 {h} < 最低 {l}")
    if h < max(o, c) - 1e-9:
        problems.append(f"最高 {h} 低于开盘/收盘的较大者 {max(o, c)}")
    if l > min(o, c) + 1e-9:
        problems.append(f"最低 {l} 高于开盘/收盘的较小者 {min(o, c)}")
    if any(v <= 0 for v in (o, h, l, c)):
        problems.append("存在非正数价格")

    d = datetime.strptime(rec["date"], "%Y-%m-%d").date()
    if d.weekday() >= 5:
        problems.append(f"{rec['date']} 是周{'六日'[d.weekday() - 5]}，非交易日")
    if d > date.today():
        problems.append(f"{rec['date']} 是未来日期")

    if prev is not None:
        pc = prev["close"]
        gap = (d - datetime.strptime(prev["date"], "%Y-%m-%d").date()).days
        computed = (c - pc) / pc * 100
        if rec["change_pct"] is None:
            if gap <= 5:
                rec["change_pct"] = round(computed, 4)
        elif abs(rec["change_pct"] - computed) > PCT_TOLERANCE:
            problems.append(
                f"涨跌幅 {rec['change_pct']:+.2f}% 与前收 {pc} 推算的 "
                f"{computed:+.2f}% 不符（差 {abs(rec['change_pct'] - computed):.2f}pp）"
            )
        if pc > 0 and not (1 / MAGNITUDE_RATIO <= c / pc <= MAGNITUDE_RATIO):
            problems.append(
                f"收盘 {c} 与上一条 {pc} 相差 {c / pc:.1f} 倍，疑似单位或位数写错"
            )
    return problems


def cmd_add(args: argparse.Namespace) -> int:
    path = Path(args.file) if args.file else default_csv()

    raw = json.loads(sys.stdin.read() if args.json == "-" else args.json)
    if isinstance(raw, dict):
        raw = [raw]

    try:
        incoming = [normalize(r) for r in raw]
    except (ValueError, KeyError, TypeError) as e:
        print(f"✗ 输入有问题: {e}", file=sys.stderr)
        return 2

    incoming.sort(key=lambda r: r["date"])
    existing = load_rows(path)
    by_date = {r["date"]: r for r in existing}

    merged = dict(by_date)
    news, updates, problems = [], [], []

    for rec in incoming:
        prior = [r for d, r in sorted(merged.items()) if d < rec["date"]]
        probs = check_record(rec, prior[-1] if prior else None)
        if probs:
            problems.append((rec, probs))
        old = by_date.get(rec["date"])
        if old is None:
            news.append(rec)
        elif any(old[k] != rec[k] for k in PRICE_FIELDS):
            updates.append((old, rec))
        merged[rec["date"]] = rec

    print(f"存储: {path}")
    print(f"现有 {len(existing)} 条，本次输入 {len(incoming)} 条\n")

    if news:
        print(f"新增 {len(news)} 条:")
        for r in news:
            pct = f"{r['change_pct']:+.2f}%" if r["change_pct"] is not None else "  n/a"
            print(
                f"  {r['date']}  开{r['open']:>9.2f} 高{r['high']:>9.2f} "
                f"低{r['low']:>9.2f} 收{r['close']:>9.2f}  {pct}"
            )
    if updates:
        print(f"\n覆盖 {len(updates)} 条（该日期已存在）:")
        for old, new in updates:
            print(f"  {new['date']}")
            for k in PRICE_FIELDS:
                if old[k] != new[k]:
                    print(f"    {k:<6} {old[k]} → {new[k]}")
    if not news and not updates:
        print("无变化：输入与现有数据完全一致。")

    if problems:
        print(f"\n⚠ {len(problems)} 条存在疑点，请核对后再落盘:")
        for rec, probs in problems:
            print(f"  {rec['date']}")
            for p in probs:
                print(f"    - {p}")

    if not args.commit:
        print("\n[预览] 未写入。确认无误后加 --commit 落盘。")
        return 1 if problems else 0

    if problems and not args.force:
        print("\n✗ 存在疑点，已中止。确认数据无误可加 --force 强制写入。")
        return 2

    write_rows(path, list(merged.values()))
    print(f"\n✓ 已写入 {path}，当前共 {len(merged)} 条。")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    path = Path(args.file) if args.file else default_csv()
    rows = load_rows(path)
    if not rows:
        print(f"{path} 为空或不存在。")
        return 0

    tail = rows[-args.tail :] if args.tail else rows
    if args.json:
        print(json.dumps(tail, ensure_ascii=False, indent=2))
        return 0

    print(f"{path}  共 {len(rows)} 条  {rows[0]['date']} ~ {rows[-1]['date']}\n")
    print(f"{'日期':<12}{'开盘':>10}{'最高':>10}{'最低':>10}{'收盘':>10}{'涨跌':>9}")
    for r in tail:
        pct = f"{r['change_pct']:+.2f}%" if r["change_pct"] is not None else "n/a"
        print(
            f"{r['date']:<12}{r['open']:>10.2f}{r['high']:>10.2f}"
            f"{r['low']:>10.2f}{r['close']:>10.2f}{pct:>9}"
        )

    gaps = []
    for a, b in zip(rows, rows[1:]):
        da = datetime.strptime(a["date"], "%Y-%m-%d").date()
        db = datetime.strptime(b["date"], "%Y-%m-%d").date()
        missing = sum(
            1
            for i in range(1, (db - da).days)
            if (da + timedelta(days=i)).weekday() < 5
        )
        if missing:
            gaps.append((a["date"], b["date"], missing))
    if gaps:
        print(f"\n⚠ {len(gaps)} 处缺口（中间有工作日未录入）:")
        for a, b, n in gaps[-10:]:
            print(f"  {a} → {b}  缺 {n} 个工作日")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    path = Path(args.file) if args.file else default_csv()
    rows = load_rows(path)
    if not rows:
        print(f"{path} 为空或不存在。")
        return 0

    bad = 0
    for i, rec in enumerate(rows):
        probs = check_record(dict(rec), rows[i - 1] if i else None)
        if probs:
            bad += 1
            print(f"{rec['date']}")
            for p in probs:
                print(f"  - {p}")
    if bad:
        print(f"\n✗ {len(rows)} 条中 {bad} 条有疑点。")
        return 1
    print(f"✓ {len(rows)} 条全部通过校验。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="0AMV 活跃市值手工录入存储")
    ap.add_argument("--file", help=f"CSV 路径，默认 {default_csv()}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="录入（默认仅预览）")
    a.add_argument("--json", required=True, help='记录数组的 JSON，或 - 从 stdin 读')
    a.add_argument("--commit", action="store_true", help="真正写入")
    a.add_argument("--force", action="store_true", help="有疑点也写入")
    a.set_defaults(func=cmd_add)

    s = sub.add_parser("show", help="查看已存数据与缺口")
    s.add_argument("--tail", type=int, default=20, help="只看最后 N 条，0 = 全部")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_show)

    v = sub.add_parser("verify", help="全量重新校验")
    v.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
