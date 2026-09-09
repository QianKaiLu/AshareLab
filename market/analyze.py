"""市场环境分析：情绪周期 → 资金风向 → 主题结构 → 主线判定。

只做客观聚合与规则判定，不下「主线就是 XX」的结论——那属于研究假设层，
由人/AI 结合盘面与消息面研判。设计与决策依据见 docs/market/设计方案.md。

四层各自独立回答一个问题：
    L1 情绪周期   现在能不能做、做多重      → 仓位基调
    L2 资金风向   该做大票还是小票          → 选股池方向
    L3 主题结构   资金在炒什么              → 候选范围
    L4 主线判定   哪个是主线、哪些是支线    → 优先级与回避

L1 一律用环比：单日截面会误判（涨停 93→73→48 递减时绝对数仍有 42）。
"""

from __future__ import annotations

from typing import Any, Optional

from market.fetch import load_history

# ---- L1 情绪阈值（来自调研版经验值，待用回溯数据标定）
ZT_CRAZY, ZT_HOT, ZT_COLD = 80, 60, 30
LIMIT_DOWN_COLD = 15
BOARD_HOT, BOARD_COLD = 5, 2
ZBR_HOT, ZBR_COLD = 0.25, 0.40          # 炸板率
PROMOTE_HOT, PROMOTE_COLD = 50.0, 35.0  # 晋级率 %
ZT_SLUMP_RATIO = 0.7                    # 涨停数环比跌破此比例算大幅下滑

# ---- L2 大小票分歧
LEAN_GAP = 2.0                          # 占比差超过此值算某一边占优

# ---- L3/L4 主题与主线
TOP_N = 15              # 板块涨幅榜取前多少名算「上榜」
PERSIST_DAYS = 3        # 近 N 日中上榜几天算有持续性
ZT_TOP_K = 6            # 涨停家数前 K 名算「涨停集中板块」
LEADER_BOARD_MIN = 3    # 板块内最高连板达到几板算有龙头


def _series(hist: dict[str, dict], days: int) -> list[str]:
    return sorted(hist)[-days:]


# ============================================================ L1 情绪周期

def emotion(hist: dict[str, dict], target: str) -> dict:
    """情绪周期五段状态机。环比前一交易日，不看单日截面。"""
    dates = sorted(hist)
    if target not in dates:
        return {"error": f"无 {target} 快照"}
    i = dates.index(target)
    snap = hist[target]
    prev = hist[dates[i - 1]] if i > 0 else None

    zt = snap.get("limit_up") or []
    broken = snap.get("broken") or []
    market = snap.get("market") or {}
    me = snap.get("money_effect") or {}

    n_zt = len(zt)
    n_zb = len(broken)
    zbr = n_zb / (n_zt + n_zb) if (n_zt + n_zb) else None
    max_board = max((s.get("boards", 0) for s in zt), default=0)
    promote = me.get("promote_rate")
    premium = me.get("premium_median")

    prev_zt = len(prev.get("limit_up") or []) if prev else None
    prev_promote = (prev.get("money_effect") or {}).get("promote_rate") if prev else None
    zt_chg = (n_zt - prev_zt) if prev_zt is not None else None

    # 状态判定：优先级从高到低，先排除极端再判趋势
    limit_down = market.get("real_limit_down") or market.get("limit_down") or 0
    stage = "中性"
    reason = []

    if n_zt < ZT_COLD and max_board <= BOARD_COLD:
        stage = "冰点期"
        reason.append(f"涨停 {n_zt}<{ZT_COLD} 且最高 {max_board} 板")
        if limit_down >= LIMIT_DOWN_COLD:
            reason.append(f"跌停 {limit_down:.0f}")
    elif (prev_zt and n_zt < prev_zt * ZT_SLUMP_RATIO
          and (promote is None or promote < PROMOTE_COLD)):
        stage = "退潮期"
        reason.append(f"涨停 {prev_zt}→{n_zt} 环比 -{(1 - n_zt / prev_zt) * 100:.0f}%")
        if promote is not None:
            reason.append(f"晋级率 {promote}%<{PROMOTE_COLD}%")
    elif n_zt >= ZT_CRAZY and zbr is not None and zbr < ZBR_HOT:
        stage = "高潮期"
        reason.append(f"涨停 {n_zt}≥{ZT_CRAZY} 且炸板率 {zbr * 100:.0f}%<{ZBR_HOT * 100:.0f}%")
    elif max_board >= BOARD_HOT and n_zt >= 40:
        stage = "发酵期"
        reason.append(f"最高 {max_board} 板 且涨停 {n_zt}≥40")
    elif prev_zt is not None and n_zt > prev_zt and n_zt > ZT_COLD:
        stage = "启动期"
        reason.append(f"涨停 {prev_zt}→{n_zt} 回暖")

    # 赚钱效应单独作反向证据：状态偏乐观但赚钱效应为负时要点出来
    warn = []
    if promote is not None and promote < PROMOTE_COLD:
        warn.append(f"晋级率 {promote}% 偏低（<{PROMOTE_COLD}%）")
    if premium is not None and premium < 0:
        warn.append(f"昨日涨停溢价中位 {premium}%（打板资金亏钱）")
    if zbr is not None and zbr > ZBR_COLD:
        warn.append(f"炸板率 {zbr * 100:.0f}% 偏高（>{ZBR_COLD * 100:.0f}%）")

    advice = {
        "冰点期": "空仓等新题材拐点",
        "启动期": "小仓位试错",
        "发酵期": "主线可重仓",
        "高潮期": "边打边撤，逐步止盈",
        "退潮期": "降仓观望，不追高",
        "中性": "按个股规则做，不加杠杆",
    }[stage]

    return {
        "stage": stage,
        "advice": advice,
        "依据": reason,
        "反向证据": warn,
        "涨停": n_zt,
        "涨停环比": zt_chg,
        "炸板": n_zb,
        "炸板率": round(zbr * 100, 1) if zbr is not None else None,
        "最高连板": max_board,
        "晋级率": promote,
        "晋级率环比": (round(promote - prev_promote, 1)
                       if promote is not None and prev_promote is not None else None),
        "昨日涨停溢价中位": premium,
        "涨跌比": (f"{market.get('up'):.0f}:{market.get('down'):.0f}"
                   if market.get("up") and market.get("down") else None),
    }


def zt_trend(hist: dict[str, dict], days: int = 8) -> list[dict]:
    """涨停数与晋级率走势——趋势比绝对值更能说明问题。"""
    out = []
    for d in _series(hist, days):
        snap = hist[d]
        me = snap.get("money_effect") or {}
        out.append({
            "date": d,
            "涨停": len(snap.get("limit_up") or []),
            "晋级率": me.get("promote_rate"),
            "溢价中位": me.get("premium_median"),
        })
    return out


# ============================================================ L2 资金风向

def divergence(hist: dict[str, dict], target: str, days: int = 6) -> dict:
    """大小票分歧（modoo 复盘法）：沪深300 vs 中证2000 创 20 日新高家数。

    涨停/炸板/晋级都是短线游资口径，看不见机构。这一层补的正是这个盲区。
    """
    cur = (hist.get(target) or {}).get("newhigh") or {}
    trend = []
    for d in _series(hist, days):
        nh = (hist[d].get("newhigh") or {})
        if nh.get("hs300_pct") is None:
            continue
        trend.append({
            "date": d,
            "hs300": nh.get("hs300_newhigh"),
            "hs300_pct": nh.get("hs300_pct"),
            "csi2000": nh.get("csi2000_newhigh"),
            "csi2000_pct": nh.get("csi2000_pct"),
            "lean": nh.get("lean"),
        })
    out = dict(cur)
    out["走势"] = trend
    if cur.get("lean"):
        out["解读"] = {
            "小票占优": "游资活跃，题材/小票方向为主",
            "大票占优": "机构主导，权重/主线方向为主",
            "均衡": "两边都无明显突破优势",
        }.get(cur["lean"])
    return out


# ============================================================ L3 主题结构

def zt_industry_agg(limit_up: list[dict]) -> list[dict]:
    """涨停池按行业聚合：家数、最高连板、封单合计、代表股。

    主口径用涨停归属而非概念榜：一只票同属几十个概念，概念榜涨幅是成分平均，
    易被单只暴涨股拉动；涨停是真金白银投的票，归属明确。
    """
    groups: dict[str, dict] = {}
    for s in limit_up:
        ind = s.get("industry") or "未知"
        g = groups.setdefault(ind, {"行业": ind, "涨停家数": 0, "最高连板": 0,
                                    "首板家数": 0, "封单合计亿": 0.0, "代表": []})
        g["涨停家数"] += 1
        g["最高连板"] = max(g["最高连板"], s.get("boards", 0))
        if s.get("boards", 0) == 1:
            g["首板家数"] += 1
        g["封单合计亿"] += s.get("seal_amt", 0) / 1e8
        if len(g["代表"]) < 3:
            g["代表"].append(f"{s['name']}{s.get('boards', 0)}板")
    for g in groups.values():
        g["封单合计亿"] = round(g["封单合计亿"], 2)
        # 梯队完整 = 有连板龙头 + 有首板跟进，说明资金分层而非单股独立行情
        g["梯队完整"] = g["最高连板"] >= LEADER_BOARD_MIN and g["首板家数"] >= 1
    return sorted(groups.values(), key=lambda g: (-g["涨停家数"], -g["最高连板"]))


def board_ladder(limit_up: list[dict]) -> list[dict]:
    """连板梯队：按连板数从高到低。"""
    ladder: dict[int, list[dict]] = {}
    for s in limit_up:
        ladder.setdefault(s.get("boards", 0), []).append(s)
    out = []
    for boards in sorted(ladder, reverse=True):
        stocks = sorted(ladder[boards], key=lambda s: s.get("seal_amt", 0), reverse=True)
        out.append({
            "连板": boards,
            "家数": len(stocks),
            "个股": [{"code": s["code"], "name": s["name"],
                      "industry": s.get("industry", ""),
                      "封单亿": round(s.get("seal_amt", 0) / 1e8, 2)}
                     for s in stocks],
        })
    return out


def zt_persist(hist: dict[str, dict], days: int = 5) -> dict:
    """涨停题材延续性：近 N 日中有几天进入涨停家数前 K。

    区分主线与一日游的核心——单日脉冲明天就散，主线会连续上榜。
    """
    dates = _series(hist, days)
    if not dates:
        return {"覆盖交易日": [], "题材": []}

    stats: dict[str, dict] = {}
    for d in dates:
        agg = zt_industry_agg(hist[d].get("limit_up") or [])
        for g in sorted(agg, key=lambda x: -x["涨停家数"])[:ZT_TOP_K]:
            st = stats.setdefault(g["行业"], {
                "行业": g["行业"], "天数": 0, "家数合计": 0,
                "最高连板": 0, "梯队完整天数": 0, "日期": [],
            })
            st["天数"] += 1
            st["家数合计"] += g["涨停家数"]
            st["最高连板"] = max(st["最高连板"], g["最高连板"])
            st["梯队完整天数"] += 1 if g["梯队完整"] else 0
            st["日期"].append(d)

    rows = []
    for st in stats.values():
        if st["天数"] >= 2:
            rows.append({
                "行业": st["行业"],
                "天数": st["天数"],
                "覆盖": len(dates),
                "家数日均": round(st["家数合计"] / st["天数"], 1),
                "最高连板": st["最高连板"],
                "梯队完整天数": st["梯队完整天数"],
                "最近上榜": st["日期"][-1],
            })
    rows.sort(key=lambda r: (-r["天数"], -r["最高连板"], -r["家数日均"]))
    return {"覆盖交易日": dates, "题材": rows}


def board_rank(hist: dict[str, dict], target: str, top: int = TOP_N) -> dict:
    """板块榜（东财概念/行业，已过滤非题材板块）。仅当日快照含。

    这是交叉验证口径，不作主证——概念归属噪声大。
    """
    snap = hist.get(target) or {}
    boards = snap.get("boards_em") or {}
    out: dict[str, Any] = {}
    for key, label in (("concept", "概念"), ("industry", "行业")):
        rows = boards.get(key) or []
        if not rows:
            continue
        ranked = sorted(rows, key=lambda b: (b.get("pct") if b.get("pct") is not None else -999),
                        reverse=True)[:top]
        out[label] = [{"name": b["name"], "pct": b.get("pct"),
                       "amount_yi": b.get("amount_yi"),
                       "up": b.get("up"), "down": b.get("down"),
                       "leader": b.get("leader")} for b in ranked]
    if not out:
        # 降级到备份源
        for key, label in (("concept_sina", "概念(新浪)"), ("industry_ths", "行业(同花顺)")):
            rows = snap.get(key) or []
            if rows:
                ranked = sorted(rows, key=lambda b: float(b.get("pct") or -999),
                                reverse=True)[:top]
                out[label] = [{"name": b["name"], "pct": b.get("pct")} for b in ranked]
    return out


# ============================================================ L4 主线判定

def mainline(hist: dict[str, dict], target: str, days: int = 5) -> dict:
    """主线 / 支线 / 冷门三级判定。硬规则分层，不用加权总分。

    主线需同时满足四条：梯队完整、多日持续、赚钱效应为正、资金环比放大。
    满足 1~2 条为支线。分层由规则定，同层内才用综合分排序。
    """
    snap = hist.get(target) or {}
    zt = snap.get("limit_up") or []
    if not zt:
        return {"主线": [], "支线": [], "说明": "当日无涨停数据"}

    today_agg = {g["行业"]: g for g in zt_industry_agg(zt)}
    persist = {r["行业"]: r for r in zt_persist(hist, days)["题材"]}

    # 板块成交额环比：用东财行业榜（名称口径与涨停行业不完全一致，尽力匹配）
    boards = (snap.get("boards_em") or {}).get("industry") or []
    amt_today = {b["name"]: b.get("amount_yi") for b in boards}
    hist_dates = _series(hist, days)
    amt_hist: dict[str, list[float]] = {}
    for d in hist_dates[:-1]:
        for b in ((hist[d].get("boards_em") or {}).get("industry") or []):
            if b.get("amount_yi") is not None:
                amt_hist.setdefault(b["name"], []).append(b["amount_yi"])

    def amount_expanding(name: str) -> Optional[bool]:
        """成交额是否高于前几日均值。用环比放大而非绝对分位——绝对额高的
        多是大市值权重板块，不是题材主线。"""
        cur = amt_today.get(name)
        past = amt_hist.get(name)
        if cur is None or not past:
            return None
        return cur > sum(past) / len(past)

    main, sub = [], []
    for ind, g in today_agg.items():
        p = persist.get(ind)
        checks = {
            "梯队完整": g["梯队完整"],
            "多日持续": bool(p and p["天数"] >= PERSIST_DAYS),
            "资金环比放大": amount_expanding(ind),
        }
        hit = sum(1 for v in checks.values() if v is True)
        row = {
            "行业": ind,
            "涨停家数": g["涨停家数"],
            "最高连板": g["最高连板"],
            "首板家数": g["首板家数"],
            "封单合计亿": g["封单合计亿"],
            "持续天数": p["天数"] if p else 0,
            "覆盖": p["覆盖"] if p else 0,
            "满足条件": [k for k, v in checks.items() if v is True],
            "未满足": [k for k, v in checks.items() if v is False],
            "无法判定": [k for k, v in checks.items() if v is None],
            "代表": g["代表"],
        }
        if checks["梯队完整"] and checks["多日持续"]:
            main.append(row)
        elif hit >= 1:
            sub.append(row)

    key = lambda r: (-r["涨停家数"], -r["最高连板"], -r["封单合计亿"])
    return {
        "主线": sorted(main, key=key),
        "支线": sorted(sub, key=key)[:8],
        "口径": ("主线 = 梯队完整（≥3板龙头+首板跟进）且近 %d 日中 ≥%d 日进涨停家数前 %d；"
                 "赚钱效应与资金环比作辅证。板块成交额缺历史时标注「无法判定」。"
                 % (days, PERSIST_DAYS, ZT_TOP_K)),
    }


# ============================================================ 汇总与渲染

def analyze(date: Optional[str] = None, days: int = 5) -> dict:
    hist = load_history()
    if not hist:
        return {"error": "history/ 为空，先跑 `python -m market.cli snapshot`"}
    target = date or sorted(hist)[-1]
    if target not in hist:
        return {"error": f"没有 {target} 的快照"}

    snap = hist[target]
    zt = snap.get("limit_up") or []
    return {
        "date": target,
        "L1情绪": emotion(hist, target),
        "L1走势": zt_trend(hist),
        "L2风向": divergence(hist, target),
        "L3涨停分布": zt_industry_agg(zt)[:10],
        "L3连板梯队": board_ladder(zt),
        "L3延续性": zt_persist(hist, days),
        "L3板块榜": board_rank(hist, target),
        "L4主线": mainline(hist, target, days),
        "errors": snap.get("errors", []),
        "_note": snap.get("_note"),
    }


def render(a: dict) -> str:
    if a.get("error"):
        return f"❌ {a['error']}"
    L: list[str] = [f"# 市场环境分析　{a['date']}", ""]

    # ---- L1
    e = a["L1情绪"]
    if not e.get("error"):
        L.append(f"## L1 情绪周期：**{e['stage']}**　→ {e['advice']}")
        if e["依据"]:
            L.append("判定依据：" + "；".join(e["依据"]))
        bits = [f"涨停 {e['涨停']}"]
        if e["涨停环比"] is not None:
            bits.append(f"环比 {e['涨停环比']:+d}")
        bits.append(f"最高 {e['最高连板']} 板")
        if e["炸板率"] is not None:
            bits.append(f"炸板率 {e['炸板率']}%")
        if e["晋级率"] is not None:
            s = f"晋级率 {e['晋级率']}%"
            if e["晋级率环比"] is not None:
                s += f"（{e['晋级率环比']:+.1f}）"
            bits.append(s)
        if e["昨日涨停溢价中位"] is not None:
            bits.append(f"昨日涨停溢价中位 {e['昨日涨停溢价中位']:+.2f}%")
        if e["涨跌比"]:
            bits.append(f"涨跌比 {e['涨跌比']}")
        L.append("　".join(bits))
        if e["反向证据"]:
            L.append("⚠ 反向证据：" + "；".join(e["反向证据"]))

        trend = a["L1走势"]
        if trend:
            L.append("走势：" + "　".join(
                f"{t['date'][4:6]}-{t['date'][6:8]} {t['涨停']}"
                + (f"/{t['晋级率']:.0f}%" if t["晋级率"] is not None else "")
                for t in trend))
            L.append("> 格式：日期 涨停数/晋级率")
    L.append("")

    # ---- L2
    d = a["L2风向"]
    if d.get("hs300_pct") is not None:
        L.append(f"## L2 资金风向：**{d.get('lean')}**"
                 + (f"　{d['解读']}" if d.get("解读") else ""))
        L.append(f"创 {d.get('window', 20)} 日新高：沪深300 {d['hs300_newhigh']}/{d['hs300_total']}"
                 f"（{d['hs300_pct']}%）　中证2000 {d['csi2000_newhigh']}/{d['csi2000_total']}"
                 f"（{d['csi2000_pct']}%）")
        if d.get("走势"):
            L.append("走势：" + "　".join(
                f"{t['date'][4:6]}-{t['date'][6:8]} {t['hs300_pct']}%/{t['csi2000_pct']}%"
                for t in d["走势"]))
            L.append("> 格式：日期 沪深300占比/中证2000占比（modoo：小票看游资态度，大票看机构）")
        L.append("")

    # ---- L4 主线放在 L3 明细之前：结论优先
    ml = a["L4主线"]
    L.append("## L4 主线判定")
    if ml["主线"]:
        for r in ml["主线"]:
            L.append(f"**主线　{r['行业']}**　涨停 {r['涨停家数']} 家（最高 {r['最高连板']} 板"
                     f"，首板 {r['首板家数']} 家，封单 {r['封单合计亿']} 亿）"
                     f"　持续 {r['持续天数']}/{r['覆盖']} 日")
            L.append(f"　　{' '.join(r['代表'])}"
                     + (f"　辅证：{'、'.join(r['满足条件'])}" if r["满足条件"] else ""))
    else:
        L.append("**无板块同时满足梯队完整 + 多日持续 —— 当前无主线。**")
    if ml["支线"]:
        L.append("")
        L.append("支线（观察，小仓博弈）：")
        for r in ml["支线"][:6]:
            miss = f"　缺：{'、'.join(r['未满足'])}" if r["未满足"] else ""
            L.append(f"　{r['行业']}　{r['涨停家数']} 家/最高 {r['最高连板']} 板"
                     f"　持续 {r['持续天数']}/{r['覆盖']}{miss}")
    L.append("")
    L.append(f"> {ml['口径']}")
    L.append("")

    # ---- L3
    ladder = a["L3连板梯队"]
    if ladder:
        L.append("## L3 连板梯队")
        for rung in ladder[:4]:      # 只列高度板，首板太多
            names = "　".join(f"{s['name']}({s['industry']},封{s['封单亿']}亿)"
                              for s in rung["个股"][:8])
            more = f" 等 {rung['家数']} 家" if rung["家数"] > 8 else ""
            L.append(f"**{rung['连板']} 板 × {rung['家数']}**：{names}{more}")
        if len(ladder) > 4:
            tail = "、".join(f"{r['连板']} 板 {r['家数']} 家" for r in ladder[4:])
            L.append(f"（另有 {tail}）")
        L.append("")

    dist = a["L3涨停分布"]
    if dist:
        L.append("## L3 涨停行业分布（当日）")
        for g in dist:
            tag = "　✓梯队" if g["梯队完整"] else ""
            L.append(f"{g['行业']}　{g['涨停家数']} 家（最高 {g['最高连板']} 板，"
                     f"首板 {g['首板家数']}）{tag}　{' '.join(g['代表'])}")
        L.append("")

    per = a["L3延续性"]
    if per["题材"]:
        L.append(f"## L3 题材延续性（{len(per['覆盖交易日'])} 日窗口）")
        for r in per["题材"][:10]:
            L.append(f"{r['行业']}　{r['覆盖']} 天中 {r['天数']} 天进前 {ZT_TOP_K}"
                     f"（日均 {r['家数日均']} 家，最高 {r['最高连板']} 板，"
                     f"梯队完整 {r['梯队完整天数']} 天）")
        L.append("")

    br = a["L3板块榜"]
    for label, rows in br.items():
        if rows:
            L.append(f"## L3 板块涨幅榜前 {len(rows)}（{label}，交叉验证）")
            L.append("　".join(
                f"{b['name']} {b['pct']:+.1f}%" for b in rows if b.get("pct") is not None))
            L.append("")

    if a.get("_note"):
        L.append(f"ℹ {a['_note']}")
    if a["errors"]:
        L.append("⚠ 抓取不完整：" + "；".join(a["errors"]))
    return "\n".join(L)
