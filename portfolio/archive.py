"""清仓归档。

某票持仓归零后，把它的全部交易、便签、止损沿革汇总成一份 Markdown 落到
`portfolio/<account>/closed/<code>.md`，供日后翻账复盘。

JSONL 是流水，翻一只票的完整经历要跨三个文件筛；归档是**为读而写的快照**，
一个文件看完一笔完整交易的始末。原始记录不动，归档可随时重生成。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from portfolio import position as pos
from portfolio import snapshot, store


def archive_path(code: str, account: str = "swing") -> Path:
    return store.account_dir(account) / "closed" / f"{code}.md"


def _round_trips(trades: list[dict]) -> list[dict]:
    """把流水切成一轮轮的「建仓→清仓」。

    同一只票可能做过多轮波段，各轮的成败要分开看——混在一起算总盈亏会把
    「一轮赚一轮亏」看成「小赚」，丢掉最该复盘的信息。
    """
    rounds: list[dict] = []
    qty = 0
    cost = 0.0
    cur: Optional[dict] = None

    for t in trades:
        price, n = float(t["price"]), int(t["qty"])
        if cur is None:
            cur = {"开始": t["date"], "交易": [], "买入额": 0.0, "卖出额": 0.0,
                   "买入股数": 0, "卖出股数": 0, "已实现": 0.0}
        cur["交易"].append(t)

        if t["side"] == "buy":
            qty += n
            cost += price * n
            cur["买入额"] += price * n
            cur["买入股数"] += n
        else:
            n = min(n, qty)  # 卖超按可卖数量算，position.py 同口径
            if n and qty:
                avg = cost / qty
                cur["已实现"] += (price - avg) * n
                cost -= avg * n
                qty -= n
            cur["卖出额"] += price * n
            cur["卖出股数"] += n
            if qty == 0:
                cost = 0.0
                cur["结束"] = t["date"]
                rounds.append(cur)
                cur = None

    if cur is not None:          # 还没清完，最后一轮是持仓中
        cur["结束"] = None
        rounds.append(cur)
    return rounds


def _hold_days(start: str, end: Optional[str]) -> Optional[int]:
    if not end:
        return None
    return (pd.Timestamp(end) - pd.Timestamp(start)).days


def build(code: str, account: str = "swing") -> Optional[str]:
    """生成归档 Markdown 文本。该票无交易记录时返回 None。"""
    trades = pos.trades_of(code, account)
    if not trades:
        return None

    lots = pos.build_lots(account)
    lot = lots.get(code)
    name = (lot.name if lot and lot.name else code)
    notes = pos.notes_of(code, account)
    stops = store.stop_history(code, account)
    rounds = _round_trips(trades)
    closed_rounds = [r for r in rounds if r.get("结束")]

    L: list[str] = [f"# {name}({code}) 交易归档", ""]

    still_open = lot.is_open if lot else False
    L.append(f"- 状态：{'仍在持仓' if still_open else '已清仓'}")
    L.append(f"- 交易笔数：{len(trades)}（买 {sum(1 for t in trades if t['side'] == 'buy')} / "
             f"卖 {sum(1 for t in trades if t['side'] == 'sell')}）")
    L.append(f"- 波段轮次：{len(rounds)}（已完成 {len(closed_rounds)}）")
    if lot:
        L.append(f"- 累计已实现盈亏：{lot.realized:+,.2f}")
        if still_open:
            L.append(f"- 当前持仓：{lot.qty} 股，加权成本 {lot.avg_cost:.3f}")
    L.append(f"- 首次买入：{trades[0]['date']}　最后交易：{trades[-1]['date']}")
    if lot and lot.warnings:
        for w in lot.warnings:
            L.append(f"- ⚠ {w}")
    L.append("")

    # ---- 逐轮明细
    for i, r in enumerate(rounds, 1):
        span = f"{r['开始']} ~ {r['结束'] or '持仓中'}"
        days = _hold_days(r["开始"], r["结束"])
        head = f"## 第 {i} 轮　{span}"
        if days is not None:
            head += f"（{days} 天）"
        L.append(head)
        L.append("")

        if r["结束"]:
            ret = (r["已实现"] / r["买入额"] * 100) if r["买入额"] else None
            line = f"- 结果：已实现 {r['已实现']:+,.2f}"
            if ret is not None:
                line += f"（投入 {r['买入额']:,.2f}，收益率 {ret:+.2f}%）"
            L.append(line)
        else:
            L.append(f"- 结果：未结束，已投入 {r['买入额']:,.2f}")
        L.append("")

        L.append("| 日期 | 方向 | 数量 | 价格 | 备注 | 记录 |")
        L.append("|---|---|---:|---:|---|---|")
        for t in r["交易"]:
            side = "买入" if t["side"] == "buy" else "卖出"
            L.append(f"| {t['date']} | {side} | {t['qty']} | {t['price']} | "
                     f"{t.get('remark', '') or ''} | `{t['id']}` |")
        L.append("")

        # 成交时的测量快照——落盘时算死的，不受后续数据修订影响
        snaps = [(t["date"], t["side"], t["snapshot"]) for t in r["交易"] if t.get("snapshot")]
        if snaps:
            L.append("<details><summary>成交时测量快照</summary>")
            L.append("")
            for day, side, sn in snaps:
                L.append(f"**{day} {'买入' if side == 'buy' else '卖出'}**")
                L.append("")
                L.append("```")
                L.append(snapshot.describe(sn))
                L.append("```")
                L.append("")
            L.append("</details>")
            L.append("")

    # ---- 便签：判断与复盘结论
    if notes:
        L.append("## 便签")
        L.append("")
        for n in notes:
            bits = [f"**{n['date']}**", f"[{n['type']}]"]
            if n.get("status"):
                bits.append(f"`{n['status']}`")
            if n.get("due"):
                bits.append(f"到期 {n['due']}")
            L.append(f"- {' '.join(bits)}　{n['text']}")
            if n.get("result"):
                L.append(f"  - 验证结论（{n.get('verified_at', '')}）：{n['result']}")
        L.append("")

    # ---- 止损沿革：调整次数是纪律的痕迹
    if stops:
        L.append("## 止损沿革")
        L.append("")
        for s in stops:
            bits = [s["plan"]]
            if s.get("price"):
                bits.append(f"价位 {s['price']}")
            if s.get("basis"):
                bits.append(s["basis"])
            L.append(f"- **{s['date']}**　{'　'.join(bits)}")
        if len(stops) > 1:
            moves = []
            for a, b in zip(stops, stops[1:]):
                if a.get("price") and b.get("price"):
                    d = float(b["price"]) - float(a["price"])
                    moves.append("上移" if d > 0 else ("下移" if d < 0 else "平移"))
            L.append("")
            L.append(f"- 共调整 {len(stops) - 1} 次"
                     + (f"（{'、'.join(moves)}）" if moves else "")
                     + "。止损下移是自欺的探针，复盘时要正面回答为什么移。")
        L.append("")
    else:
        L.append("## 止损沿革")
        L.append("")
        L.append("- ⚠ 全程未登记止损计划。核心原则：每一笔交易都必须有止损计划。")
        L.append("")

    L.append("---")
    L.append("")
    L.append("本文件由 `python -m portfolio.archive` 生成，可随时重跑覆盖；"
             "原始记录在 `trades.jsonl` / `notes.jsonl` / `stops.jsonl`。")
    return "\n".join(L)


def write(code: str, account: str = "swing", commit: bool = False) -> tuple[Optional[Path], str]:
    """生成并（可选）落盘。返回 (路径, 正文)。"""
    text = build(code, account)
    if text is None:
        return None, ""
    path = archive_path(code, account)
    if commit:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return path, text


def closed_codes(account: str = "swing") -> list[str]:
    """已清仓的票（曾有持仓、现在归零）。"""
    return [l.code for l in pos.closed_positions(account)]


def main() -> int:
    ap = argparse.ArgumentParser(description="清仓归档")
    ap.add_argument("code", nargs="?", help="股票代码；省略则归档全部已清仓的票")
    ap.add_argument("--account", default="swing")
    ap.add_argument("--commit", action="store_true", help="写入文件，否则只打印")
    args = ap.parse_args()

    codes = [args.code] if args.code else closed_codes(args.account)
    if not codes:
        print("没有已清仓的票。")
        return 0

    for code in codes:
        path, text = write(code, args.account, args.commit)
        if path is None:
            print(f"✗ {code} 无交易记录")
            continue
        if args.commit:
            print(f"✓ {path}")
        else:
            print(text)
            print(f"\n[预览] 未写入。确认无误后加 --commit 落盘到 {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
