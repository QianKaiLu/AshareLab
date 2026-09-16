"""市场日报配图：把分析数据画成图，供图片版报告嵌入。

四张图对应报告里最需要「一眼看出趋势」的四组数据：

    limitup.png   涨停家数折线        —— 情绪的日频读数
    newhigh.png   创 20 日新高双线    —— 游资（中证2000）与机构（沪深300）的态度
    amv.png       活跃市值 K 线       —— 资金闸门本体
    shindex.png   上证指数 K 线       —— 价格位置

**涨停家数折线只画有数据的日期**：20260820 之前的快照 `limit_up` 是空 list（抓取
失败），不是「当天没有涨停」。用 0 填补会画出一条从 0 起跳的假线，比不画更糟。

用法:
    python -m market.charts [YYYYMMDD]
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd

from datas.query_stock import query_index_bars
from draws.figs_factory.simple_figs import candle_fig, line_fig, save_fig
from market.amv import load_amv
from market.fetch import load_history
from tools.log import get_analyze_logger

logger = get_analyze_logger()

REPO = Path(__file__).resolve().parent.parent
CHART_ROOT = REPO / "market_reports" / "charts"

KLINE_DAYS = 60          # K 线回看天数
CHART_W = 600            # 出图宽度（CSS px），与报告内容区同量级


def _norm_date(target: str) -> str:
    t = str(target).strip()
    return f"{t[:4]}-{t[4:6]}-{t[6:8]}" if "-" not in t else t


def _limitup_df(target: str) -> pd.DataFrame:
    """涨停家数：只取 limit_up 非空的快照。"""
    hist = load_history()
    rows = []
    for d in sorted(hist):
        if d > target.replace("-", ""):
            break
        zt = hist[d].get("limit_up") or []
        if not zt:
            continue                        # 空 list 是抓取失败，不是 0 家涨停
        rows.append({"date": pd.Timestamp(_norm_date(d)), "涨停家数": len(zt)})
    return pd.DataFrame(rows)


def _newhigh_df(target: str) -> pd.DataFrame:
    """创 20 日新高占比：沪深300（机构）vs 中证2000（游资）。"""
    hist = load_history()
    rows = []
    for d in sorted(hist):
        if d > target.replace("-", ""):
            break
        nh = hist[d].get("newhigh") or {}
        if nh.get("hs300_pct") is None:
            continue
        rows.append({"date": pd.Timestamp(_norm_date(d)),
                     "沪深300": nh.get("hs300_pct"),
                     "中证2000": nh.get("csi2000_pct")})
    return pd.DataFrame(rows)


def draw_daily_charts(target: str, out_dir: Optional[Path] = None) -> dict[str, Path]:
    """画齐四张图，返回 {名字: 绝对路径}。数据不足的图会被跳过。"""
    day = _norm_date(target)
    out = out_dir or (CHART_ROOT / day)
    out.mkdir(parents=True, exist_ok=True)
    made: dict[str, Path] = {}

    # 涨停家数
    zt = _limitup_df(target)
    if len(zt) >= 2:
        fig = line_fig(zt, [("涨停家数", "涨停家数")],
                       title=f"涨停家数（近 {len(zt)} 个交易日）", height=300)
        made["limitup"] = save_fig(fig, out / "limitup.png", CHART_W, 300)
    else:
        logger.warning(f"涨停家数数据仅 {len(zt)} 点，跳过该图")

    # 创 20 日新高
    nh = _newhigh_df(target)
    if len(nh) >= 2:
        fig = line_fig(nh, [("沪深300", "沪深300（机构）"),
                            ("中证2000", "中证2000（游资）")],
                       title=f"创 20 日新高占比（近 {len(nh)} 个交易日，%）", height=300,
                       y_label="%")
        made["newhigh"] = save_fig(fig, out / "newhigh.png", CHART_W, 300)
    else:
        logger.warning(f"创新高数据仅 {len(nh)} 点，跳过该图")

    # 活跃市值 K 线
    amv = load_amv()
    if not amv.empty:
        sub = amv[amv["date"] <= pd.Timestamp(day)].tail(KLINE_DAYS).reset_index(drop=True)
        if len(sub) >= 5:
            fig = candle_fig(sub, title=f"活跃市值 0AMV（近 {len(sub)} 个交易日）",
                             height=380, ma_lines=(20,))
            made["amv"] = save_fig(fig, out / "amv.png", CHART_W, 380)

    # 上证指数 K 线
    idx = query_index_bars("sh000001", to_date=day)
    if not idx.empty:
        sub = idx.tail(KLINE_DAYS).reset_index(drop=True)
        fig = candle_fig(sub, title=f"上证指数（近 {len(sub)} 个交易日）",
                         height=380, ma_lines=(20, 60))
        made["shindex"] = save_fig(fig, out / "shindex.png", CHART_W, 380)

    for name, p in made.items():
        assert p.is_file() and p.stat().st_size > 0, f"{name} 图未落盘: {p}"
        logger.info(f"配图 {name}: {p}（{p.stat().st_size // 1024} KB）")
    return made


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else pd.Timestamp.today().strftime("%Y%m%d")
    print(draw_daily_charts(arg))
