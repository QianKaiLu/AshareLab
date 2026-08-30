"""S1 信号有效性回测：指数成分股池，S1（加速后天量巨阴）后是否大幅回撤。

用事件研究骨架 backtest/event_study.py，回答三个层次的问题：

1. S1 之后 5/10/20/40/60 日，前向收益与最深回撤长什么样？
2. 比「无条件基准」（同宇宙随机日的回撤分布）深多少？
3. 比「市场匹配基准」（信号日同池中位回撤）深多少——剥离大盘 beta 后，
   S1 本身还有没有选股信息？

用法：
    PYTHONPATH=. conda run --live-stream -n stock python -m backtest.s1_hs300 --pool hs300
    PYTHONPATH=. conda run --live-stream -n stock python -m backtest.s1_hs300 --pool csi500
    PYTHONPATH=. conda run --live-stream -n stock python -m backtest.s1_hs300 --pool hs300 --from 2019-01-01
    PYTHONPATH=. conda run --live-stream -n stock python -m backtest.s1_hs300 --variant   # S1 + S1变式 合并看

已知局限（结果解读时须知）：
- 宇宙用「当前」成分股名单，存在幸存者偏差——已退出的成分股的历史 S1 不计入。
- 事件之间不独立：崩盘日会同一批触发多个 S1，样本点有聚类，标准差会偏乐观。
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/qianqian/stock/AshareLab")

from datas.query_stock import get_stock_info_by_code, query_daily_bars  # noqa: E402
from datas.stock_index_list import (  # noqa: E402
    csi500_code_list,
    csi2000_code_list,
    csi_a500_code_list,
    hs300_code_list,
)
from hunter.distribution_signals import (  # noqa: E402
    _detect_s1,
    prepare_distribution_df,
)
from backtest.event_study import (  # noqa: E402
    DEFAULT_HORIZONS,
    forward_metrics,
    join_market,
    market_baseline,
    summarize,
)

MIN_BARS = 120
DEFAULT_FROM = "2015-01-01"


def load_one(code: str, from_date: Optional[str]):
    """返回 (events, close, low, dates, panel_frame)。

    events: 该股全部 S1/S1变式 事件，每项含 i + 事件字段；
    panel_frame: 以 date 为索引的 close/low，供市场基准用。
    """
    df = query_daily_bars(code, from_date=from_date)
    if df.empty or len(df) < MIN_BARS:
        return None

    info = get_stock_info_by_code(code)
    name = info["name"].values[0] if not info.empty else ""
    d = prepare_distribution_df(df, code=code, name=name)
    n = len(d)
    close = d["close"].to_numpy(dtype=float)
    low = d["low"].to_numpy(dtype=float)
    dates = d["date"]

    events = []
    for i in range(60, n):
        hit = _detect_s1(d, i)
        if hit is None:
            continue
        kind, grade, metrics = hit
        events.append({
            "i": i, "code": code, "name": name,
            "date": str(dates.iloc[i])[:10],
            "kind": kind, "grade": grade,
            "body_norm": metrics.get("body_norm"),
            "vol60_ratio": metrics.get("vol60_ratio"),
        })
    if not events:
        return None

    panel = pd.DataFrame({"close": d["close"].to_numpy(dtype=float),
                          "low": d["low"].to_numpy(dtype=float)},
                         index=pd.DatetimeIndex(dates))
    return events, close, low, panel


def main():
    ap = argparse.ArgumentParser(description="S1 信号有效性回测（指数成分池）")
    ap.add_argument("--pool", choices=["hs300", "csi500", "csi2000", "a500"],
                    default="hs300", help="股票池，默认 hs300")
    ap.add_argument("--from", dest="from_date", default=DEFAULT_FROM,
                    help="起始日 YYYY-MM-DD，默认 2015-01-01")
    ap.add_argument("--variant", action="store_true",
                    help="把 S1变式 也并入样本（默认只算标准 S1）")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    pool_fn = {"hs300": hs300_code_list, "csi500": csi500_code_list,
               "csi2000": csi2000_code_list, "a500": csi_a500_code_list}[args.pool]
    codes = pool_fn().tolist()
    print(f"宇宙 {len(codes)} 只（当前 {args.pool} 名单），起始 {args.from_date}")

    events, panels = [], {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(load_one, c, args.from_date): c for c in codes}
        for f in as_completed(futs):
            out = f.result()
            if out is None:
                continue
            ev, close, low, panel = out
            code = ev[0]["code"]
            panels[code] = panel
            for e in ev:
                e.update(forward_metrics(close, low, e["i"], DEFAULT_HORIZONS))
            events.extend(ev)

    events_df = pd.DataFrame(events)
    print(f"原始事件 {len(events_df)} 条，覆盖 {events_df['code'].nunique()} 只股票\n")

    # 按 kind 切分：标准 S1 为主样本，S1变式 单独看
    for tag, mask in [("S1", events_df["kind"] == "S1"),
                      ("S1变式", events_df["kind"] == "S1变式")]:
        sub = events_df[mask]
        if sub.empty:
            print(f"[{tag}] 无样本\n")
            continue
        print(f"===== {tag}（{len(sub)} 条事件）=====")
        _report(sub, panels, DEFAULT_HORIZONS)
        print()

    if args.variant:
        print("===== S1 + S1变式 合并（%d 条）=====" % len(events_df))
        _report(events_df, panels, DEFAULT_HORIZONS)


def _report(events: pd.DataFrame, panels: dict, horizons):
    """打印一组事件的收益/回撤分布 + 双基准对比。"""
    df = summarize(events, horizons).set_index("horizon")
    print("--- 前向走势（从信号收盘价起算）---")
    print(df[["n", "mean_ret", "median_ret", "mean_dd", "median_dd",
              "pct_dd_lt_-10", "pct_dd_lt_-20"]]
          .round(4).to_string())

    mkt = market_baseline(panels, events["date"].unique(), horizons)
    joined = join_market(events, mkt, horizons)

    rows = []
    for k in horizons:
        dd = joined[f"dd_{k}"].dropna()
        mdd = joined[f"mkt_dd_{k}"].dropna()
        alpha = joined[f"alpha_dd_{k}"].dropna()
        rows.append({
            "horizon": k,
            "mean_dd": dd.mean(),
            "mkt_mean_dd": mdd.mean(),
            "alpha_dd": alpha.mean(),
            "pct_beat_market": float((alpha < 0).mean()),
        })
    ex = pd.DataFrame(rows).set_index("horizon")
    print("\n--- 相对市场基准（alpha_dd = 事件回撤 - 市场同日中位回撤，负=跑输市场）---")
    print(ex.round(4).to_string())
    print(f"\n解读：alpha_dd 越负，说明 S1 后该股跌得比大盘更深、信号越有选股信息；"
          f"pct_beat_market 是「跑输市场」的占比（理想卖出信号应 >0.5）。")


if __name__ == "__main__":
    main()
