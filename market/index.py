"""宽基指数概览：价格位置 + 大小盘风格。

数据来自 `index_bars_daily`（由 `workflow/daily_update.py` 第 5 步维护），
查询走 `datas/query_stock.py`。

与 `market/amv.py` 的分工：活跃市值是**资金**视角（活筹进出，决定要不要参与），
指数是**价格**视角（大盘走到哪了、什么风格占优）。两者都在 L0 层回答「环境如何」，
但一个看钱、一个看价，缺一不可。

**关键约束同 amv：只能用 target 当日及之前的数据**，否则回看失真。

用法:
    python -m market.index            # 最新
    python -m market.index 20260821
"""
from __future__ import annotations

import sys

import pandas as pd

from datas.query_stock import query_index_bars

MA_WINDOW = 60

# 报告主行显示的指数；与 INDEX_POOL 对齐但只挑代表性的，避免一行塞 11 个
CORE = (("sh000001", "上证"), ("sz399001", "深证"), ("sz399006", "创业板"),
        ("sh000688", "科创50"), ("bj899050", "北证50"))
BROAD = (("sh000300", "沪深300"), ("sh000905", "中证500"), ("sh000852", "中证1000"),
         ("sz399303", "国证2000"), ("sh000985", "中证全指"), ("sh000016", "上证50"),
         ("sz399975", "证券公司"))

# 「券商 + 沪深300 + 创业板」三者同时上涨 → 聪明资金进场
# （来源：reference_articles/modoo/大富翁(4)）。券商是先行指标，单看它容易假信号，
# 三个一起动才算数。
RESONANCE = (("sz399975", "证券公司"), ("sh000300", "沪深300"), ("sz399006", "创业板"))

# 大小盘风格：中证1000 − 沪深300，正=小盘占优
STYLE_SMALL, STYLE_BIG = "sh000852", "sh000300"
STYLE_GAP = 0.5         # 差值超过此值（pp）才算某一边占优

CALIBER = "涨跌幅为当日，位置为距各自 60 日线；风格 = 中证1000 − 沪深300 当日之差"


def _norm_date(target: str) -> str:
    t = str(target).strip()
    return f"{t[:4]}-{t[4:6]}-{t[6:8]}" if "-" not in t else t


def _one(symbol: str, name: str, day: str, days: int, group: str) -> dict | None:
    """单只指数的当日/近 N 日表现与距 60 日线位置。数据不足返回 None。"""
    df = query_index_bars(symbol, to_date=day)
    if df.empty:
        return None
    df = df[df["date"] <= pd.Timestamp(day)]
    if len(df) < 2:
        return None

    close = df["close"]
    ma60 = close.rolling(MA_WINDOW).mean()
    last = float(close.iloc[-1])

    pct = df["change_pct"].iloc[-1]
    pct = float(pct) if pd.notna(pct) else (last / float(close.iloc[-2]) - 1) * 100

    base = float(close.iloc[-1 - days]) if len(close) > days else float(close.iloc[0])
    out = {
        "symbol": symbol,
        "名称": name,
        "组": group,
        "收盘": round(last, 2),
        "当日": round(pct, 2),
        "近N日": round((last / base - 1) * 100, 2),
        "距60线": None,
    }
    if pd.notna(ma60.iloc[-1]):
        out["距60线"] = round((last / float(ma60.iloc[-1]) - 1) * 100, 2)
    return out


def index_overview(target: str, days: int = 5) -> dict:
    """宽基指数概览。缺数据时返回 {"error": ...}。"""
    day = _norm_date(target)
    rows = []
    for label, group in (("主要", CORE), ("宽基", BROAD)):
        for symbol, name in group:
            r = _one(symbol, name, day, days, label)
            if r:
                rows.append(r)
    if not rows:
        return {"error": f"index_bars_daily 无 {day} 之前的数据"}

    by = {r["symbol"]: r for r in rows}
    style = None
    if STYLE_SMALL in by and STYLE_BIG in by and by[STYLE_SMALL]["当日"] is not None:
        gap = by[STYLE_SMALL]["当日"] - by[STYLE_BIG]["当日"]
        lean = ("小盘占优" if gap > STYLE_GAP
                else "大盘占优" if gap < -STYLE_GAP else "均衡")
        style = {"值": round(gap, 2), "解读": lean}

    trio = [(by[s]["当日"], n) for s, n in RESONANCE
            if s in by and by[s]["当日"] is not None]
    resonance = None
    if len(trio) == len(RESONANCE):
        resonance = {
            "共振": all(p > 0 for p, _ in trio),
            "明细": "　".join(f"{n} {p:+.2f}%" for p, n in trio),
        }

    ups = sum(1 for r in rows if r["当日"] > 0)
    if ups == len(rows):
        breadth = "普涨"
    elif ups == 0:
        breadth = "普跌"
    else:
        breadth = f"{ups} 涨 {len(rows) - ups} 跌"

    # 全都跌破 60 线本身就是最强的单一信号，值得单独提炼
    with_ma = [r for r in rows if r["距60线"] is not None]
    below = [r for r in with_ma if r["距60线"] < 0]
    if with_ma and len(below) == len(with_ma):
        ma_note = f"{len(with_ma)} 只全部在 60 日线下"
    elif with_ma and not below:
        ma_note = f"{len(with_ma)} 只全部在 60 日线上"
    elif with_ma:
        ma_note = f"{len(below)}/{len(with_ma)} 只在 60 日线下"
    else:
        ma_note = "60 日线不可用"

    return {
        "数据日期": day,
        "指数": rows,
        "概览": breadth,
        "60线概览": ma_note,
        "风格": style,
        "共振": resonance,
        "口径": CALIBER,
    }


def render_index(a: dict) -> str:
    """人读格式，供 __main__ 与排查使用。报告里的渲染在 analyze.render() 内。"""
    if a.get("error"):
        return f"❌ {a['error']}"
    lines = [f"# 宽基指数概览　{a['数据日期']}（{a['概览']}）", ""]
    for r in a["指数"]:
        bits = [f"{r['名称']} {r['收盘']:,.2f}（{r['当日']:+.2f}%）"]
        bits.append(f"近5日 {r['近N日']:+.2f}%")
        if r["距60线"] is not None:
            bits.append(f"距60线 {r['距60线']:+.2f}%")
        lines.append("　".join(bits))
    if a["风格"]:
        lines.append(f"\n风格：中证1000 − 沪深300 = {a['风格']['值']:+.2f}pp → {a['风格']['解读']}")
    if a.get("共振"):
        r = a["共振"]
        lines.append(f"券商+沪深300+创业板：{r['明细']}"
                     + ("　→ **共振，疑似聪明资金进场**" if r["共振"] else "　→ 未共振"))
    lines.append(f"\n> {a['口径']}")
    return "\n".join(lines)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else pd.Timestamp.today().strftime("%Y%m%d")
    print(render_index(index_overview(arg)))
