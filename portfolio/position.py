"""持仓与盈亏计算。

持仓状态**不落盘**，每次从 trades.jsonl 现算——避免「记录」与「状态」两份真相
互相打架（设计决策 D3）。成本按加权平均：

    买入：qty += q,  cost += price * q
    卖出：先按当前均价结出已实现盈亏，再 qty -= q，cost 按剩余比例等比缩减

不含手续费（D15），所以盈亏是毛额。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from portfolio.store import ValidationError, read_records


@dataclass
class Lot:
    """单只票的持仓状态与累计盈亏。"""

    code: str
    name: str = ""
    qty: int = 0
    cost_total: float = 0.0        # 当前持仓对应的累计成本
    realized: float = 0.0          # 已实现盈亏（毛额）
    buy_count: int = 0
    sell_count: int = 0
    first_date: str = ""
    last_date: str = ""
    closed_dates: list[str] = field(default_factory=list)  # 每次清零的日期
    warnings: list[str] = field(default_factory=list)

    @property
    def avg_cost(self) -> Optional[float]:
        return self.cost_total / self.qty if self.qty else None

    @property
    def is_open(self) -> bool:
        return self.qty > 0

    def market_value(self, price: float) -> float:
        return price * self.qty

    def unrealized(self, price: float) -> float:
        return price * self.qty - self.cost_total

    def unrealized_pct(self, price: float) -> Optional[float]:
        if not self.qty or self.cost_total <= 0:
            return None
        return (price * self.qty - self.cost_total) / self.cost_total * 100


def build_lots(account: str = "swing", to_date: Optional[str] = None) -> dict[str, Lot]:
    """回放全部交易，得到每票的持仓与盈亏。

    to_date 用于「看某天收盘后的持仓」，回测与历史复盘会用到。
    卖出超过持仓不抛错——记 warning 并按可卖数量处理，免得一条录错的记录
    让整个日报跑不起来。
    """
    trades = read_records("trade", account)
    lots: dict[str, Lot] = {}

    for t in trades:
        day = t.get("date", "")
        if to_date and day > to_date:
            continue

        code = t.get("code")
        if not code:
            continue
        lot = lots.setdefault(code, Lot(code=code, name=t.get("name", "")))
        if t.get("name"):
            lot.name = t["name"]
        if not lot.first_date:
            lot.first_date = day
        lot.last_date = day

        side = t.get("side")
        price = float(t.get("price", 0))
        qty = int(t.get("qty", 0))

        if side == "buy":
            lot.qty += qty
            lot.cost_total += price * qty
            lot.buy_count += 1
        elif side == "sell":
            if qty > lot.qty:
                lot.warnings.append(
                    f"{day} 卖出 {qty} 股超过当时持仓 {lot.qty} 股（记录 {t.get('id')}），按 {lot.qty} 股计"
                )
                qty = lot.qty
            if qty:
                avg = lot.cost_total / lot.qty
                lot.realized += (price - avg) * qty
                lot.cost_total -= avg * qty
                lot.qty -= qty
            lot.sell_count += 1
            if lot.qty == 0:
                # 浮点残留清零，否则下次买入的均价会被污染
                lot.cost_total = 0.0
                lot.closed_dates.append(day)
        else:
            lot.warnings.append(f"{day} 未知 side={side!r}（记录 {t.get('id')}）")

    return lots


def open_positions(account: str = "swing", to_date: Optional[str] = None) -> list[Lot]:
    """当前持仓，按首次买入日期排序。"""
    lots = build_lots(account, to_date)
    return sorted(
        (l for l in lots.values() if l.is_open),
        key=lambda l: (l.first_date, l.code),
    )


def closed_positions(account: str = "swing", to_date: Optional[str] = None) -> list[Lot]:
    """已清仓的票（曾有持仓、现在归零），按最后交易日排序。"""
    lots = build_lots(account, to_date)
    return sorted(
        (l for l in lots.values() if not l.is_open and l.sell_count),
        key=lambda l: (l.last_date, l.code),
    )


def trades_of(code: str, account: str = "swing") -> list[dict]:
    return [t for t in read_records("trade", account) if t.get("code") == code]


def notes_of(code: str, account: str = "swing") -> list[dict]:
    return [n for n in read_records("note", account) if n.get("code") == code]


def pending_notes(account: str = "swing", as_of: Optional[str] = None) -> list[dict]:
    """待验证且已到期的便签（D5 的复盘闭环）。

    没写 due 的待验证便签也返回——它们同样需要人来判断是否应验，
    只是不带到期压力，由调用方按 due 是否存在区别对待。
    """
    from datetime import date

    today = as_of or date.today().strftime("%Y-%m-%d")
    out = []
    for n in read_records("note", account):
        if n.get("status") != "待验证":
            continue
        due = n.get("due")
        if due is None or due <= today:
            out.append(n)
    return out


def summary(account: str = "swing", to_date: Optional[str] = None) -> dict:
    """账户层汇总。不含市值——那需要行情，由调用方补。"""
    lots = build_lots(account, to_date)
    opens = [l for l in lots.values() if l.is_open]
    return {
        "持仓只数": len(opens),
        "持仓成本合计": round(sum(l.cost_total for l in opens), 2),
        "已实现盈亏合计": round(sum(l.realized for l in lots.values()), 2),
        "交易笔数": sum(l.buy_count + l.sell_count for l in lots.values()),
        "清仓票数": len([l for l in lots.values() if not l.is_open and l.sell_count]),
        "警告": [w for l in lots.values() for w in l.warnings],
    }
