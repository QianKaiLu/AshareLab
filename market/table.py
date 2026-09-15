"""每日观察数据表：把快照与 0AMV 拼成一张连续的表。

对应交易系统里那张「每天维护的表格」（`reference_articles/modoo/每天大A重要数据表格`）：
   日期 / 活跃市值 / 涨停 / 中证2000-20日新高 / 沪深300-20日新高

**这是纯视图，不抓任何数据。** 五项来源都已存在：

    日期            market/history/*.json 的文件名
    活跃市值        manual_data/0AMV.csv（market/amv.py:load_amv）
    涨停家数        snapshot["limit_up"] 的长度
    创20日新高      snapshot["newhigh"]（market/fetch.py:fetch_newhigh_divergence）

三个必须小心的坑：

1. **涨停为 0 与「没有数据」是两回事**。20260730~20260819 那批快照的 `limit_up` 是空 list
   （抓取失败），不是「当天没有涨停」。表里必须留空，显示 0 会被读成真实读数。
2. **中证2000 的分母只有 699 而不是 2000**。`fetch_newhigh_divergence` 的分母是
   「成分名单 ∩ 库里有行情的股票」，而库里没有北交所 8xx 小票。所以 27 家不是绝对家数，
   口径行必须标出分母。
3. **0AMV 靠手工录入，可能滞后于快照**。最后几行会出现「有日期无 0AMV」，留空即可。

用法:
    python -m market.table [--days 30]
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

import sqlite3

from datas.create_database import DAILY_BAR_TABLE, DB_PATH
from market.amv import load_amv
from market.fetch import load_history

DAYS_DEFAULT = 30

CALIBER = ("涨停家数取当日涨停池长度；创20日新高为收盘价口径（非最高价），"
           "分母是「成分名单 ∩ 库里有行情的股票」，中证2000 因缺北交所小票只覆盖约 35%，"
           "所以该列是占比参照不是绝对家数")


def _norm_date(d: str) -> str:
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if "-" not in d else d


def _missing_trade_days(start: str, end: str, have: set[str]) -> list[str]:
    """快照区间内「是交易日但没有快照」的日期（YYYYMMDD 升序）。

    表只覆盖「跑过 snapshot 的日子」，而 snapshot 是手动触发的。缺的日子
    会被误读成「休市」，尤其是环比类指标（涨停家数、创新高家数）会断层。
    交易日历取自个股表的 distinct date，与 market/fetch.py 反推日历的口径一致。
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                f"SELECT DISTINCT date FROM {DAILY_BAR_TABLE} "
                f"WHERE date >= ? AND date <= ? ORDER BY date",
                (_norm_date(start), _norm_date(end))).fetchall()
    except sqlite3.Error:
        return []
    return [str(r[0]).replace("-", "") for r in rows if str(r[0]).replace("-", "") not in have]


def daily_table(days: int = DAYS_DEFAULT) -> dict:
    """返回最近 days 个快照拼成的表。"""
    hist = load_history()
    if not hist:
        return {"error": "history/ 为空，先跑 `python -m market.cli snapshot`"}

    dates = sorted(hist)[-days:]
    amv = load_amv()
    amv_by = {}
    if not amv.empty:
        for _, r in amv.iterrows():
            amv_by[r["date"].strftime("%Y-%m-%d")] = r

    rows = []
    for d in dates:
        snap = hist[d]
        zt = snap.get("limit_up") or []
        nh = snap.get("newhigh") or {}
        a = amv_by.get(_norm_date(d))

        rows.append({
            "日期": d,
            "活跃市值": round(float(a["close"]), 1) if a is not None else None,
            "活跃市值涨跌": (round(float(a["change_pct"]), 2)
                             if a is not None and pd.notna(a.get("change_pct")) else None),
            # 空 list 表示抓取失败，不是「0 家涨停」
            "涨停": len(zt) if zt else None,
            "沪深300新高": nh.get("hs300_newhigh"),
            "沪深300总数": nh.get("hs300_total"),
            "沪深300占比": nh.get("hs300_pct"),
            "中证2000新高": nh.get("csi2000_newhigh"),
            "中证2000总数": nh.get("csi2000_total"),
            "中证2000占比": nh.get("csi2000_pct"),
        })

    # 分母取最近一期的实际值——它随库中行情覆盖变化，不该在口径里写死
    latest_nh = next((r for r in reversed(rows) if r.get("沪深300总数")), None)
    denom = ""
    if latest_nh:
        denom = (f"最新一期分母：沪深300 {latest_nh['沪深300总数']} 只、"
                 f"中证2000 {latest_nh['中证2000总数']} 只")

    missing_amv = [r["日期"] for r in rows if r["活跃市值"] is None]
    missing_days = (_missing_trade_days(rows[0]["日期"], rows[-1]["日期"],
                                        {r["日期"] for r in rows})
                    if rows else [])
    return {
        "行数": len(rows),
        "起": rows[0]["日期"] if rows else None,
        "止": rows[-1]["日期"] if rows else None,
        "rows": rows,
        "分母": denom,
        "0AMV缺失": missing_amv,
        "缺失交易日": missing_days,
        "口径": CALIBER,
    }


def _fmt(v, digits: int = 0, suffix: str = "") -> str:
    if v is None:
        return "—"
    if digits:
        return f"{v:,.{digits}f}{suffix}"
    return f"{v:,.0f}{suffix}"


def render_table(a: dict) -> str:
    if a.get("error"):
        return f"❌ {a['error']}"

    L = [f"# 每日观察数据表　{a['起']} ~ {a['止']}（{a['行数']} 个交易日）", ""]
    L.append("| 日期 | 活跃市值 | 涨跌 | 涨停 | 沪深300新高 | 中证2000新高 |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for r in a["rows"]:
        nh_hs = ("—" if r["沪深300新高"] is None
                 else f"{r['沪深300新高']}（{r['沪深300占比']}%）")
        nh_cs = ("—" if r["中证2000新高"] is None
                 else f"{r['中证2000新高']}（{r['中证2000占比']}%）")
        L.append(
            f"| {r['日期']} | {_fmt(r['活跃市值'])} "
            f"| {_fmt(r['活跃市值涨跌'], 2, '%')} "
            f"| {_fmt(r['涨停'])} | {nh_hs} | {nh_cs} |"
        )

    L.append("")
    L.append(f"> 口径：{a['口径']}")
    if a["分母"]:
        L.append(f"> {a['分母']}")
    if a["缺失交易日"]:
        d = a["缺失交易日"]
        L.append(f"> ⚠ **区间内有 {len(d)} 个交易日没有快照**，环比在这里是断的（不是休市）："
                 f"{'、'.join(d[:8])}" + ("…" if len(d) > 8 else ""))
        L.append("> 补法：`python -m market.cli backfill --days N`（涨停池与创新高可回溯；"
                 "乐咕活跃度/板块榜是实时接口，补不出来）")
    if a["0AMV缺失"]:
        L.append(f"> ⚠ 0AMV 缺 {len(a['0AMV缺失'])} 天（手工录入，落后是常态）："
                 f"{'、'.join(a['0AMV缺失'][:6])}"
                 + ("…" if len(a["0AMV缺失"]) > 6 else ""))
    L.append("> 涨停列为「—」表示当日快照没抓到涨停池，不是「0 家涨停」")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="每日观察数据表")
    ap.add_argument("--days", type=int, default=DAYS_DEFAULT, help=f"回看天数（默认 {DAYS_DEFAULT}）")
    args = ap.parse_args()
    print(render_table(daily_table(args.days)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
