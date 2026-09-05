"""持仓每日监控的客观测量。

只测不判：这里把「止损是否触及、卖点信号是否出现、指标处在什么位置」摆成结构化
数据，「今天该怎么办」由 skill 层的 AI 结合交易系统、便签历史与盘面细节研判。

两套线各管一段（需求文档 D4）：
    买点 / 止损 → 黄线、白线（zxdkx）
    卖点 / 离场 → BBI

用法:
    python -m portfolio.monitor                      # 监控当前持仓
    python -m portfolio.monitor --codes 300314,002594  # 指定代码（自选股/试跑）
    python -m portfolio.monitor --json
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Optional

import numpy as np
import pandas as pd

from datas.query_stock import get_stock_info_by_code, query_bars_by_days
from hunter.distribution_signals import scan_signals, summarize
from portfolio import position as pos
from portfolio import snapshot, store

BARS = 500

# 「中大阳线」的起判门槛：实体占当日涨跌幅上限的比例（body_norm）。
# 0.4 即 10% 涨跌幅的板块里实体 4% 以上。这是起点参照不是硬规则——
# 精确口径按设计决策 D12 推后，最终由 AI 结合盘面判断。
MID_YANG_BODY_NORM = 0.4
YANG_LOOKBACK = 5        # 找「BBI 上两根中大阳」的回看窗口
VOL_SPIKE_RATIO = 2.0    # 相对 5 日均量的放量异动倍数
NEAR_STOP_PCT = 3.0      # 距止损位这个百分比内算「逼近」


def _streak_below(d: pd.DataFrame, col: str) -> int:
    """收盘连续低于某条线的天数（含当日）。当日在线上则为 0。"""
    n = 0
    for i in range(len(d) - 1, -1, -1):
        line = d.iloc[i].get(col)
        if line is None or not np.isfinite(line):
            break
        if float(d.iloc[i]["close"]) < float(line):
            n += 1
        else:
            break
    return n


def _bbi_signals(d: pd.DataFrame) -> dict:
    """B1 的卖点两条：连续两日收盘跌破 BBI 清仓；BBI 上两根中大阳线减仓。

    BBI 与黄线是**两条不同的线**，不可互相替代：
        BBI    = MA(3,6,12,24) 均值，快线，管卖点 / 离场
        黄线   = MA(14,28,57,114) 均值，慢线，管买点 / 止损 / 趋势
    规则原文（B1.md）对 BBI 离场没有任何黄线前置条件，这里照原文报「条件成立」，
    不拿黄线去否决它。

    但同一天两条线可以给出方向相反的信息（戴维医疊 2026-09-04：跌破 BBI 十日，
    却仍在黄线上 +0.70%），因为 B1 买点本身是缩量回踩，回踩时价格常常已在快线
    之下。这类冲突交给 AI 结合持仓阶段权衡——「止盈放飞后的离场」与「刚买入后的
    回踩」用同一条 BBI 规则，含义并不一样。脚本只负责把两个事实分别摆清楚。
    """
    out: dict[str, Any] = {}
    below = _streak_below(d, "bbi")
    out["bbi_below_days"] = below

    last = d.iloc[-1]
    close = float(last["close"])
    bbi = last.get("bbi")
    yellow = last.get("z_yellow")
    if bbi is not None and np.isfinite(bbi):
        out["close_vs_bbi_pct"] = snapshot._num((close / float(bbi) - 1) * 100)

    if below >= 2:
        out["exit_signal"] = f"连续 {below} 日收盘跌破 BBI —— B1 离场条件成立（规则原文）"
        # 黄线的状态单独作为并列事实给出，供 AI 权衡，不改变上面的结论
        if yellow is not None and np.isfinite(yellow) and close >= float(yellow):
            out["exit_conflict"] = (
                f"但收盘仍在黄线之上（{(close / float(yellow) - 1) * 100:+.2f}%）："
                "BBI（快线）已失守而黄线（慢线）未破，需按持仓阶段判断这是回踩还是走坏"
            )
    elif below == 1:
        out["exit_watch"] = "首日收盘跌破 BBI —— 次日若再收在 BBI 下则离场条件成立"

    # 止盈放飞：BBI 之上出现两根中大阳线
    win = d.tail(YANG_LOOKBACK)
    yang = []
    for _, r in win.iterrows():
        body_norm = r.get("body_norm")
        if body_norm is None or not np.isfinite(body_norm):
            continue
        above_bbi = np.isfinite(r.get("bbi", np.nan)) and float(r["close"]) > float(r["bbi"])
        if body_norm >= MID_YANG_BODY_NORM and above_bbi:
            yang.append({
                "date": str(r["date"])[:10],
                "body_norm": snapshot._num(body_norm, 2),
                "change_pct": snapshot._num(r.get("change_pct")),
            })
    if yang:
        out["mid_yang_above_bbi"] = yang
        if len(yang) >= 2:
            out["reduce_signal"] = (
                f"BBI 上近 {YANG_LOOKBACK} 日已有 {len(yang)} 根中大阳线"
                f"（实体归一 {', '.join(str(y['body_norm']) for y in yang)}）—— 止盈放飞条件成立"
            )
    return out


def _line_signals(d: pd.DataFrame) -> dict:
    """双线系统的趋势判定：跌破白线短期走坏，跌破黄线次日不收回中期走坏。"""
    out: dict[str, Any] = {}
    white_below = _streak_below(d, "z_white")
    yellow_below = _streak_below(d, "z_yellow")
    out["white_below_days"] = white_below
    out["yellow_below_days"] = yellow_below

    if yellow_below == 1:
        out["line_warning"] = "今日收盘跌破黄线 —— 按双线系统留一两根 K 观察能否收回"
    elif yellow_below >= 2:
        out["line_warning"] = f"连续 {yellow_below} 日收在黄线下 —— 中期趋势走坏，非震仓"
    elif white_below >= 1:
        out["line_warning"] = f"连续 {white_below} 日收在白线下 —— 短期趋势转弱，黄线仍在下方托底"

    # 白线死叉黄线是最后离场时机
    if len(d) >= 2:
        a, b = d.iloc[-2], d.iloc[-1]
        w0, y0 = a.get("z_white"), a.get("z_yellow")
        w1, y1 = b.get("z_white"), b.get("z_yellow")
        if all(v is not None and np.isfinite(v) for v in (w0, y0, w1, y1)):
            if w0 >= y0 and w1 < y1:
                out["cross_warning"] = "白线今日下穿黄线 —— 双线系统的最后离场时机"
            elif w1 > y1 and (w1 / y1 - 1) < 0.005:
                out["cross_warning"] = "白黄线接近粘合，将死未死 —— 方向待定"
    return out


def _kdj_state(d: pd.DataFrame) -> dict:
    """J 值位置与方向。走平/翘头是买点确认信号，钝化要靠趋势另判（kdj.md）。"""
    out: dict[str, Any] = {}
    j = d["kdj_j"].tail(4).to_numpy(dtype=float)
    if len(j) < 2 or not np.isfinite(j[-1]):
        return out
    out["kdj_j"] = snapshot._num(j[-1])
    out["kdj_j_prev"] = snapshot._num(j[-2])
    delta = j[-1] - j[-2]
    if abs(delta) < 2:
        direction = "走平"
    elif delta > 0:
        direction = "翘头上行"
    else:
        direction = "下行"
    out["kdj_direction"] = direction

    zone = "超卖(≤15)" if j[-1] <= 15 else ("超买(≥85)" if j[-1] >= 85 else "中位")
    out["kdj_zone"] = zone
    if j[-1] >= 85:
        # 强趋势下 J 会长期钝化，不能单独当卖出理由
        out["kdj_note"] = "J 在超买区，强趋势下可能钝化，需配合双线与量能判断"
    if "kdj_j_weekly" in d.columns and np.isfinite(d["kdj_j_weekly"].iloc[-1]):
        out["kdj_j_weekly"] = snapshot._num(d["kdj_j_weekly"].iloc[-1])
    return out


def _volume_state(d: pd.DataFrame) -> dict:
    out: dict[str, Any] = {}
    last = d.iloc[-1]
    vma5 = last.get("volume_ma_5")
    if vma5 and np.isfinite(vma5) and vma5 > 0:
        ratio = float(last["volume"]) / float(vma5)
        out["vol_ratio"] = snapshot._num(ratio)
        if ratio >= VOL_SPIKE_RATIO:
            body = last.get("body_norm")
            kind = "放量" + ("上攻" if float(last["close"]) > float(last["open"]) else "下跌")
            out["vol_alert"] = f"{kind}：量为 5 日均量 {ratio:.1f} 倍" + (
                f"，实体归一 {snapshot._num(body, 2)}" if body is not None and np.isfinite(body) else ""
            )
    vol60 = d["volume"].tail(60)
    if len(vol60) >= 20:
        out["vol_pct_in_60d"] = snapshot._num(
            float((vol60 < float(last["volume"])).sum()) / len(vol60), 2
        )
    return out


def _stop_check(code: str, close: float, d: pd.DataFrame, account: str = "swing") -> dict:
    """对照我当初写下的止损计划——不是每天重算一个新位置（那等于没有止损）。"""
    stop = store.latest_stop(code, account)
    if not stop:
        return {"stop_plan": None, "stop_warning": "未登记止损计划"}

    out: dict[str, Any] = {
        "stop_plan": stop["plan"],
        "stop_date": stop["date"],
        "stop_basis": stop.get("basis"),
    }
    hist = store.stop_history(code)
    if len(hist) > 1:
        out["stop_adjust_count"] = len(hist) - 1

    price = stop.get("price")
    if price:
        price = float(price)
        out["stop_price"] = price
        gap = (close / price - 1) * 100
        out["stop_gap_pct"] = snapshot._num(gap)
        if close < price:
            # 触及后要看是否已连续多日收在下方
            days = 0
            for i in range(len(d) - 1, -1, -1):
                if float(d.iloc[i]["close"]) < price:
                    days += 1
                else:
                    break
            out["stop_hit"] = True
            out["stop_hit_days"] = days
            out["stop_warning"] = (
                f"已跌破止损位 {price}（连续 {days} 日）—— 按计划应执行：{stop['plan']}"
            )
        elif gap <= NEAR_STOP_PCT:
            out["stop_warning"] = f"距止损位 {price} 仅 {gap:+.2f}%，逼近"
    else:
        out["stop_warning"] = "止损计划无明确价位，需人工按计划描述判断"
    return out


def _distribution(df: pd.DataFrame, code: str, name: str) -> dict:
    """主力出货识别（S1~S5）。复用 hunter/distribution_signals，不重写。"""
    try:
        signals = scan_signals(df, code=code, name=name)
        summ = summarize(signals, df)
    except Exception as e:
        return {"distribution_error": str(e)}
    if not summ:
        return {"distribution": None}
    out = {
        "distribution": {
            "verdict": summ["verdict"],
            "tier": summ["tier"],
            "newest_age": summ["newest_age"],
            "kinds": summ["kinds"],
            "composite": summ["composite"],
            "invalidated": summ["invalidated"],
            "signals": [
                {"date": s.date, "kind": s.kind, "grade": s.grade, "age": s.age}
                for s in summ["signals"]
            ],
        }
    }
    return out


def _notes_context(code: str, limit: int = 4, account: str = "swing") -> dict:
    """便签历史——日报的核心价值在这：我之前的判断今天应验了没有。"""
    notes = pos.notes_of(code, account)
    if not notes:
        return {"notes_recent": [], "notes_pending": []}
    pending = [n for n in notes if n.get("status") == "待验证"]
    return {
        "notes_recent": [
            {"date": n["date"], "type": n["type"], "text": n["text"],
             "status": n.get("status"), "due": n.get("due")}
            for n in notes[-limit:]
        ],
        "notes_pending": [
            {"date": n["date"], "text": n["text"], "due": n.get("due"), "id": n["id"]}
            for n in pending
        ],
    }


def _urgency(item: dict) -> tuple[str, list[str]]:
    """机械判定的紧急度，供 AI 作为起点（SKILL.md 允许重新权衡）。

    只看能客观框死的条件，形态与情境类判断留给 AI。
    """
    triggers: list[str] = []
    if item.get("stop_hit"):
        triggers.append("止损已触及")
    # 只认「黄线之下」的 BBI 跌破（见 _bbi_signals）；黄线之上的走 exit_watch
    if item.get("exit_signal"):
        triggers.append(item["exit_signal"])
    dist = item.get("distribution")
    if dist and dist["tier"] == "高危" and not dist["invalidated"]:
        triggers.append(f"出货信号 {dist['verdict']}（{'/'.join(dist['kinds'])}）")
    if item.get("cross_warning", "").startswith("白线今日下穿"):
        triggers.append("白线下穿黄线")
    if triggers:
        return "需操作", triggers

    watch: list[str] = []
    if item.get("stop_warning") and not item.get("stop_hit"):
        # 「未登记止损」只对真实持仓算问题（核心原则），看盘模式不提
        if item.get("stop_plan") or item.get("qty"):
            watch.append(item["stop_warning"])
    if item.get("exit_watch"):
        watch.append(item["exit_watch"])
    if item.get("reduce_signal"):
        watch.append("止盈放飞条件成立")
    if item.get("line_warning"):
        watch.append(item["line_warning"])
    if item.get("vol_alert"):
        watch.append(item["vol_alert"])
    if dist and dist["tier"] == "观察" and not dist["invalidated"]:
        watch.append(f"出货信号（{dist['newest_age']} 日前，{dist['verdict']}）")
    if item.get("notes_pending"):
        watch.append(f"{len(item['notes_pending'])} 条便签待验证")
    if watch:
        return "需观察", watch
    return "无事", []


def monitor_one(
    code: str,
    lot: Optional[pos.Lot] = None,
    as_of: Optional[str] = None,
    account: str = "swing",
) -> dict:
    """测量单只票。lot 为 None 时按「只看盘不算盈亏」处理（自选股/试跑）。"""
    info = get_stock_info_by_code(code)
    name = str(info.iloc[0]["name"]) if not info.empty else code

    df = query_bars_by_days(code=code, days=BARS, to_date=as_of)
    if df is None or df.empty:
        return {"code": code, "name": name, "error": "无行情数据"}
    if len(df) < 60:
        return {"code": code, "name": name, "error": f"仅 {len(df)} 根 K 线，不足以测量"}

    d = snapshot._prepare(df)
    # 出货识别用的归一化实体（body_norm）需要 price_limit，按板块/日期取涨跌幅上限
    from indicators.price_limit import add_price_limit_to_dataframe
    add_price_limit_to_dataframe(d, code=code, name=name, inplace=True)

    last = d.iloc[-1]
    close = float(last["close"])
    item: dict[str, Any] = {
        "code": code,
        "name": name,
        "date": str(last["date"])[:10],
        "close": snapshot._num(close),
        "change_pct": snapshot._num(last.get("change_pct")),
        "z_white": snapshot._num(last.get("z_white")),
        "z_yellow": snapshot._num(last.get("z_yellow")),
        "bbi": snapshot._num(last.get("bbi")),
        "line_position": snapshot._line_position(
            close, snapshot._num(last.get("z_white")), snapshot._num(last.get("z_yellow"))
        ),
    }

    if lot is not None:
        item.update({
            "qty": lot.qty,
            "avg_cost": snapshot._num(lot.avg_cost, 3),
            "unrealized": snapshot._num(lot.unrealized(close), 2),
            "unrealized_pct": snapshot._num(lot.unrealized_pct(close)),
            "first_buy": lot.first_date,
            "realized": snapshot._num(lot.realized, 2) if lot.realized else None,
        })
        # 持仓期内的最高收盘，看回吐了多少浮盈
        held = d[d["date"] >= pd.Timestamp(lot.first_date)]
        if not held.empty:
            peak = float(held["close"].max())
            item["peak_close_since_buy"] = snapshot._num(peak)
            item["giveback_from_peak_pct"] = snapshot._num((close / peak - 1) * 100)

    item.update(_kdj_state(d))
    item.update(snapshot._macd_state(d))
    item.update(_line_signals(d))
    item.update(_bbi_signals(d))
    item.update(_volume_state(d))
    item.update(_stop_check(code, close, d, account))
    item.update(_distribution(df, code, name))
    item.update(_notes_context(code, account=account))

    urgency, triggers = _urgency(item)
    item["urgency"] = urgency
    item["triggers"] = triggers
    return item


def monitor_all(
    account: str = "swing",
    as_of: Optional[str] = None,
    codes: Optional[list[str]] = None,
) -> dict:
    """监控全部持仓（或指定代码）。"""
    if codes:
        items = [monitor_one(c, None, as_of, account) for c in codes]
        lots = []
    else:
        lots = pos.open_positions(account, to_date=as_of)
        items = [monitor_one(l.code, l, as_of, account) for l in lots]

    order = {"需操作": 0, "需观察": 1, "无事": 2}
    items.sort(key=lambda i: (order.get(i.get("urgency", "无事"), 3), i.get("code", "")))

    report: dict[str, Any] = {
        "as_of": items[0]["date"] if items and items[0].get("date") else as_of,
        "account": account,
        "watch_only": bool(codes),
        "count": len(items),
        "items": items,
    }
    if lots:
        total_cost = sum(l.cost_total for l in lots)
        total_mv = sum(
            (i.get("close") or 0) * (i.get("qty") or 0) for i in items if not i.get("error")
        )
        report["总成本"] = round(total_cost, 2)
        report["总市值"] = round(total_mv, 2)
        if total_cost:
            report["浮动盈亏"] = round(total_mv - total_cost, 2)
            report["浮动幅度"] = round((total_mv / total_cost - 1) * 100, 2)
        s = pos.summary(account, to_date=as_of)
        report["已实现盈亏合计"] = s["已实现盈亏合计"]

    pend = pos.pending_notes(account)
    if pend:
        report["待验证便签"] = [
            {"date": n["date"], "code": n.get("code", "market"), "text": n["text"],
             "due": n.get("due"), "id": n["id"]}
            for n in pend
        ]
    return report


def render(report: dict) -> str:
    """排成人读的报告。AI 在此基础上做定性研判，不要直接把这个当最终日报交付。"""
    lines: list[str] = []
    head = f"# 持仓监控  {report.get('as_of') or '?'}"
    if report.get("watch_only"):
        head += "（指定代码，非实际持仓）"
    lines.append(head)

    if report.get("总成本"):
        lines.append(
            f"持仓 {report['count']} 只  成本 {report['总成本']:,.2f}  "
            f"市值 {report['总市值']:,.2f}  浮动 {report.get('浮动盈亏', 0):+,.2f}"
            f"（{report.get('浮动幅度', 0):+.2f}%）"
        )
        if report.get("已实现盈亏合计"):
            lines.append(f"已实现盈亏合计 {report['已实现盈亏合计']:+,.2f}")
    elif report["count"]:
        lines.append(f"共 {report['count']} 只")

    if not report["count"]:
        lines.append("\n当前无持仓。用 `python -m portfolio.cli buy ...` 录入，"
                     "或加 --codes 指定代码试跑。")
        return "\n".join(lines)

    for bucket in ("需操作", "需观察", "无事"):
        group = [i for i in report["items"] if i.get("urgency") == bucket]
        errs = [i for i in report["items"] if i.get("error")]
        if bucket == "无事":
            group = [i for i in group if not i.get("error")]
        if not group:
            continue
        lines.append(f"\n## {bucket}（{len(group)} 只）")

        for it in group:
            if it.get("error"):
                lines.append(f"  {it['code']} {it['name']} — {it['error']}")
                continue
            head = f"\n### {it['code']} {it['name']}  收 {it['close']}（{it.get('change_pct', 0):+.2f}%）"
            if it.get("qty"):
                head += (f"  持 {it['qty']} 股  成本 {it['avg_cost']}  "
                         f"浮动 {it.get('unrealized_pct', 0):+.2f}%")
            lines.append(head)
            if it.get("triggers"):
                lines.append("  触发：" + "；".join(it["triggers"]))

            if it.get("notes_recent"):
                lines.append("  便签历史（跟踪对照用）：")
                for n in it["notes_recent"]:
                    tag = f" [{n['status']}]" if n.get("status") else ""
                    due = f" 到期{n['due']}" if n.get("due") else ""
                    lines.append(f"    {n['date']} [{n['type']}]{tag}{due} {n['text']}")

            lines.append(
                f"  线位：白 {it.get('z_white')} / 黄 {it.get('z_yellow')} / "
                f"BBI {it.get('bbi')}  {it.get('line_position') or ''}"
                + (f"  距 BBI {it['close_vs_bbi_pct']:+.2f}%" if it.get("close_vs_bbi_pct") is not None else "")
            )
            lines.append(
                f"  KDJ：J {it.get('kdj_j')} {it.get('kdj_direction', '')} {it.get('kdj_zone', '')}"
                + (f"  周J {it['kdj_j_weekly']}" if it.get("kdj_j_weekly") is not None else "")
            )
            if it.get("macd_state"):
                extra = f"  {it['macd_cross']}" if it.get("macd_cross") else ""
                lines.append(f"  MACD：{it['macd_state']}{extra}")
            vol = f"  量能：量比 {it.get('vol_ratio')}"
            if it.get("vol_pct_in_60d") is not None:
                vol += f"  60日分位 {it['vol_pct_in_60d']}"
            lines.append(vol)
            if it.get("vol_alert"):
                lines.append(f"    ⚠ {it['vol_alert']}")

            stop_line = f"  止损：{it.get('stop_plan') or '未登记'}"
            if it.get("stop_price"):
                stop_line += f"  位 {it['stop_price']}  距现价 {it.get('stop_gap_pct', 0):+.2f}%"
            if it.get("stop_adjust_count"):
                stop_line += f"  （已调整 {it['stop_adjust_count']} 次）"
            lines.append(stop_line)
            if it.get("stop_warning"):
                lines.append(f"    ⚠ {it['stop_warning']}")

            for key in ("exit_signal", "exit_watch", "reduce_signal",
                        "line_warning", "cross_warning"):
                if it.get(key):
                    lines.append(f"  信号：{it[key]}")
            if it.get("exit_conflict"):
                lines.append(f"    ↳ {it['exit_conflict']}")
            if it.get("mid_yang_above_bbi"):
                ys = ", ".join(f"{y['date']}({y['body_norm']})" for y in it["mid_yang_above_bbi"])
                lines.append(f"    BBI 上中大阳：{ys}")

            dist = it.get("distribution")
            if dist:
                tag = "（已被换庄失效）" if dist["invalidated"] else ""
                lines.append(
                    f"  出货：{dist['tier']} / {dist['verdict']}  "
                    f"{'/'.join(dist['kinds'])}  最近 {dist['newest_age']} 日前{tag}"
                    + ("  复合头部" if dist["composite"] else "")
                )
            if it.get("giveback_from_peak_pct") is not None:
                lines.append(
                    f"  持仓期高点 {it['peak_close_since_buy']}，"
                    f"现价回吐 {it['giveback_from_peak_pct']:+.2f}%"
                )

    if report.get("待验证便签"):
        lines.append(f"\n## 待验证便签（{len(report['待验证便签'])} 条）")
        for n in report["待验证便签"]:
            due = f" 到期 {n['due']}" if n.get("due") else ""
            lines.append(f"  {n['date']} {n['code']}{due}  {n['text']}  [{n['id']}]")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="持仓每日监控测量")
    ap.add_argument("--codes", help="逗号分隔的代码，替代实际持仓（自选股/试跑）")
    ap.add_argument("--date", help="评估日，默认库内最新交易日")
    ap.add_argument("--account", default="swing")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    codes = [c.strip() for c in args.codes.split(",")] if args.codes else None
    report = monitor_all(account=args.account, as_of=args.date, codes=codes)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
