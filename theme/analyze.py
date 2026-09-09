"""主题/主线分析：情绪温度计、涨停梯队、板块持续性、主线候选。

只做客观聚合与规则线，不下「主线就是 XX」的结论——那是研判（研究假设层），
由人/AI 基于这些事实做。

持续性（主线区别于一日游的核心）依赖 theme/history/ 多日快照：
    板块连续 N 日进入涨幅榜前 15 → 候选主线；单日脉冲 → 仅主题。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from theme.fetch import load_history

# 规则阈值（第一版，可调，先观察后标定）
TOP_N = 15          # 每日涨幅榜前多少名算「上榜」
PERSIST_DAYS = 3    # 连续几天上榜算持续性候选
HIGHEST_BOARD_MIN = 3  # 板块内最高连板 ≥ 3 才算有高度


def temperature(market: dict, n_zt: int, n_broken: int) -> dict:
    """情绪温度计：0~100，加一句定性。

    依据：真实涨停数、涨跌家数比、炸板率、连板高度。规则线先粗后调。
    """
    if not market:
        return {"score": None, "label": "无情绪数据"}

    real_zt = market.get("real_limit_up", 0)
    up = market.get("up", 0)
    down = market.get("down", 0)
    total = up + down
    up_ratio = up / total if total else 0.5
    broken_rate = n_broken / (n_broken + n_zt) if (n_broken + n_zt) else 0

    # 各维度 0~100
    s_zt = min(100, real_zt * 2.5)                  # 40 只真实涨停 = 100
    s_breadth = up_ratio * 100
    s_broken = (1 - broken_rate) * 100
    score = int(round(0.4 * s_zt + 0.35 * s_breadth + 0.25 * s_broken))

    if score >= 75:
        label = "活跃·情绪高位"
    elif score >= 55:
        label = "回暖·可参与"
    elif score >= 35:
        label = "低迷·挑着做"
    else:
        label = "冰点·防守为主"

    return {
        "score": score,
        "label": label,
        "真实涨停": real_zt,
        "炸板率": round(broken_rate * 100, 1),
        "涨跌比": f"{up:.0f}:{down:.0f}",
    }


def zt_industry_agg(limit_up: list[dict]) -> list[dict]:
    """涨停池按行业聚合：家数、最高连板、代表股。"""
    groups: dict[str, dict] = {}
    for s in limit_up:
        ind = s.get("industry") or "未知"
        g = groups.setdefault(ind, {"行业": ind, "涨停家数": 0, "最高连板": 0, "封板资金合计": 0.0, "代表": []})
        g["涨停家数"] += 1
        g["最高连板"] = max(g["最高连板"], s["boards"])
        g["封板资金合计"] += s.get("seal_amt", 0)
        if len(g["代表"]) < 3:
            g["代表"].append(f"{s['name']}{s['boards']}板")
    return sorted(groups.values(), key=lambda g: (-g["涨停家数"], -g["最高连板"]))


def board_ladder(limit_up: list[dict]) -> list[dict]:
    """连板梯队：按连板数从高到低列。"""
    ladder: dict[int, list[dict]] = {}
    for s in limit_up:
        ladder.setdefault(s["boards"], []).append(s)
    out = []
    for boards in sorted(ladder, reverse=True):
        stocks = sorted(ladder[boards], key=lambda s: s.get("seal_amt", 0), reverse=True)
        out.append({
            "连板": boards,
            "家数": len(stocks),
            "个股": [{"code": s["code"], "name": s["name"],
                      "industry": s["industry"],
                      "seal_amt_yi": round(s.get("seal_amt", 0) / 1e8, 2)}
                     for s in stocks],
        })
    return out


def top_boards(days: int = 5) -> dict:
    """板块持续性：近 N 日每天上榜次数与平均涨幅。

    行业用同花顺口径（industry_ths），概念用新浪口径（concept_sina），分开算。
    """
    hist = load_history()
    dates = sorted(hist)[-days:]
    if not dates:
        return {"行业": [], "概念": [], "覆盖交易日": []}

    def persist(key: str, col_pct: str) -> list[dict]:
        stats: dict[str, dict] = {}
        for d in dates:
            snap = hist[d]
            boards = snap.get(key) or []
            ranked = sorted(boards, key=lambda b: float(b.get(col_pct, 0) or -999),
                            reverse=True)[:TOP_N]
            for b in ranked:
                name = b["name"]
                st = stats.setdefault(name, {"板块": name, "上榜": 0, "涨幅合计": 0.0, "天数": 0})
                st["上榜"] += 1
                st["涨幅合计"] += float(b.get(col_pct, 0) or 0)
        out = []
        for st in stats.values():
            if st["上榜"] >= PERSIST_DAYS:      # 只有多日上榜才进候选
                out.append({
                    "板块": st["板块"],
                    "上榜天数": st["上榜"],
                    "覆盖天数": len(dates),
                    "均涨幅": round(st["涨幅合计"] / st["上榜"], 2),
                })
        return sorted(out, key=lambda x: (-x["上榜天数"], -x["均涨幅"]))

    return {
        "行业": persist("industry_ths", "pct"),
        "概念": persist("concept_sina", "pct"),
        "覆盖交易日": dates,
    }


def day_rank(days: int = 5) -> dict:
    """每日板块榜前 15（行业/概念），供看当日与最近几天的结构。"""
    hist = load_history()
    dates = sorted(hist)[-days:]
    out = {"行业": {}, "概念": {}}
    for d in dates:
        snap = hist[d]
        for key in ("行业", "概念"):
            src = snap.get("industry_ths" if key == "行业" else "concept_sina") or []
            ranked = sorted(src, key=lambda b: float(b.get("pct", 0) or -999), reverse=True)[:TOP_N]
            out[key][d] = [{"name": b["name"], "pct": float(b.get("pct", 0) or 0),
                            "leader": b.get("leader", b.get("leader_pct") and "") or ""}
                           for b in ranked]
    return out


def analyze(date: Optional[str] = None, days: int = 5) -> dict:
    """汇总一份分析 dict（渲染层再排成文本）。date 缺省 = 最新快照。"""
    hist = load_history()
    if not hist:
        return {"error": "history/ 为空，先跑 `python -m theme.cli snapshot`"}
    target = date or sorted(hist)[-1]
    if target not in hist:
        return {"error": f"没有 {target} 的快照"}

    snap = hist[target]
    market = snap.get("market", {})
    zt = snap.get("limit_up", [])
    broken = snap.get("broken", [])

    # 涨停数走势：温度计初版按绝对数打分，不看趋势会误判（93→73→48 递减
    # 是退潮，绝对数 42 却给高分）。走势列出来，趋势由人/AI 判断。
    zt_trend = {d: len(hist[d].get("limit_up") or []) for d in sorted(hist)[-6:]}

    return {
        "date": target,
        "温度计": temperature(market, len(zt), len(broken)),
        "涨停走势": zt_trend,
        "涨停行业分布": zt_industry_agg(zt)[:10],
        "连板梯队": board_ladder(zt),
        "板块持续性": top_boards(days),
        "涨停延续性": zt_persist(days),
        "当日行业榜": day_rank(1)["行业"].get(target, [])[:15],
        "当日概念榜": day_rank(1)["概念"].get(target, [])[:15],
        "errors": snap.get("errors", []),
    }


def render(a: dict) -> str:
    if a.get("error"):
        return f"❌ {a['error']}"
    L: list[str] = [f"# 主题/主线观察　{a['date']}", ""]

    t = a["温度计"]
    if t.get("score") is not None:
        L.append(f"## 市场温度　{t['label']}（{t['score']}）")
        L.append(f"真实涨停 {t['真实涨停']:.0f}　炸板率 {t['炸板率']}%　"
                 f"涨跌比 {t['涨跌比']}")
        trend = a.get("涨停走势") or {}
        if trend:
            L.append(f"涨停数走势：{'　'.join(f'{d[4:6]}-{d[6:8]} {n}' for d, n in trend.items())}")
        L.append("> 温度计是初版规则线（绝对数打分），趋势与结构请人/AI 研判，标定待积累")
    L.append("")

    ladder = a["连板梯队"]
    if ladder:
        L.append("## 涨停梯队")
        for rung in ladder:
            names = "　".join(f"{s['name']}({s['industry']},封{s['seal_amt_yi']}亿)"
                              for s in rung["个股"])
            L.append(f"**{rung['连板']} 板 × {rung['家数']}**：{names}")
        L.append("")

    dist = a["涨停行业分布"]
    if dist:
        L.append("## 涨停行业分布（当日）")
        for g in dist:
            L.append(f"{g['行业']}　{g['涨停家数']} 家（最高 {g['最高连板']} 板）"
                     f"　{' '.join(g['代表'])}")
        L.append("")

    for key, label in (("行业", "同花顺行业"), ("概念", "新浪概念")):
        top = a.get("当日" + ("行业榜" if key == "行业" else "概念榜"))
        if top:
            L.append(f"## 当日涨幅前 15（{label}）")
            L.append("　".join(f"{b['name']} {b['pct']:+.1f}%" for b in top))
            L.append("")

    ztp = a.get("涨停延续性") or {}
    if ztp.get("题材"):
        L.append("## 涨停题材延续性（东财行业口径）")
        for r in ztp["题材"]:
            L.append(f"{r['行业']}　{r['覆盖']} 天中 {r['天数']} 天进涨停家数前6"
                     f"（日均 {r['家数日均']} 家，最高 {r['最高连板']} 板）")
        L.append("")

    persist = a["板块持续性"]
    if persist.get("行业") or persist.get("概念"):
        L.append("## 持续性候选（主线观察池）")
        for key, label in (("行业", "行业"), ("概念", "概念")):
            rows = persist[key]
            if rows:
                L.append(f"**{label}**（{persist['覆盖交易日']} 日内 ≥3 日上榜）：")
                L.append("　".join(f"{r['板块']}({r['上榜天数']}/{r['覆盖天数']}天,"
                                   f"均{r['均涨幅']:+.1f}%)" for r in rows[:8]))
        L.append("")
        L.append("> 上表是客观候选：多日上榜且均涨幅为正。哪个是真主线、处于什么阶段，"
                 "需结合涨停梯队、龙头结构人工研判。")
    else:
        L.append("\n## 持续性候选\n（不足 3 日，无 — 最近都在炒一日游）")
        L.append("")

    if a["errors"]:
        L.append("⚠ 抓取不完整：" + "；".join(a["errors"]))

    return "\n".join(L)


def zt_persist(days: int = 5) -> dict:
    """涨停题材延续性（东财行业口径，多日涨停池聚合）。

    东财涨停池支持历史日期，可补抓；industry/concept 榜是实时接口只能逐日累积。
    判断「题材是否持续」用涨停结构：某行业连续 N 天有涨停、高度板延续。
    """
    hist = load_history()
    dates = sorted(hist)[-days:]
    if not dates:
        return {"覆盖交易日": [], "题材": []}

    per_day: dict[str, list[dict]] = {}
    for d in dates:
        zt = hist[d].get("limit_up") or []
        agg = zt_industry_agg(zt)
        per_day[d] = {g["行业"]: g for g in agg}

    # 行业出现在「当日涨停家数前 6」的天数
    stats: dict[str, dict] = {}
    for d in dates:
        top = sorted(per_day[d].values(), key=lambda g: -g["涨停家数"])[:6]
        for g in top:
            st = stats.setdefault(g["行业"], {"行业": g["行业"], "天数": 0, "家数合计": 0,
                                              "最高连板": 0, "日期": []})
            st["天数"] += 1
            st["家数合计"] += g["涨停家数"]
            st["最高连板"] = max(st["最高连板"], g["最高连板"])
            st["日期"].append(d)

    rows = []
    for st in stats.values():
        if st["天数"] >= 2:          # ≥2 天进榜才算有延续性
            rows.append({
                "行业": st["行业"],
                "天数": st["天数"],
                "覆盖": len(dates),
                "家数日均": round(st["家数合计"] / st["天数"], 1),
                "最高连板": st["最高连板"],
            })
    rows.sort(key=lambda r: (-r["天数"], -r["最高连板"], -r["家数日均"]))
    return {"覆盖交易日": dates, "题材": rows}
