"""行业板块超跌扫描：等权合成板块指数 → KDJ → 筛超卖。

对应《大富翁(4)》里那条「来看领跌的品种，就是我们的 KDJ 为负……如果要做超跌反弹的
短线，也可以从这里面选择合适的目标」。**按板块层面做**——文章里「这两个是同一板块的
共振」说的是板块，个股粒度每天几十只会看得疲劳。

做法：把每个行业的成分股先各自归一到窗口首日，再按日取均值，得到一条等权板块指数，
对它跑 KDJ。**不是把成分股的 J 平均**——平均 J 与「板块指数的 J」不等价，前者会被
成分股数量稀释。

两个口径选择，都写在返回值里：

- **收盘价口径**：只用 close 合成，high/low 传 close。这样 RSV 的分子分母退化为
  「窗口内最高收盘/最低收盘」，是标准的收盘价随机指标。与 `fetch_newhigh_divergence`
  的收盘价口径一致。
- **等权而非市值加权**：`stock_base_info` 里没有市值字段，且等权更能反映「板块里
  多数票的体感」，与超跌反弹的用法匹配。

用法:
    python -m market.sector [YYYYMMDD]
"""
from __future__ import annotations

import sys
from typing import Optional

import pandas as pd

from datas.query_stock import query_close_matrix, query_stock_industry_map
from indicators.kdj import add_kdj_to_dataframe
from market.fetch import fetch_newhigh_codes

LOOKBACK = 120          # 合成指数取多长窗口（KDJ(9) 需要足够历史让 K/D 收敛）
KDJ_PERIOD = 9
TOP_DEFAULT = 12
CALENDAR_PAD = 260      # 往回多取些自然日，保证够 LOOKBACK 个交易日
MIN_MEMBERS = 5         # 成分太少的行业不参与（保险只有 5 只，噪声大）

CALIBER = ("板块指数为成分股等权合成（各股先归一到窗口首日再取均值）、收盘价口径；"
           "KDJ(9) 跑在合成指数上，不是成分股 J 的平均；负值 = 超卖")


def _norm_date(target: str) -> str:
    t = str(target).strip()
    return f"{t[:4]}-{t[4:6]}-{t[6:8]}" if "-" not in t else t


def oversold_sectors(target: str, top: int = TOP_DEFAULT,
                     lookback: int = LOOKBACK) -> dict:
    """返回 KDJ 为负（超卖）的行业板块，按当日跌幅排序。"""
    day = _norm_date(target)
    start = (pd.Timestamp(day) - pd.Timedelta(days=CALENDAR_PAD)).strftime("%Y-%m-%d")

    mat = query_close_matrix(start, day)
    if mat.empty:
        return {"error": f"{day} 之前无行情数据"}
    mat = mat.tail(lookback)
    if len(mat) < KDJ_PERIOD + 5:
        return {"error": f"可用交易日仅 {len(mat)} 天，不足以算 KDJ"}

    industry = query_stock_industry_map()
    if not industry:
        return {"error": "stock_base_info 无行业字段（idn_name 为空）"}

    by_ind: dict[str, list[str]] = {}
    for c in mat.columns:
        name = industry.get(c)
        if name:
            by_ind.setdefault(name, []).append(c)

    rows = []
    for name, cols in by_ind.items():
        if len(cols) < MIN_MEMBERS:
            continue
        sub = mat[cols]
        # bfill 让上市/停牌导致的头部 NaN 取到首个有效值，避免整列被丢弃
        base = sub.bfill().iloc[0]
        sub = sub.loc[:, base.notna() & (base > 0)]
        if sub.shape[1] < MIN_MEMBERS:
            continue
        syn = (sub / base[sub.columns]).mean(axis=1)

        df = pd.DataFrame({"high": syn, "low": syn, "close": syn})
        add_kdj_to_dataframe(df, inplace=True, period=KDJ_PERIOD)
        j = df["kdj_j"].iloc[-1]
        if pd.isna(j):
            continue

        pct = (syn.iloc[-1] / syn.iloc[-2] - 1) * 100 if len(syn) > 1 else 0.0
        rows.append({
            "行业": name, "J值": round(float(j), 2),
            "当日": round(float(pct), 2), "成分数": int(sub.shape[1]),
        })

    if not rows:
        return {"error": "没有算出任何板块（成分数或数据不足）"}

    oversold = [r for r in rows if r["J值"] < 0]
    # 按 J 升序（越负越超跌），不按跌幅。普跌行情里大半个市场都超卖，
    # 「是否在榜」没有区分度，排序才有——实测 2026-09-15 有 68/90 个行业超卖。
    oversold.sort(key=lambda r: r["J值"])

    note = None
    if rows and len(oversold) / len(rows) >= 0.6:
        note = (f"{len(oversold)}/{len(rows)} 个行业 KDJ 为负（普跌格局）——这个筛选几乎不筛东西，"
                f"看排序不看是否在榜")
    return {
        "数据日期": mat.index[-1].strftime("%Y-%m-%d"),
        "行业总数": len(rows),
        "超卖数": len(oversold),
        "超卖板块": oversold[:top],
        "提示": note,
        "口径": CALIBER,
    }


def newhigh_sectors(target: str, window: int = 20, top: int = 10) -> dict:
    """创 window 日新高的股票按行业聚合。

    「创 20 日新高 → 找资金抱团板块」——家数只说明突破的**广度**，
    下钻到行业才知道是**谁**在突破。这是找方向的入口：哪类票在创新高，
    就去对应板块找预案。

    这里统计的是**全市场**的创新高家数（不只是沪深300/中证2000 成分），
    所以总数会比 L2 那两个口径大。
    """
    codes = fetch_newhigh_codes(target, window)
    if not codes:
        return {"error": f"{target} 取不到创新高名单（数据不足或行情库缺失）"}

    industry = query_stock_industry_map()
    if not industry:
        return {"error": "stock_base_info 无行业字段"}

    by_ind: dict[str, list[str]] = {}
    for c in codes:
        name = industry.get(c)
        if name:
            by_ind.setdefault(name, []).append(c)
    if not by_ind:
        return {"error": "创新高名单与行业表对不上（代码格式？）"}

    rows = [{"行业": k, "家数": len(v), "个股": sorted(v)[:5]}
            for k, v in sorted(by_ind.items(), key=lambda kv: -len(kv[1]))]

    # 集中度：前 3 大行业占全部创新高家的比例。越高说明抱团越集中
    total = sum(r["家数"] for r in rows)
    top3 = sum(r["家数"] for r in rows[:3])
    concentration = round(top3 / total * 100, 1) if total else None

    return {
        "数据日期": target,
        "窗口": window,
        "创新高总数": total,
        "覆盖行业": len(rows),
        "行业": rows[:top],
        "前3集中度": concentration,
        "口径": (f"全市场收盘价创 {window} 日新高的股票按行业聚合；"
                 "家数为该行业内创新高的只数，非全部成分；"
                 "集中度 = 前三行业家数 ÷ 创新高总数，越高说明抱团越集中"),
    }


def render_newhigh_sectors(a: dict) -> str:
    if a.get("error"):
        return f"❌ {a['error']}"
    lines = [f"# 创 {a['窗口']} 日新高的行业分布　{a['数据日期']}"
             f"　共 {a['创新高总数']} 只 / {a['覆盖行业']} 个行业", ""]
    for r in a["行业"]:
        lines.append(f"  {r['行业']:<10} {r['家数']:>3} 只   "
                     f"{' '.join(r['个股'][:3])}")
    if a["前3集中度"] is not None:
        lines.append(f"\n前 3 行业集中度：{a['前3集中度']}%")
    lines.append(f"\n> {a['口径']}")
    return "\n".join(lines)


def render_sectors(a: dict) -> str:
    if a.get("error"):
        return f"❌ {a['error']}"
    lines = [f"# 超跌板块（KDJ 为负，按超卖深度排序）　{a['数据日期']}"
             f"　{a['超卖数']}/{a['行业总数']} 个行业", ""]
    if not a["超卖板块"]:
        lines.append("无超卖板块。")
    for r in a["超卖板块"]:
        lines.append(f"  {r['行业']:<10} J={r['J值']:>7.2f}   当日 {r['当日']:+6.2f}%   "
                     f"成分 {r['成分数']}")
    if a.get("提示"):
        lines.append(f"\n⚠ {a['提示']}")
    lines.append(f"\n> {a['口径']}")
    return "\n".join(lines)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else pd.Timestamp.today().strftime("%Y%m%d")
    print(render_sectors(oversold_sectors(arg)))
