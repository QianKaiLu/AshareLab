"""市场日报配图：把分析数据画成图，供图片版报告嵌入。

六张图，对应报告里最需要「一眼看出趋势」的几组数据：

    limitup.png          涨停家数折线     —— 情绪的日频读数
    newhigh_hs300.png    沪深300 创新高   —— 机构态度
    newhigh_csi2000.png  中证2000 创新高  —— 游资态度
    amv.png              活跃市值 K 线    —— 资金闸门本体
    shindex.png          上证指数 K 线    —— 价格位置
    min30.png            上证 30 分钟 K 线 + MACD —— 分钟级结构与背离

几个不显然但重要的约定：

- **涨停家数只画有数据的日期**：20260820 之前的快照 `limit_up` 是空 list（抓取失败），
  不是「当天没有涨停」。用 0 填补会画出一条从 0 起跳的假线，比不画更糟。
- **创新高拆成两张**，各配一色（机构=琥珀、游资=蓝）。放一张图上的问题：两者量级
  差得多（沪深300 常年 2~15%、中证2000 可到 40%），共用一个纵轴会把沪深300 压成
  贴着底边的一条线。对比放在正文里说，不必靠同一张图叠出来。
- **K 线多取一段做指标预热**（`IND_WARMUP`），算完只画展示段。不这样做的话，
  展示 60 根画 MA60 只有 1 个有效值、线根本画不出来。

用法:
    python -m market.charts [YYYYMMDD]
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd

from datas.query_stock import query_index_bars, query_index_min_bars
from draws.figs_factory.simple_figs import (
    DEFAULT_THEME as CHART_THEME,
    candle_fig,
    candle_macd_fig,
    line_fig,
    save_fig,
)
from draws.kline_theme import ThemeRegistry
from indicators.macd import add_macd_to_dataframe
from market.amv import load_amv
from market.fetch import load_history
from tools.log import get_analyze_logger

logger = get_analyze_logger()

REPO = Path(__file__).resolve().parent.parent
CHART_ROOT = REPO / "market_reports" / "charts"

KLINE_DAYS = 60          # 日线 K 线**展示**天数
MIN30_BARS = 90          # 30 分钟**展示**根数（约 11 个交易日，够看清背离的两个低点）
# 指标预热：多取一段用于算均线/MACD，算完只画展示段。
# 不这样做的话，展示 60 根画 MA60 只有 1 个有效值、线画不出来；MACD 则要 35 根才收敛，
# 展示段开头一大截是空的。取 120 是因为要覆盖 MA60（60）+ MACD 收敛（~35）还有余量。
IND_WARMUP = 120
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

    # 创 20 日新高 —— **拆成两张**。
    # 放一张图上的问题：两者量级差得多（沪深300 常年 2~15%，中证2000 可到 40%），
    # 共用一个纵轴会把沪深300 压成贴着底边的一条线；而各自独立刻度后，
    # 「这条线现在处于什么水平」对每条线都看得清。
    # 两者的**对比**放在文字里说（谁在动、差值多少），不必靠同一张图叠出来。
    nh = _newhigh_df(target)
    if len(nh) >= 2:
        # 两张图各给一色：机构=琥珀、游资=蓝。凑成一对时颜色有区分，
        # 读者扫一眼就能认出「刚才那张是哪个口径」——不必读标题。
        theme = ThemeRegistry.get(name=CHART_THEME)
        for key, col, label, color in (
                ("newhigh_hs300", "沪深300", "沪深300（机构）", theme.line_color_0),
                ("newhigh_csi2000", "中证2000", "中证2000（游资）", theme.line_color_1)):
            if col not in nh.columns:
                continue
            fig = line_fig(nh[["date", col]], [(col, label)],
                           title=f"{label} 创 20 日新高占比（近 {len(nh)} 个交易日）",
                           height=280, y_label="%",
                           annotate_suffix="%", annotate_digits=1,
                           palette=[color])
            made[key] = save_fig(fig, out / f"{key}.png", CHART_W, 280)
    else:
        logger.warning(f"创新高数据仅 {len(nh)} 点，跳过该图")

    # 活跃市值 K 线（多取预热段，均线从第一根就画得出来）
    amv = load_amv()
    if not amv.empty:
        sub = amv[amv["date"] <= pd.Timestamp(day)].tail(
            KLINE_DAYS + IND_WARMUP).reset_index(drop=True)
        if len(sub) >= KLINE_DAYS:
            fig = candle_fig(sub, title=f"活跃市值 0AMV（近 {KLINE_DAYS} 个交易日）",
                             height=380, ma_lines=(20,), display_bars=KLINE_DAYS)
            made["amv"] = save_fig(fig, out / "amv.png", CHART_W, 380)

    # 上证指数 K 线（同上；MA60 需要至少 60 根预热才画得完整）
    idx = query_index_bars("sh000001", to_date=day)
    if not idx.empty:
        sub = idx.tail(KLINE_DAYS + IND_WARMUP).reset_index(drop=True)
        if len(sub) >= KLINE_DAYS:
            fig = candle_fig(sub, title=f"上证指数（近 {KLINE_DAYS} 个交易日）",
                             height=380, ma_lines=(20, 60), display_bars=KLINE_DAYS)
            made["shindex"] = save_fig(fig, out / "shindex.png", CHART_W, 380)

    # 上证 30 分钟 K 线 + MACD —— 为分钟级结构那节配图。
    # 取 30 分钟（不是 60/120）是因为它是入库的基础粒度，也是报告里讲背离用的那个周期。
    min30 = query_index_min_bars("sh000001", period=30, to_dt=f"{day} 23:59",
                                 limit=MIN30_BARS + IND_WARMUP)
    if not min30.empty:
        # MACD 在**完整序列**上算（含预热段），画的时候只取尾部——否则展示段开头
        # 三十多根没有 DIF/DEA，图上一大块是空的
        add_macd_to_dataframe(min30, inplace=True)
        fig = candle_macd_fig(
            min30, title=f"上证 30 分钟（近 {MIN30_BARS} 根）", height=520,
            ma_lines=(20,), display_bars=MIN30_BARS)
        made["min30"] = save_fig(fig, out / "min30.png", CHART_W, 520)

    for name, p in made.items():
        assert p.is_file() and p.stat().st_size > 0, f"{name} 图未落盘: {p}"
        logger.info(f"配图 {name}: {p}（{p.stat().st_size // 1024} KB）")
    return made


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else pd.Timestamp.today().strftime("%Y%m%d")
    print(draw_daily_charts(arg))
