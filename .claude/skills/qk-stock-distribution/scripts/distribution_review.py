#!/usr/bin/env python
"""单股出货复核：输出顶部区逐根 K 线量价明细，供 AI 综合判读。

量化探测器（S1~S5）只报「规则能框死的形态」，复合出货、温和放量深实体、
早期绿肥红瘦雏形这类边界形态故意不硬编码——本脚本把顶部区每一根 K 线的
量、实体、位置、白黄线关系摆出来，由 AI 对照 references/distribution_rules.md
做最终判断（文稿作者也明说「我的文章也可能片面」）。

只做客观测量，不下整体结论。

用法:
    python distribution_review.py <股票名或代码> [日期]
    python distribution_review.py 600016 20250815
    python distribution_review.py 光线传媒 --json
"""
import argparse
import json
import sys
from typing import Optional

import pandas as pd

sys.path.insert(0, "/Users/qianqian/stock/AshareLab")

from datas.query_stock import (  # noqa: E402
    get_stock_code_by_name,
    get_stock_info_by_code,
    query_bars_by_days,
)
from hunter.distribution_signals import (  # noqa: E402
    cap_tier,
    float_cap_yi,
    prepare_distribution_df,
    scan_signals,
    summarize,
)
from tools.stock_tools import latest_trade_day, to_std_code  # noqa: E402

BARS = 300
DETAIL_DAYS = 40  # 顶部区明细表默认行数上限


def resolve(name_or_code: str) -> tuple[Optional[str], str]:
    try:
        code = to_std_code(name_or_code)
        info = get_stock_info_by_code(code)
        if not info.empty:
            return code, "按代码匹配"
    except Exception:
        pass
    code = get_stock_code_by_name(name_or_code)
    if code:
        return code, f"按名称模糊匹配到 {code}"
    return None, f"无法解析「{name_or_code}」：股票池中查不到该名称或代码"


def review(name_or_code: str, date: Optional[str]) -> dict:
    code, resolve_note = resolve(name_or_code)
    if code is None:
        return {"error": resolve_note}

    to_date = date or latest_trade_day().strftime("%Y%m%d")
    df = query_bars_by_days(code, days=BARS, to_date=to_date)
    if df.empty:
        return {"error": f"{code} 在 {to_date} 之前无行情数据"}
    if len(df) < 120:
        return {"error": f"{code} 仅 {len(df)} 根 K 线，不足以评估（需 ≥120）"}

    info = get_stock_info_by_code(code)
    name = info["name"].values[0] if not info.empty else ""
    d = prepare_distribution_df(df, code=code, name=name)
    n = len(d)
    last = d.iloc[-1]

    signals = scan_signals(df, code=code, name=name)  # 默认 lookback=60
    summary = summarize(signals, df)
    cap = float_cap_yi(df)

    out: dict = {
        "标的": {
            "code": code, "name": name, "解析": resolve_note,
            "行业": info["idn_name"].values[0] if "idn_name" in info.columns and not info.empty else "",
            "评估日": str(last["date"])[:10],
            "流通市值_亿": cap, "盘子分档": cap_tier(cap),
            "说明": "文稿：小盘单顶、中盘双头、大盘综合——盘子越大出货方式越复合",
        }
    }

    # ---------------- 位置：当前价相对 60 日高点
    high60 = float(d["high"].iloc[-60:].max())
    h60_idx = d["high"].iloc[-60:].idxmax()
    out["位置"] = {
        "现价": round(float(last["close"]), 2),
        "60日最高价": round(high60, 2),
        "60日高点日": str(d.at[h60_idx, "date"])[:10],
        "现价距60日高点": f"{(float(last['close']) / high60 - 1) * 100:+.1f}%",
        "高点日距今_交易日": int(n - 1 - h60_idx),
        "白线": round(float(last["z_white"]), 2),
        "黄线": round(float(last["z_yellow"]), 2),
        "现价vs白黄线": ("白线上方" if last["close"] >= last["z_white"]
                        else ("白黄之间" if last["close"] >= last["z_yellow"]
                              else "黄线下方")),
    }

    # ---------------- 量化信号
    if summary is None:
        out["量化信号"] = {"命中": False, "说明": "近 60 个交易日内 S1~S5 均无命中"}
    else:
        out["量化信号"] = {
            "命中": True,
            "结论": summary["verdict"],
            "分层": ("失效(换庄)" if summary["invalidated"] else summary["tier"]),
            "最新信号距今_交易日": summary["newest_age"],
            "形态": summary["kinds"],
            "复合(高危窗内>=2种)": summary["composite"],
            "信号列表": [
                {"date": s.date, "kind": s.kind, "grade": s.grade,
                 "age": s.age, **s.metrics}
                for s in sorted(summary["signals"], key=lambda x: x.age)
            ],
        }

    # ---------------- 顶部区逐根明细（供 AI 判读的核心数据）
    # 起点：60 日高点日与最早信号日孰早，再往前留 3 根背景
    start_idx = h60_idx
    if summary is not None and summary["signals"]:
        sig_dates = [s.date for s in summary["signals"]]
        sig_idx = d.index[d["date"].astype(str).str[:10].isin(sig_dates)]
        if len(sig_idx):
            start_idx = min(start_idx, int(sig_idx.min()))
    start_idx = max(60, start_idx - 3)
    if n - start_idx > DETAIL_DAYS:
        start_idx = n - DETAIL_DAYS

    rows = []
    for i in range(start_idx, n):
        r = d.iloc[i]
        vol_ratio = (float(r["volume"] / r["vol_ma20_prev"])
                     if pd.notna(r["vol_ma20_prev"]) and r["vol_ma20_prev"] else None)
        flags = []
        if pd.notna(r["vol60max_prev"]) and r["volume"] >= r["vol60max_prev"] * 0.95:
            flags.append("天量")
        if vol_ratio is not None and vol_ratio <= 0.6:
            flags.append("缩量")
        if r["is_down"] and abs(float(r["body_norm"])) >= 0.6:
            flags.append("巨阴")
        if r["close"] < r["z_yellow"]:
            flags.append("破黄线")
        elif r["close"] < r["z_white"]:
            flags.append("破白线")
        if r["high"] >= high60 * 0.99:
            flags.append("触顶")
        rows.append({
            "日期": str(r["date"])[:10],
            "开": round(float(r["open"]), 2),
            "收": round(float(r["close"]), 2),
            "高": round(float(r["high"]), 2),
            "低": round(float(r["low"]), 2),
            "涨跌%": round(float(r["change_pct"]), 2) if pd.notna(r.get("change_pct")) else None,
            "实体%": round(float(r["body_pct"]), 2),
            "归一实体": round(float(r["body_norm"]), 2),
            "量/均20": round(vol_ratio, 2) if vol_ratio is not None else None,
            "阴阳": "阴" if r["is_down"] else "阳",
            "标记": ",".join(flags),
        })
    out["顶部区明细"] = {
        "列说明": {
            "归一实体": "实体涨跌幅/板块涨跌停幅度。-1.0=满幅跌停实体；假阴真阳为负（文稿纪律）",
            "量/均20": "当日量 / 前 20 日均量（不含当日）",
        },
        "行数": len(rows),
        "明细": rows,
    }

    # ---------------- 换庄豁免检查（信号日之后有更大量资金接货则旧信号失效）
    if summary is not None and summary["invalidated"]:
        out["换庄豁免"] = {
            "触发": True,
            "说明": "信号日之后出现「收盘 > 信号日高点×1.02 且量 > 信号日量」的 K 线，"
                    "说明有新资金接走筹码（中铁 2014 案例），旧出货信号失效",
        }

    return out


def render(r: dict) -> str:
    if "error" in r:
        return f"❌ {r['error']}"
    lines = []
    s = r["标的"]
    lines.append(f"# {s['name']}({s['code']})  {s.get('行业', '')}")
    lines.append(f"评估日 {s['评估日']}（{s['解析']}）  "
                 f"流通市值 {s['流通市值_亿']} 亿 / {s['盘子分档']}")

    lines.append("\n## 位置")
    for k, v in r["位置"].items():
        lines.append(f"  {k}: {v}")

    lines.append("\n## 量化信号（S1~S5 规则命中）")
    q = r["量化信号"]
    if not q["命中"]:
        lines.append(f"  无命中。{q['说明']}")
        lines.append("  注意：无命中 ≠ 无出货——复合式/温和式出货需看下方明细表人工判读")
    else:
        lines.append(f"  结论: {q['结论']}  分层: {q['分层']}  "
                     f"最新信号 {q['最新信号距今_交易日']} 个交易日前  "
                     f"形态: {'/'.join(q['形态'])}"
                     + ("  [复合]" if q["复合(高危窗内>=2种)"] else ""))
        for sig in q["信号列表"]:
            metrics = {k: v for k, v in sig.items()
                       if k not in ("date", "kind", "grade", "age")}
            mstr = " ".join(f"{k}={v}" for k, v in metrics.items())
            lines.append(f"    {sig['date']} {sig['kind']}[{sig['grade']}] "
                         f"age={sig['age']}  {mstr}")

    if "换庄豁免" in r:
        lines.append(f"\n## 换庄豁免\n  {r['换庄豁免']['说明']}")

    t = r["顶部区明细"]
    lines.append(f"\n## 顶部区逐根明细（{t['行数']} 行）")
    for k, v in t["列说明"].items():
        lines.append(f"  {k}: {v}")
    lines.append(f"  {'日期':<12}{'开':>8}{'收':>8}{'高':>8}{'低':>8}"
                 f"{'涨跌%':>7}{'实体%':>7}{'归一':>6}{'量/均':>6}  {'阴阳':<2} 标记")
    for b in t["明细"]:
        lines.append(
            f"  {b['日期']:<12}{b['开']:>8}{b['收']:>8}{b['高']:>8}{b['低']:>8}"
            f"{str(b['涨跌%']):>7}{b['实体%']:>7}{b['归一实体']:>6}"
            f"{str(b['量/均20']):>6}  {b['阴阳']:<2} {b['标记']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="单股出货复核（量价明细供 AI 判读）")
    ap.add_argument("target", help="股票名或 6 位代码")
    ap.add_argument("date", nargs="?", default=None, help="评估日 YYYYMMDD，默认最近交易日")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    r = review(args.target, args.date)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        print(render(r))
    return 1 if "error" in r else 0


if __name__ == "__main__":
    sys.exit(main())
