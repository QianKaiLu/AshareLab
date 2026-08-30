"""出货形态信号有效性回测：S1~S5 任一探测器 × 指数成分池。

用事件研究骨架 backtest/event_study.py，回答三个层次的问题：

1. 信号之后 5/10/20/40/60 日，前向收益 / 最深回撤 / 最大反弹长什么样？
2. 比「无条件基准」（同宇宙随机日）深多少、反弹少多少？
3. 比「市场匹配基准」（信号日同池中位走势）差多少——剥离大盘 beta 后，
   信号本身还有没有选股信息？

用法：
    PYTHONPATH=. conda run --live-stream -n stock python -m backtest.signal_study --detector s1
    PYTHONPATH=. conda run --live-stream -n stock python -m backtest.signal_study --detector s2 --pool csi500
    PYTHONPATH=. conda run --live-stream -n stock python -m backtest.signal_study --detector s3 --from 2019-01-01

信号日约定（关键）：S1/S2 在顶部附近触发，是「早信号」；S3/S4 是形态走完
才确认，是「晚信号」——信号日已经在跌了一段之后。所以解读时：
    S1/S2 的 dd（回撤）大 = 从顶躲掉了大段跌幅；
    S3/S4 的 dd 天然偏小（跌完才确认），重点看 up（还能不能弹）与 ret（继续跌不跌）。

S3/S4 会连续多日触发，本脚本按 kind 把相邻触发折叠成「一次发作」，只留最早
那根，避免重叠样本虚增。

已知局限：
- 宇宙用「当前」成分股名单，存在幸存者偏差。
- 事件之间不独立：崩盘日会同一批触发多个信号，样本点有聚类。
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

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
    _detect_s2,
    _detect_s3,
    _detect_s4,
    _detect_s5,
    prepare_distribution_df,
)
from backtest.event_study import (  # noqa: E402
    forward_metrics,
    join_market,
    market_baseline,
    summarize,
)

MIN_BARS = 120
DEFAULT_FROM = "2015-01-01"

DETECTORS = {"s1": _detect_s1, "s2": _detect_s2, "s3": _detect_s3,
             "s4": _detect_s4, "s5": _detect_s5}
EPISODE_GAP = 10  # 同 kind 相邻多少根 K 线内视为同一次发作，只留最早


def dedup_episodes(events: list, gap: int = EPISODE_GAP) -> list:
    """把同一 kind 连续/邻近触发的信号折叠成一次，保留最早（最早的才是最可操作的）。"""
    events = sorted(events, key=lambda e: e["i"])
    kept, last = [], {}
    for e in events:
        k = e["kind"]
        if k in last and e["i"] - last[k] < gap:
            continue
        last[k] = e["i"]
        kept.append(e)
    return kept


def load_one(code: str, detect, from_date: Optional[str]):
    """返回 (events, close, low, panel_frame)，无信号返回 None。"""
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
        hit = detect(d, i)
        if hit is None:
            continue
        kind, grade, metrics = hit
        events.append({
            "i": i, "code": code, "name": name,
            "date": str(dates.iloc[i])[:10],
            "kind": kind, "grade": grade,
        })
    if not events:
        return None

    events = dedup_episodes(events)
    panel = pd.DataFrame({"close": d["close"].to_numpy(dtype=float),
                          "low": d["low"].to_numpy(dtype=float)},
                         index=pd.DatetimeIndex(dates))
    return events, close, low, panel


def main():
    ap = argparse.ArgumentParser(description="出货形态信号有效性回测")
    ap.add_argument("--detector", required=True, choices=list(DETECTORS),
                    help="S1~S5 探测器")
    ap.add_argument("--pool", choices=["hs300", "csi500", "csi2000", "a500"],
                    default="hs300", help="股票池，默认 hs300")
    ap.add_argument("--from", dest="from_date", default=DEFAULT_FROM,
                    help="起始日 YYYY-MM-DD，默认 2015-01-01")
    ap.add_argument("--horizons", default="5,10,20,40,60",
                    help="前向窗口（交易日，逗号分隔），默认 5,10,20,40,60")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    horizons = tuple(int(x) for x in args.horizons.split(","))

    detect = DETECTORS[args.detector]
    pool_fn = {"hs300": hs300_code_list, "csi500": csi500_code_list,
               "csi2000": csi2000_code_list, "a500": csi_a500_code_list}[args.pool]
    codes = pool_fn().tolist()
    print(f"探测器 {args.detector} | 宇宙 {len(codes)} 只（当前 {args.pool}）"
          f" | 起始 {args.from_date}")

    events, panels = [], {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(load_one, c, detect, args.from_date): c for c in codes}
        for f in as_completed(futs):
            out = f.result()
            if out is None:
                continue
            ev, close, low, panel = out
            code = ev[0]["code"]
            panels[code] = panel
            for e in ev:
                e.update(forward_metrics(close, low, e["i"], horizons))
            events.extend(ev)

    events_df = pd.DataFrame(events)
    print(f"事件 {len(events_df)} 条（去重后），覆盖 {events_df['code'].nunique()} 只股票\n")

    # _detect_s1 会返回 S1 与 S1变式 两种 kind，必须分开报告——
    # 两者信号质量差距悬殊（回测已证实），混在一起会被变式淹没
    for kind, sub in events_df.groupby("kind", sort=False):
        print(f"===== {kind}（{len(sub)} 条）=====")
        _report(sub, panels, horizons)
        print()


def _report(events: pd.DataFrame, panels: dict, horizons):
    df = summarize(events, horizons).set_index("horizon")
    print("--- 前向走势（从信号收盘价起算；dd 最深回撤 / up 最大反弹 / ret 窗口末收益）---")
    print(df[["n", "mean_ret", "median_ret", "mean_dd", "median_dd",
              "mean_up", "median_up", "pct_dd_lt_-10", "pct_dd_lt_-20"]]
          .round(4).to_string())

    mkt = market_baseline(panels, events["date"].unique(), horizons)
    joined = join_market(events, mkt, horizons)

    rows = []
    for k in horizons:
        alpha_dd = joined[f"alpha_dd_{k}"].dropna()
        alpha_up = joined[f"alpha_up_{k}"].dropna()
        alpha_ret = joined[f"alpha_ret_{k}"].dropna()
        rows.append({
            "horizon": k,
            "alpha_dd": alpha_dd.mean(),
            "alpha_up": alpha_up.mean(),
            "alpha_ret": alpha_ret.mean(),
            "pct_deeper_than_mkt": float((alpha_dd < 0).mean()),
            "pct_bounce_less_than_mkt": float((alpha_up < 0).mean()),
        })
    ex = pd.DataFrame(rows).set_index("horizon")
    print("\n--- 相对市场基准（alpha = 事件值 - 市场同日中位值，负 = 跑输市场）---")
    print(ex.round(4).to_string())
    print(f"\n解读：alpha_dd 越负 = 跌得比市场深；alpha_up 越负 = 反弹不如市场（跌完起不来）；"
          f"alpha_ret 越负 = 窗口末仍跑输。卖出信号有效 = dd 深 + up 弱 + ret 负。")


if __name__ == "__main__":
    main()
