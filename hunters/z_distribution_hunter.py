"""出货形态全市场扫描。

理论来源：《主力出货的 5 种典型方式》（探测器实现见 hunter/distribution_signals.py）。

与 B1 等买点 hunter 的分工：买点 hunter 回答「能不能进」，本 hunter 回答
「要不要回避」。输出按文稿语义分级（必走 / 至少走一半 / 稳一手）× 时效
（20 个交易日内 = 高危，60 日内 = 观察）。

用法：
    PYTHONPATH=. conda run --live-stream -n stock python -m hunters.z_distribution_hunter
"""
from typing import Optional

import pandas as pd

from hunter.distribution_signals import (
    AGE_HOT,
    cap_tier,
    float_cap_yi,
    scan_signals,
    summarize,
)
from hunter.hunt_machine import HuntMachine, HuntResult
from tools.log import get_analyze_logger

logger = get_analyze_logger()

# 扫描窗口：最近 60 个交易日内的信号，再按 age ≤20 / ≤60 分高危 / 观察
SCAN_LOOKBACK = 60
# 需要的历史长度：vol60/high60 窗口 + 前置约 250 根够 ST 幅度推断
MIN_BARS = 300


def hunt_distribution(df: pd.DataFrame, code: str) -> Optional[dict]:
    """HuntMachine 入口：命中近期出货形态则返回汇总 dict。"""
    if df is None or df.empty:
        return None

    signals = scan_signals(df, code=code, lookback=SCAN_LOOKBACK)
    summary = summarize(signals, df)
    if summary is None:
        return None
    # 信号日后有更大量资金把货接走（换庄），旧信号失效——中铁 2014 案例
    if summary["invalidated"]:
        return None

    cap = float_cap_yi(df)
    recent = sorted(summary["signals"], key=lambda s: s.age)[:4]
    return {
        "verdict": summary["verdict"],
        "tier": summary["tier"],
        "newest_age": summary["newest_age"],
        "kinds": ",".join(summary["kinds"]),
        "composite": summary["composite"],
        "cap_yi": cap,
        "cap_tier": cap_tier(cap),
        "signal_count": summary["signal_count"],
        "recent_signals": "; ".join(
            f"{s.date} {s.kind}[{s.grade}]" for s in recent),
    }


def main():
    def print_result(result: HuntResult):
        info = result.result_info
        logger.info(f"{result.format_info} | {info['tier']} {info['verdict']} "
                    f"age={info['newest_age']} kinds={info['kinds']} "
                    f"cap={info['cap_yi']}亿/{info['cap_tier']}")
        logger.info(f"    {info['recent_signals']}")

    hunter = HuntMachine(max_workers=20, on_result_found=print_result)
    results: list[HuntResult] = hunter.hunt(
        hunt_distribution, min_bars=MIN_BARS, hunt_pool=None, with_code=True)

    if not results:
        print("No distribution signals found.")
        return

    hot = [r for r in results if r.result_info["tier"] == "高危"]
    watch = [r for r in results if r.result_info["tier"] == "观察"]

    print(f"\n🚨 高危（{AGE_HOT} 个交易日内有信号）: {len(hot)} 只")
    for r in sorted(hot, key=lambda r: r.result_info["newest_age"]):
        info = r.result_info
        print(f"  {r.code} {r.name} [{info['verdict']}] "
              f"age={info['newest_age']} {info['kinds']} | {info['recent_signals']}")

    print(f"\n⚠️ 观察（20~60 个交易日前的信号）: {len(watch)} 只")
    for r in sorted(watch, key=lambda r: r.result_info["newest_age"]):
        info = r.result_info
        print(f"  {r.code} {r.name} [{info['verdict']}] "
              f"age={info['newest_age']} {info['kinds']}")

    print(f"\n高危代码列表：{' '.join(r.code for r in hot)}")


if __name__ == "__main__":
    main()
