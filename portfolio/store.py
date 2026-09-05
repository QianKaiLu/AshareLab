"""波段账户的 JSONL 存储层。

三类记录各一个文件，全部追加式写入（含止损调整——改止损是追加一条新记录，
不覆盖旧的，这样才能统计「往下挪止损」的次数）：

    portfolio/swing/trades.jsonl    逐笔交易
    portfolio/swing/notes.jsonl     便签
    portfolio/swing/stops.jsonl     止损计划及其调整

本模块只做校验与落盘，不碰行情数据库——持仓与成本由 position.py 现算，
股票名解析由 cli.py 负责。这样 store / position 不依赖 pandas 与 sqlite。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

# 记录类型 → (文件名, id 前缀)
KINDS = {
    "trade": ("trades.jsonl", "T"),
    "note": ("notes.jsonl", "N"),
    "stop": ("stops.jsonl", "S"),
}

SIDES = ("buy", "sell")

# 便签类型，自由填写，这里只是给 CLI 做提示与拼写检查的参考集
NOTE_TYPES = ("买入理由", "卖出理由", "盘中异动", "交易计划", "复盘结论", "其它")

# 止损依据线。「人工」表示凭观察确定的位置，不必对应某条均线
STOP_BASIS = ("黄线", "白线", "点火低点", "N型低点", "BBI", "人工")

NOTE_STATUS = ("待验证", "已验证", "已复盘")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def account_dir(account: str = "swing") -> Path:
    return repo_root() / "portfolio" / account


def kind_path(kind: str, account: str = "swing") -> Path:
    if kind not in KINDS:
        raise ValueError(f"未知记录类型 {kind!r}，可选 {list(KINDS)}")
    return account_dir(account) / KINDS[kind][0]


class ValidationError(ValueError):
    """录入数据不合法。CLI 捕获后打印人话，不抛栈。"""


def parse_date(raw: str | date | datetime | None) -> str:
    """把常见日期写法归一成 YYYY-MM-DD，None / 空 → 今天。"""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return date.today().strftime("%Y-%m-%d")
    if isinstance(raw, datetime):
        return raw.strftime("%Y-%m-%d")
    if isinstance(raw, date):
        return raw.strftime("%Y-%m-%d")

    s = str(raw).strip().replace("/", "-").replace(".", "-")
    for ch in ("年", "月"):
        s = s.replace(ch, "-")
    s = s.replace("日", "").strip().rstrip("-")
    if s in ("today", "今天"):
        return date.today().strftime("%Y-%m-%d")

    for fmt in ("%Y-%m-%d", "%y-%m-%d", "%Y%m%d", "%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if fmt == "%m-%d":
            # 无年份：按今年补，若落在未来则算上一年
            today = date.today()
            dt = dt.replace(year=today.year)
            if dt.date() > today:
                dt = dt.replace(year=today.year - 1)
        return dt.strftime("%Y-%m-%d")
    raise ValidationError(f"无法识别的日期: {raw!r}")


def read_records(kind: str, account: str = "swing") -> list[dict]:
    """读一类记录，按 (date, id) 排序。坏行不静默跳过，直接报错定位到行号。"""
    path = kind_path(kind, account)
    if not path.exists():
        return []

    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValidationError(f"{path}:{lineno} JSON 解析失败: {e}") from e
    rows.sort(key=lambda r: (r.get("date", ""), r.get("id", "")))
    return rows


def append_record(kind: str, record: dict, account: str = "swing") -> dict:
    """追加一条记录。id 由调用方通过 next_id 预先生成。"""
    path = kind_path(kind, account)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def rewrite_records(kind: str, records: Iterable[dict], account: str = "swing") -> None:
    """整体重写（仅用于删除记录）。先写临时文件再替换，避免写坏原文件。"""
    path = kind_path(kind, account)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)


def next_id(kind: str, day: str, code: str, account: str = "swing") -> str:
    """生成形如 T20260904-300314-1 的 id：可读、可 grep、同日同票自动递增。"""
    prefix = KINDS[kind][1]
    stem = f"{prefix}{day.replace('-', '')}-{code}"
    used = {r.get("id", "") for r in read_records(kind, account)}
    seq = 1
    while f"{stem}-{seq}" in used:
        seq += 1
    return f"{stem}-{seq}"


def find_record(rid: str, account: str = "swing") -> tuple[Optional[str], Optional[dict]]:
    """按 id 在三类记录里查，返回 (kind, record)。"""
    for kind in KINDS:
        for r in read_records(kind, account):
            if r.get("id") == rid:
                return kind, r
    return None, None


def delete_record(rid: str, account: str = "swing") -> Optional[dict]:
    """按 id 删除。删交易会连带影响持仓，调用方负责提示。"""
    kind, rec = find_record(rid, account)
    if not rec:
        return None
    remain = [r for r in read_records(kind, account) if r.get("id") != rid]
    rewrite_records(kind, remain, account)
    return rec


def update_record(rid: str, changes: dict, account: str = "swing") -> Optional[dict]:
    """按 id 就地改字段，返回改后的记录。

    只给便签状态流转用（待验证 → 已验证/已复盘）。**交易与止损不走这里**：
    交易改了会让持仓与历史对不上，止损改了会抹掉「当时写的是什么」——那两类要么
    追加新记录，要么删掉重录。
    """
    kind, rec = find_record(rid, account)
    if not rec:
        return None
    if kind != "note":
        raise ValidationError(
            f"{rid} 是 {kind} 记录，不能改。交易请删除重录，止损请追加新记录（保留留痕）"
        )
    rows = read_records(kind, account)
    for r in rows:
        if r.get("id") == rid:
            r.update(changes)
            rec = r
            break
    rewrite_records(kind, rows, account)
    return rec


def verify_note(
    rid: str,
    status: str = "已验证",
    result: Optional[str] = None,
    account: str = "swing",
) -> Optional[dict]:
    """给便签盖章：待验证 → 已验证 / 已复盘（设计决策 D5 的复盘闭环）。

    result 是应验与否的结论，附加在原文之后而不是替换——原判断必须留着，
    否则下次就看不出当时想错在哪。
    """
    if status not in NOTE_STATUS:
        raise ValidationError(f"status 可选 {list(NOTE_STATUS)}，收到 {status!r}")
    changes: dict[str, Any] = {"status": status, "verified_at": date.today().strftime("%Y-%m-%d")}
    if result:
        changes["result"] = result.strip()
    return update_record(rid, changes, account)


# --- 记录构造：字段校验集中在这里，CLI 只管收集参数 ---------------------------


def _positive(value: Any, field_name: str, allow_zero: bool = False) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError) as e:
        raise ValidationError(f"{field_name} 不是数字: {value!r}") from e
    if v < 0 or (v == 0 and not allow_zero):
        raise ValidationError(f"{field_name} 必须为正数，收到 {value!r}")
    return v


def make_trade(
    code: str,
    name: str,
    side: str,
    day: str,
    price: float,
    qty: float,
    remark: Optional[str] = None,
    note_id: Optional[str] = None,
    snapshot: Optional[dict] = None,
    account: str = "swing",
) -> dict:
    """构造一条交易记录。不含手续费（设计决策 D15）。"""
    if side not in SIDES:
        raise ValidationError(f"side 必须是 buy / sell，收到 {side!r}")
    day = parse_date(day)
    rec = {
        "id": next_id("trade", day, code, account),
        "code": code,
        "name": name,
        "side": side,
        "date": day,
        "price": round(_positive(price, "price"), 4),
        "qty": int(_positive(qty, "qty")),
    }
    if remark:
        rec["remark"] = remark
    if note_id:
        rec["note_id"] = note_id
    # 测量快照（D14）：成交日的客观测量值，落盘时算一次存死，
    # 避免半年后重算历史撞上前复权因子变化导致结论不可复现
    rec["snapshot"] = snapshot or {}
    return rec


def make_note(
    text: str,
    day: str,
    code: Optional[str] = None,
    note_type: str = "其它",
    related_trade_id: Optional[str] = None,
    status: Optional[str] = None,
    due: Optional[str] = None,
    account: str = "swing",
) -> dict:
    if not text or not text.strip():
        raise ValidationError("便签内容不能为空")
    day = parse_date(day)
    rec = {
        "id": next_id("note", day, code or "market", account),
        "date": day,
        "type": note_type,
        "text": text.strip(),
    }
    if code:
        rec["code"] = code
    if related_trade_id:
        rec["related_trade_id"] = related_trade_id
    if status:
        if status not in NOTE_STATUS:
            raise ValidationError(f"status 可选 {list(NOTE_STATUS)}，收到 {status!r}")
        rec["status"] = status
    if due:
        rec["due"] = parse_date(due)
    return rec


def make_stop(
    code: str,
    plan: str,
    day: str,
    price: Optional[float] = None,
    basis: Optional[str] = None,
    related_trade_id: Optional[str] = None,
    account: str = "swing",
) -> dict:
    """构造止损计划（D9）。

    plan 文字描述必填——「每一笔交易都必须有止损计划」是核心原则，但价位不好
    客观识别时（如 N 型上一低点）允许只写文字，由人工观察把关。
    """
    if not plan or not plan.strip():
        raise ValidationError("止损计划描述不能为空")
    day = parse_date(day)
    rec = {
        "id": next_id("stop", day, code, account),
        "code": code,
        "date": day,
        "plan": plan.strip(),
    }
    if price is not None:
        rec["price"] = round(_positive(price, "price"), 4)
    if basis:
        if basis not in STOP_BASIS:
            raise ValidationError(f"basis 可选 {list(STOP_BASIS)}，收到 {basis!r}")
        rec["basis"] = basis
    if related_trade_id:
        rec["related_trade_id"] = related_trade_id
    return rec


def latest_stop(code: str, account: str = "swing") -> Optional[dict]:
    """取某票当前生效的止损计划——即最后追加的那条。"""
    stops = [r for r in read_records("stop", account) if r.get("code") == code]
    return stops[-1] if stops else None


def stop_history(code: str, account: str = "swing") -> list[dict]:
    return [r for r in read_records("stop", account) if r.get("code") == code]
