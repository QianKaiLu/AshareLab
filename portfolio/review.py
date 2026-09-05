"""单笔交易的买点复盘（场景 A）。

在 `b1_review.py` 的静态体检之上叠三样它没有的东西：

    实际成交价 vs 理想买点价的偏离   —— 追高多少，容错空间被吃掉多少
    当时写下的买入理由与止损计划     —— 我当时怎么想的
    成交之后的走势                   —— 那个想法应验了没有

**诚实前提（设计决策 D8）**：本流程没有事前计划层，所以这是**事后复盘**，不满足
核心原则第二条的「事前依据」。它的价值在于积累「我的买点质量分布」，不是为已成交
的交易背书。测量值是今天算出来的，不等于买入时我真的看过这些数——报告里必须保持
这个区分。

用法:
    python -m portfolio.review 300314              # 复盘该票最近一笔买入
    python -m portfolio.review 300314 --trade T20260825-300314-1
    python -m portfolio.review 300314 --sim 20260825 12.29   # 无记录时试算
    python -m portfolio.review 300314 --json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from datas.query_stock import get_stock_info_by_code, query_bars_by_days
from portfolio import position as pos
from portfolio import snapshot, store

_B1_REVIEW_PATH = (
    Path(__file__).resolve().parent.parent
    / ".claude/skills/qk-stock-b1-review/scripts/b1_review.py"
)


def load_b1_review():
    """按路径加载 b1_review 模块。

    skill 目录名带横线不能当包名，只能走 importlib。复用而不复制——那份脚本是
    `/qk-stock-b1-review` 的测量基准，两处实现迟早会漂。
    """
    if not _B1_REVIEW_PATH.exists():
        raise FileNotFoundError(f"找不到 b1_review.py：{_B1_REVIEW_PATH}")
    spec = importlib.util.spec_from_file_location("b1_review_mod", _B1_REVIEW_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pick_trade(
    code: str, trade_id: Optional[str], account: str
) -> tuple[Optional[dict], Optional[str]]:
    """选出要复盘的那笔买入。默认取最近一笔。"""
    trades = [t for t in pos.trades_of(code, account) if t.get("side") == "buy"]
    if not trades:
        return None, f"{code} 没有买入记录"
    if trade_id:
        for t in trades:
            if t["id"] == trade_id:
                return t, None
        return None, f"找不到交易 {trade_id}（该票有 {len(trades)} 笔买入）"
    return trades[-1], None


def _stop_in_effect(stops: list[dict], day: str) -> Optional[dict]:
    """取 day 当天生效的止损——即 date ≤ day 的最后一条。

    不能拿最新止损去判定它写下之前的日子：那条止损当时还不存在，用它复盘等于
    掺入未来信息。实测踩过这个坑（8-31 被判触及 9-01 才写下的 11.84）。
    """
    eff = [s for s in stops if s.get("date", "") <= day and s.get("price")]
    return eff[-1] if eff else None


def _aftermath(d: pd.DataFrame, buy_date: str, buy_price: float,
               stops: Optional[list[dict]] = None,
               fallback_stop: Optional[float] = None) -> dict:
    """成交之后发生了什么。这是复盘区别于静态体检的核心。

    stops 是该票的止损沿革，逐日按当时生效的那条判定是否触及；没有记录时退回
    fallback_stop（脚本按规则算出的参考位），并在结果里标明用的是哪种。
    """
    after = d[d["date"] > pd.Timestamp(buy_date)]
    if after.empty:
        return {"交易日数": 0, "说明": "成交日之后还没有新的交易日数据"}

    high = float(after["high"].max())
    low = float(after["low"].min())
    close = float(after["close"].iloc[-1])
    hi_row = after.loc[after["high"].idxmax()]
    lo_row = after.loc[after["low"].idxmin()]

    out: dict[str, Any] = {
        "交易日数": int(len(after)),
        "截至": str(after["date"].iloc[-1])[:10],
        "最高": snapshot._num(high),
        "最高日": str(hi_row["date"])[:10],
        "最低": snapshot._num(low),
        "最低日": str(lo_row["date"])[:10],
        "现价": snapshot._num(close),
        "最大浮盈%": snapshot._num((high / buy_price - 1) * 100),
        "最大浮亏%": snapshot._num((low / buy_price - 1) * 100),
        "当前盈亏%": snapshot._num((close / buy_price - 1) * 100),
    }

    # 先到最高还是先到最低——决定了这笔是「拿住就赚」还是「一上来就套」
    out["先触"] = "最高" if hi_row["date"] <= lo_row["date"] else "最低"

    if stops:
        # 逐日用当天生效的止损判定，而不是拿最新那条回溯套用
        first_hit = None
        for n, (_, r) in enumerate(after.iterrows(), start=1):
            day = str(r["date"])[:10]
            eff = _stop_in_effect(stops, day)
            if not eff:
                continue
            if float(r["close"]) < float(eff["price"]):
                first_hit = {
                    "首次": day,
                    "第几个交易日": n,
                    "收盘": snapshot._num(float(r["close"])),
                    "止损价": snapshot._num(float(eff["price"])),
                    "当时生效的计划": eff["plan"],
                    "该计划写于": eff["date"],
                }
                break
        out["止损触及"] = first_hit
        out["止损判定依据"] = "按止损沿革逐日取当时生效的那条"
    elif fallback_stop:
        hit = after[after["close"] < float(fallback_stop)]
        out["止损触及"] = (
            {
                "首次": str(hit["date"].iloc[0])[:10],
                "第几个交易日": int(after.index.get_loc(hit.index[0])) + 1,
                "收盘": snapshot._num(float(hit["close"].iloc[0])),
                "止损价": snapshot._num(float(fallback_stop)),
            }
            if not hit.empty
            else None
        )
        out["止损判定依据"] = "无止损记录，用脚本按规则算出的参考位试算"

    out["逐日"] = [
        {
            "日期": str(r["date"])[:10],
            "收": snapshot._num(float(r["close"])),
            "涨跌%": snapshot._num(r.get("change_pct")),
            "距成本%": snapshot._num((float(r["close"]) / buy_price - 1) * 100),
            "J": snapshot._num(r.get("kdj_j")),
            "距BBI%": (
                snapshot._num((float(r["close"]) / float(r["bbi"]) - 1) * 100)
                if np.isfinite(r.get("bbi", np.nan)) and r.get("bbi")
                else None
            ),
        }
        for _, r in after.tail(20).iterrows()
    ]
    return out


def _deviation(buy_price: float, meas: dict) -> dict:
    """成交价与各参考位的距离。B1 是收盘信号，买在收盘之上多少直接吃掉容错空间。"""
    out: dict[str, Any] = {"买入价": snapshot._num(buy_price)}

    close = meas.get("均线结构", {}).get("收盘价")
    if close:
        out["当日收盘"] = close
        out["vs收盘%"] = snapshot._num((buy_price / float(close) - 1) * 100)

    stop = meas.get("止损", {})
    if stop.get("止损价"):
        sp = float(stop["止损价"])
        out["止损位"] = sp
        out["止损参考线"] = stop.get("建议参考线")
        out["单笔风险敞口%"] = snapshot._num((buy_price / sp - 1) * 100)

    fire_low = stop.get("点火首日低点")
    if fire_low:
        out["点火首日低点"] = fire_low
        out["距点火低点%"] = snapshot._num((buy_price / float(fire_low) - 1) * 100)

    rng = meas.get("洗盘形态", {}).get("点火后区间")
    if rng and len(rng) == 2 and rng[1] > rng[0]:
        out["买入价在点火区间位置"] = snapshot._num(
            (buy_price - rng[0]) / (rng[1] - rng[0]), 2
        )
    return out


def review_trade(
    code_or_name: str,
    trade_id: Optional[str] = None,
    account: str = "swing",
    sim: Optional[tuple[str, float]] = None,
    as_of: Optional[str] = None,
) -> dict:
    """复盘一笔买入。sim=(日期, 价格) 时不读记录，按假设成交试算。"""
    b1r = load_b1_review()
    code, resolve_note = b1r.resolve(code_or_name)
    if code is None:
        return {"error": resolve_note}

    info = get_stock_info_by_code(code)
    name = str(info.iloc[0]["name"]) if not info.empty else code

    if sim:
        buy_date, buy_price = store.parse_date(sim[0]), float(sim[1])
        trade = None
        qty = None
    else:
        trade, err = _pick_trade(code, trade_id, account)
        if err:
            return {"error": err + "。可用 --sim <日期> <价格> 试算，或先用 "
                                  "`python -m portfolio.cli buy ...` 录入"}
        buy_date, buy_price, qty = trade["date"], float(trade["price"]), trade["qty"]

    # 买点测量：一律以成交日为基准日，只用当天及之前的数据
    meas = b1r.review(code, buy_date.replace("-", ""))
    if "error" in meas:
        return {"error": f"买点测量失败：{meas['error']}"}

    out: dict[str, Any] = {
        "标的": {"code": code, "name": name,
                 "行业": str(info.iloc[0]["idn_name"]) if not info.empty else ""},
        "这笔交易": {
            "成交日": buy_date,
            "买入价": snapshot._num(buy_price),
            "数量": qty,
            "记录id": trade["id"] if trade else None,
            "模式": "试算（无成交记录）" if sim else "实际成交记录",
        },
        "买点测量": meas,
        "买入价偏离": _deviation(buy_price, meas),
    }

    if trade:
        lot = pos.build_lots(account).get(code)
        if lot:
            out["这笔交易"]["当前持仓"] = lot.qty
            out["这笔交易"]["加权成本"] = snapshot._num(lot.avg_cost, 3)
            if lot.realized:
                out["这笔交易"]["该票已实现"] = snapshot._num(lot.realized, 2)
        if trade.get("snapshot"):
            # 成交时存下的快照 vs 现在重算的测量：两者不一致说明数据被修订过
            out["成交时快照"] = trade["snapshot"]

        # 当时写下的想法
        notes = [n for n in pos.notes_of(code, account)
                 if n.get("related_trade_id") == trade["id"] or n["date"] == buy_date]
        if notes:
            out["当时的判断"] = [
                {"日期": n["date"], "类型": n["type"], "内容": n["text"],
                 "状态": n.get("status"), "到期": n.get("due"), "id": n["id"]}
                for n in notes
            ]
        stops = [s for s in store.stop_history(code, account) if s["date"] >= buy_date]
        if stops:
            out["止损沿革"] = [
                {"日期": s["date"], "计划": s["plan"], "价位": s.get("price"),
                 "依据": s.get("basis")}
                for s in stops
            ]

    # 事后走势
    df = query_bars_by_days(code, days=800, to_date=as_of)
    if df is not None and not df.empty:
        d = snapshot._prepare(df)
        # 有止损记录就按沿革逐日判定；没有则退回脚本算出的参考位试算
        hist = (
            [s for s in store.stop_history(code, account) if s.get("price")]
            if trade
            else []
        )
        out["事后走势"] = _aftermath(
            d, buy_date, buy_price,
            stops=hist or None,
            fallback_stop=meas.get("止损", {}).get("止损价"),
        )

    out["规则对照"] = {
        "B1硬筛命中": meas.get("策略判定", {}).get("hunt_b1命中"),
        "variant": meas.get("策略判定", {}).get("variant"),
        "口径说明": (
            "以上测量是复盘时算出来的，不代表买入当时我看过这些数。"
            "本流程没有事前计划记录（设计决策 D8），因此无法据此判定「规则内交易」——"
            "只能说这笔买入在事后测量上是否落在 B1 形态里。"
        ),
    }
    return out


def render(r: dict) -> str:
    if "error" in r:
        return f"❌ {r['error']}"

    b1r = load_b1_review()
    lines: list[str] = []
    s, t = r["标的"], r["这笔交易"]
    lines.append(f"# {s['name']}({s['code']}) 买点复盘  {s['行业']}")
    head = f"成交 {t['成交日']} @ {t['买入价']}"
    if t.get("数量"):
        head += f" × {t['数量']} 股"
    head += f"   [{t['模式']}]"
    lines.append(head)
    if t.get("当前持仓"):
        extra = f"当前持仓 {t['当前持仓']} 股，加权成本 {t['加权成本']}"
        if t.get("该票已实现"):
            extra += f"，该票已实现 {t['该票已实现']:+,.2f}"
        lines.append(extra)

    if r.get("当时的判断"):
        lines.append("\n## 当时的判断")
        for n in r["当时的判断"]:
            tag = f" [{n['状态']}]" if n.get("状态") else ""
            due = f" 到期{n['到期']}" if n.get("到期") else ""
            lines.append(f"  {n['日期']} [{n['类型']}]{tag}{due}  {n['内容']}")
    if r.get("止损沿革"):
        lines.append("\n## 止损沿革")
        for st in r["止损沿革"]:
            bits = [st["计划"]]
            if st.get("价位"):
                bits.append(f"价位 {st['价位']}")
            if st.get("依据"):
                bits.append(st["依据"])
            lines.append(f"  {st['日期']}  {'  '.join(bits)}")
        if len(r["止损沿革"]) > 1:
            lines.append(f"  （共调整 {len(r['止损沿革']) - 1} 次，止损下移是自欺的探针）")

    lines.append("\n## 买入价偏离")
    dv = r["买入价偏离"]
    if dv.get("vs收盘%") is not None:
        lines.append(f"  买入 {dv['买入价']} vs 当日收盘 {dv['当日收盘']}："
                     f"{dv['vs收盘%']:+.2f}%")
    if dv.get("单笔风险敞口%") is not None:
        lines.append(f"  距止损位 {dv['止损位']}（{dv.get('止损参考线')}）："
                     f"{dv['单笔风险敞口%']:+.2f}%  ← 单笔最大风险敞口")
    if dv.get("距点火低点%") is not None:
        lines.append(f"  距点火首日低点 {dv['点火首日低点']}：{dv['距点火低点%']:+.2f}%")
    if dv.get("买入价在点火区间位置") is not None:
        lines.append(f"  买入价在点火区间位置：{dv['买入价在点火区间位置']}")

    if r.get("事后走势"):
        a = r["事后走势"]
        lines.append(f"\n## 事后走势（{a['交易日数']} 个交易日"
                     + (f"，截至 {a['截至']}" if a.get("截至") else "") + "）")
        if a["交易日数"] == 0:
            lines.append(f"  {a.get('说明', '')}")
        else:
            lines.append(f"  最高 {a['最高']}（{a['最高日']}）  最低 {a['最低']}（{a['最低日']}）"
                         f"  现价 {a['现价']}")
            lines.append(f"  最大浮盈 {a['最大浮盈%']:+.2f}%  最大浮亏 {a['最大浮亏%']:+.2f}%"
                         f"  当前 {a['当前盈亏%']:+.2f}%  先触{a['先触']}")
            hit = a.get("止损触及")
            basis = a.get("止损判定依据")
            if hit:
                lines.append(f"  ⚠ 止损触及：{hit['首次']}（第 {hit['第几个交易日']} 个交易日）"
                             f"收 {hit['收盘']}，止损价 {hit['止损价']}")
                if hit.get("当时生效的计划"):
                    lines.append(f"    当时生效：{hit['当时生效的计划']}"
                                 f"（写于 {hit['该计划写于']}）")
            elif "止损触及" in a:
                lines.append("  止损未被触及")
            if basis:
                lines.append(f"    判定依据：{basis}")
            lines.append(f"\n  {'日期':<12}{'收':>8}{'涨跌%':>8}{'距成本%':>9}{'J':>8}{'距BBI%':>8}")
            for row in a["逐日"]:
                lines.append(
                    f"  {row['日期']:<12}{row['收']:>8.2f}"
                    f"{(row['涨跌%'] or 0):>8.2f}{(row['距成本%'] or 0):>9.2f}"
                    f"{(row['J'] if row['J'] is not None else 0):>8.1f}"
                    f"{(row['距BBI%'] if row['距BBI%'] is not None else 0):>8.2f}"
                )

    lines.append("\n## 买点当时的测量")
    lines.append(b1r.render(r["买点测量"]))

    rc = r["规则对照"]
    lines.append(f"\n## 规则对照")
    lines.append(f"  B1 硬筛命中：{rc['B1硬筛命中']}"
                 + (f"  variant={rc['variant']}" if rc.get("variant") else ""))
    lines.append(f"  {rc['口径说明']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="单笔买入的买点复盘")
    ap.add_argument("stock", help="股票名或代码")
    ap.add_argument("--trade", help="指定交易 id，默认取该票最近一笔买入")
    ap.add_argument("--sim", nargs=2, metavar=("日期", "价格"),
                    help="无成交记录时按假设成交试算")
    ap.add_argument("--date", help="事后走势截至哪天，默认到最新")
    ap.add_argument("--account", default="swing")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    sim = (args.sim[0], float(args.sim[1])) if args.sim else None
    try:
        r = review_trade(args.stock, args.trade, args.account, sim, args.date)
    except store.ValidationError as e:
        sys.exit(f"✗ {e}")
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        print(render(r))
    return 0 if "error" not in r else 1


if __name__ == "__main__":
    sys.exit(main())
