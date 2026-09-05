#!/usr/bin/env python
"""波段账户命令行入口。

    # 录入（默认预览，加 --commit 落盘）
    buy  <股票> <价格> <数量> [日期] [--stop "计划"] [--reason "买入理由"]
    sell <股票> <价格> <数量> [日期] [--reason "卖出理由"]
    note <股票|market> "内容" [--type 交易计划] [--due 20260915]
    stop <股票> "计划" [--price 11.45] [--basis 黄线]

    # 查询
    show                持仓总览（含浮动盈亏，需行情）
    detail <股票>       单票全部交易 + 便签 + 止损沿革
    pending             待验证便签（复盘闭环）
    rm <记录id>         删除一条记录

用法:
    conda run --live-stream -n stock python -m portfolio.cli show
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from portfolio import position as pos
from portfolio import store

# 行情相关的导入放在函数内部：只查记录时不该被 pandas / sqlite 拖慢，
# 也让本 CLI 在数据库不可用时仍能录入与查询记录。


def resolve(name_or_code: str) -> tuple[str, str]:
    """把股票名或代码解析成 (6位标准码, 名称)。解析不出来直接退出。"""
    from datas.query_stock import get_stock_code_by_name, get_stock_info_by_code
    from tools.stock_tools import to_std_code

    try:
        code = to_std_code(name_or_code)
        info = get_stock_info_by_code(code)
        if not info.empty:
            name = str(info.iloc[0].get("name", "")) or code
            return code, name
    except Exception:
        pass

    code = get_stock_code_by_name(name_or_code)
    if code:
        info = get_stock_info_by_code(code)
        name = str(info.iloc[0].get("name", "")) if not info.empty else code
        return code, name

    sys.exit(f"✗ 无法解析「{name_or_code}」：股票池中查不到该名称或代码")


def last_close(code: str) -> Optional[tuple[str, float]]:
    """取最近收盘 (日期, 收盘价)，取不到返回 None。"""
    from datas.query_stock import query_latest_bars

    df = query_latest_bars(code, 1)
    if df is None or df.empty:
        return None
    row = df.iloc[-1]
    return str(row["date"])[:10], float(row["close"])


def _preview(kind: str, rec: dict, commit: bool) -> int:
    tag = "已写入" if commit else "[预览] 未写入"
    print(f"{tag} {kind}:")
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    if commit:
        store.append_record(kind, rec)
    else:
        print("\n确认无误后加 --commit 落盘。")
    return 0


def cmd_buy(args) -> int:
    code, name = resolve(args.stock)
    day = store.parse_date(args.date)

    trade = store.make_trade(
        code=code, name=name, side="buy", day=day,
        price=args.price, qty=args.qty, remark=args.remark,
    )

    lots_before = pos.build_lots().get(code)
    held = lots_before.qty if lots_before else 0
    print(f"{name}({code})  买入 {args.qty} 股 @ {args.price}  {day}")
    if held:
        print(f"  加仓：原持仓 {held} 股，均价 {lots_before.avg_cost:.3f}")
    if not args.stop:
        print("  ⚠ 未写止损计划。核心原则：每一笔交易都必须有止损计划，建议补 --stop")

    print()
    if args.commit:
        store.append_record("trade", trade)
        print(f"✓ 交易 {trade['id']}")
        if args.reason:
            note = store.make_note(
                text=args.reason, day=day, code=code,
                note_type="买入理由", related_trade_id=trade["id"], status="待验证",
                due=args.due,
            )
            store.append_record("note", note)
            print(f"✓ 便签 {note['id']}  {note['text']}")
        if args.stop:
            stop = store.make_stop(
                code=code, plan=args.stop, day=day,
                price=args.stop_price, basis=args.basis, related_trade_id=trade["id"],
            )
            store.append_record("stop", stop)
            print(f"✓ 止损 {stop['id']}  {stop['plan']}")

        lot = pos.build_lots()[code]
        print(f"\n持仓 {lot.qty} 股，加权成本 {lot.avg_cost:.3f}，投入 {lot.cost_total:,.2f}")
        return 0

    print(json.dumps(trade, ensure_ascii=False, indent=2))
    if args.reason:
        print(f"便签（买入理由）: {args.reason}")
    if args.stop:
        print(f"止损计划: {args.stop}" + (f"  价位 {args.stop_price}" if args.stop_price else ""))
    print("\n[预览] 未写入。确认无误后加 --commit 落盘。")
    return 0


def cmd_sell(args) -> int:
    code, name = resolve(args.stock)
    day = store.parse_date(args.date)

    lot = pos.build_lots().get(code)
    if not lot or not lot.is_open:
        print(f"⚠ {name}({code}) 当前无持仓记录，仍可录入（可能是补录历史）。")
    else:
        avg = lot.avg_cost
        gain = (args.price - avg) * min(args.qty, lot.qty)
        pct = (args.price / avg - 1) * 100
        clear = args.qty >= lot.qty
        print(f"{name}({code})  卖出 {args.qty} 股 @ {args.price}  {day}")
        print(f"  持仓 {lot.qty} 股，均价 {avg:.3f} → {'清仓' if clear else f'剩 {lot.qty - args.qty} 股'}")
        print(f"  本笔已实现盈亏 {gain:+,.2f}（{pct:+.2f}%）")
        if args.qty > lot.qty:
            print(f"  ⚠ 卖出数量超过持仓，将按 {lot.qty} 股计")

    trade = store.make_trade(
        code=code, name=name, side="sell", day=day,
        price=args.price, qty=args.qty, remark=args.remark,
    )
    print()
    if args.commit:
        store.append_record("trade", trade)
        print(f"✓ 交易 {trade['id']}")
        if args.reason:
            note = store.make_note(
                text=args.reason, day=day, code=code,
                note_type="卖出理由", related_trade_id=trade["id"],
            )
            store.append_record("note", note)
            print(f"✓ 便签 {note['id']}")
        after = pos.build_lots()[code]
        if after.is_open:
            print(f"\n剩余 {after.qty} 股，成本 {after.avg_cost:.3f}，累计已实现 {after.realized:+,.2f}")
        else:
            print(f"\n已清仓。该票累计已实现盈亏 {after.realized:+,.2f}")
            print("  提示：清仓归档（closed/<code>.md）尚未实现，见落地顺序")
        return 0

    print(json.dumps(trade, ensure_ascii=False, indent=2))
    print("\n[预览] 未写入。确认无误后加 --commit 落盘。")
    return 0


def cmd_note(args) -> int:
    code = None
    if args.stock and args.stock != "market":
        code, _ = resolve(args.stock)
    rec = store.make_note(
        text=args.text, day=args.date, code=code, note_type=args.type,
        related_trade_id=args.trade, status=args.status, due=args.due,
    )
    return _preview("note", rec, args.commit)


def cmd_stop(args) -> int:
    code, name = resolve(args.stock)
    prev = store.latest_stop(code)
    if prev:
        print(f"{name}({code}) 现行止损（{prev['date']}）: {prev['plan']}")
        if prev.get("price"):
            print(f"  价位 {prev['price']}")
        if args.price and prev.get("price") and float(args.price) < float(prev["price"]):
            print(f"  ⚠ 新价位 {args.price} 低于现行 {prev['price']} —— 止损下移，这通常是自欺的信号")
        print()
    rec = store.make_stop(
        code=code, plan=args.plan, day=args.date,
        price=args.price, basis=args.basis, related_trade_id=args.trade,
    )
    return _preview("stop", rec, args.commit)


def cmd_show(args) -> int:
    lots = pos.open_positions()
    if not lots:
        print("当前无持仓。")
        s = pos.summary()
        if s["已实现盈亏合计"]:
            print(f"历史已实现盈亏合计 {s['已实现盈亏合计']:+,.2f}（清仓 {s['清仓票数']} 票）")
        return 0

    rows, total_cost, total_mv = [], 0.0, 0.0
    for l in lots:
        quote = None if args.no_quote else last_close(l.code)
        price = quote[1] if quote else None
        mv = l.market_value(price) if price else 0.0
        total_cost += l.cost_total
        total_mv += mv if price else l.cost_total
        stop = store.latest_stop(l.code)
        rows.append((l, quote, price, mv, stop))

    print(f"{'代码':<8}{'名称':<9}{'股数':>7}{'成本':>9}{'现价':>9}{'浮动盈亏':>13}{'幅度':>9}  止损")
    for l, quote, price, mv, stop in rows:
        name = l.name[:6]
        pad = " " * (9 - sum(2 if ord(c) > 127 else 1 for c in name))
        if price:
            pnl = l.unrealized(price)
            pct = l.unrealized_pct(price)
            cells = f"{price:>9.2f}{pnl:>+13,.0f}{pct:>+8.2f}%"
        else:
            cells = f"{'n/a':>9}{'':>13}{'':>9}"
        sp = ""
        if stop:
            sp = f"{stop.get('price', '')} {stop.get('basis', '')}".strip() or stop["plan"][:16]
            if price and stop.get("price"):
                gap = (price / float(stop["price"]) - 1) * 100
                sp += f" ({gap:+.1f}%)"
        else:
            sp = "⚠ 未设"
        print(f"{l.code:<8}{name}{pad}{l.qty:>7}{l.avg_cost:>9.3f}{cells}  {sp}")

    print(f"\n持仓成本合计 {total_cost:,.2f}")
    if not args.no_quote:
        print(f"当前市值合计 {total_mv:,.2f}   浮动盈亏 {total_mv - total_cost:+,.2f}"
              f"（{(total_mv / total_cost - 1) * 100:+.2f}%）")
    s = pos.summary()
    if s["已实现盈亏合计"]:
        print(f"已实现盈亏合计 {s['已实现盈亏合计']:+,.2f}（清仓 {s['清仓票数']} 票）")
    for w in s["警告"]:
        print(f"⚠ {w}")

    pend = pos.pending_notes()
    if pend:
        print(f"\n待验证便签 {len(pend)} 条（pending 查看详情）")
    return 0


def cmd_detail(args) -> int:
    code, name = resolve(args.stock)
    lots = pos.build_lots()
    lot = lots.get(code)
    if not lot:
        print(f"{name}({code}) 无任何交易记录。")
        return 0

    print(f"# {name}({code})")
    if lot.is_open:
        quote = last_close(code)
        print(f"持仓 {lot.qty} 股，加权成本 {lot.avg_cost:.3f}，投入 {lot.cost_total:,.2f}")
        if quote:
            print(f"最近收盘 {quote[0]} {quote[1]:.2f}，浮动 {lot.unrealized(quote[1]):+,.2f}"
                  f"（{lot.unrealized_pct(quote[1]):+.2f}%）")
    else:
        print(f"已清仓（{', '.join(lot.closed_dates)}），累计已实现 {lot.realized:+,.2f}")

    print("\n## 交易")
    for t in pos.trades_of(code):
        side = "买入" if t["side"] == "buy" else "卖出"
        line = f"  {t['date']}  {side} {t['qty']:>6} 股 @ {t['price']:<8} [{t['id']}]"
        if t.get("remark"):
            line += f"  {t['remark']}"
        print(line)
        if t.get("snapshot"):
            print(f"      快照 {json.dumps(t['snapshot'], ensure_ascii=False)}")

    hist = store.stop_history(code)
    if hist:
        print("\n## 止损沿革")
        for s in hist:
            bits = [s["plan"]]
            if s.get("price"):
                bits.append(f"价位 {s['price']}")
            if s.get("basis"):
                bits.append(s["basis"])
            print(f"  {s['date']}  {'  '.join(bits)}  [{s['id']}]")
        if len(hist) > 1:
            print(f"  （共调整 {len(hist) - 1} 次）")

    notes = pos.notes_of(code)
    if notes:
        print("\n## 便签")
        for n in notes:
            head = f"  {n['date']}  [{n['type']}]"
            if n.get("status"):
                head += f" {n['status']}"
            if n.get("due"):
                head += f" 到期 {n['due']}"
            print(f"{head}  [{n['id']}]")
            print(f"      {n['text']}")
    return 0


def cmd_pending(args) -> int:
    rows = pos.pending_notes()
    if not rows:
        print("没有待验证便签。")
        return 0
    print(f"待验证便签 {len(rows)} 条：\n")
    for n in rows:
        code = n.get("code", "market")
        due = f" 到期 {n['due']}" if n.get("due") else " 无到期日"
        print(f"{n['date']}  {code}  [{n['type']}]{due}  [{n['id']}]")
        print(f"    {n['text']}")
    print("\n回看这些判断是否应验，验证后把 status 改成「已验证」（当前需手工编辑 JSONL）。")
    return 0


def cmd_rm(args) -> int:
    kind, rec = store.find_record(args.id)
    if not rec:
        sys.exit(f"✗ 找不到记录 {args.id}")
    print(f"将删除 {kind}:")
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    if kind == "trade":
        print("\n⚠ 删除交易会改变持仓与成本。")
    if not args.commit:
        print("\n[预览] 未删除。确认后加 --commit。")
        return 0
    store.delete_record(args.id)
    print(f"\n✓ 已删除 {args.id}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="portfolio.cli", description="波段账户交易记录 / 便签 / 止损计划"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("buy", help="录入买入")
    b.add_argument("stock", help="股票名或代码")
    b.add_argument("price", type=float)
    b.add_argument("qty", type=int)
    b.add_argument("date", nargs="?", help="默认今天")
    b.add_argument("--stop", help="止损计划描述（强烈建议填）")
    b.add_argument("--stop-price", type=float, help="止损价位（可选）")
    b.add_argument("--basis", choices=store.STOP_BASIS, help="止损依据线")
    b.add_argument("--reason", help="买入理由，存为便签")
    b.add_argument("--due", help="买入理由的复盘到期日")
    b.add_argument("--remark", help="交易备注")
    b.add_argument("--commit", action="store_true")
    b.set_defaults(func=cmd_buy)

    s = sub.add_parser("sell", help="录入卖出")
    s.add_argument("stock")
    s.add_argument("price", type=float)
    s.add_argument("qty", type=int)
    s.add_argument("date", nargs="?")
    s.add_argument("--reason", help="卖出理由，存为便签")
    s.add_argument("--remark")
    s.add_argument("--commit", action="store_true")
    s.set_defaults(func=cmd_sell)

    n = sub.add_parser("note", help="挂便签")
    n.add_argument("stock", help="股票名/代码，或 market 表示大盘级")
    n.add_argument("text")
    n.add_argument("--date")
    n.add_argument("--type", default="其它", choices=store.NOTE_TYPES)
    n.add_argument("--trade", help="关联的交易 id")
    n.add_argument("--status", choices=store.NOTE_STATUS)
    n.add_argument("--due")
    n.add_argument("--commit", action="store_true")
    n.set_defaults(func=cmd_note)

    st = sub.add_parser("stop", help="写/改止损计划（追加留痕）")
    st.add_argument("stock")
    st.add_argument("plan", help="计划描述，如「跌破黄线 11.45 且次日无法收回则离场」")
    st.add_argument("--price", type=float)
    st.add_argument("--basis", choices=store.STOP_BASIS)
    st.add_argument("--date")
    st.add_argument("--trade")
    st.add_argument("--commit", action="store_true")
    st.set_defaults(func=cmd_stop)

    sh = sub.add_parser("show", help="持仓总览")
    sh.add_argument("--no-quote", action="store_true", help="不查行情，只看成本")
    sh.set_defaults(func=cmd_show)

    d = sub.add_parser("detail", help="单票交易 / 便签 / 止损沿革")
    d.add_argument("stock")
    d.set_defaults(func=cmd_detail)

    p = sub.add_parser("pending", help="待验证便签")
    p.set_defaults(func=cmd_pending)

    r = sub.add_parser("rm", help="删除一条记录")
    r.add_argument("id")
    r.add_argument("--commit", action="store_true")
    r.set_defaults(func=cmd_rm)

    args = ap.parse_args()
    try:
        return args.func(args)
    except store.ValidationError as e:
        sys.exit(f"✗ {e}")


if __name__ == "__main__":
    sys.exit(main())
