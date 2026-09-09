"""主题/主线工具的当日数据抓取。

独立工具，不依赖 portfolio / hunters。数据源全部走 akshare 公开接口
（2026-09-09 实测）：
    乐咕市场活跃度    —— 涨跌家数、真实涨停/跌停、活跃度
    东财涨停池系列    —— 涨停/炸板/跌停池（东财 push2ex，稳定）
    同花顺行业总览    —— 90 个行业：涨跌幅、净流入、涨跌家数、领涨股
    新浪概念板块      —— 175 个概念：涨跌幅、公司家数、领涨股
    （东财板块榜 push2 接口被断连，不可用；新浪概念作主题口径）

输出：theme/history/YYYY-MM-DD.json，入 git，供多日持续性分析。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import akshare as ak

HISTORY_DIR = Path(__file__).parent / "history"


def history_path(date: str) -> Path:
    return HISTORY_DIR / f"{date}.json"


def load_history() -> dict[str, dict]:
    """读全部历史快照，{date: snapshot}。"""
    out = {}
    if HISTORY_DIR.exists():
        for p in sorted(HISTORY_DIR.glob("*.json")):
            try:
                out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
    return out


def fetch_market() -> dict:
    """乐咕市场活跃度：涨跌家数、涨停跌停（含真实口径）、活跃度。"""
    df = ak.stock_market_activity_legu()
    d = {r["item"]: r["value"] for _, r in df.iterrows()}

    def num(v):
        """乐咕返回值带 '%' 等格式，剥干净再转。"""
        if v is None:
            return None
        try:
            return float(str(v).replace("%", "").strip())
        except (TypeError, ValueError):
            return None

    return {
        "up": num(d.get("上涨")),
        "down": num(d.get("下跌")),
        "flat": num(d.get("平盘")),
        "limit_up": num(d.get("涨停")),
        "real_limit_up": num(d.get("真实涨停")),
        "limit_down": num(d.get("跌停")),
        "real_limit_down": num(d.get("真实跌停")),
        "activity": num(d.get("活跃度")),
        "date": str(d.get("统计日期", ""))[:10],
    }


def fetch_limit_up(date: str) -> list[dict]:
    """东财涨停池 → 精简字段。"""
    df = ak.stock_zt_pool_em(date=date)
    out = []
    for _, r in df.iterrows():
        out.append({
            "code": str(r["代码"]),
            "name": str(r["名称"]),
            "industry": str(r["所属行业"]),     # 东财行业口径
            "boards": int(r["连板数"]),
            "seal_amt": float(r["封板资金"]),
            "first_seal": str(r["首次封板时间"]),
            "turnover": float(r["换手率"]),
        })
    return out


def fetch_broken(date: str) -> list[dict]:
    """炸板池：炸过板的票（首板失败者）——情绪弱的核心指标。"""
    df = ak.stock_zt_pool_zbgc_em(date=date)
    return [{"code": str(r["代码"]), "name": str(r["名称"]),
             "industry": str(r.get("所属行业", "")), "chg": float(r["涨跌幅"])}
            for _, r in df.iterrows()]


def fetch_industry_ths() -> list[dict]:
    """同花顺 90 个行业板块行情（含净流入、涨跌家数、领涨股）。"""
    df = ak.stock_board_industry_summary_ths()
    return [
        {"name": str(r["板块"]),
         "pct": float(r["涨跌幅"]) if r["涨跌幅"] not in ("", None) else None,
         "net_inflow": float(r["净流入"]) if r["净流入"] not in ("", None) else None,
         "up": int(r["上涨家数"]) if str(r["上涨家数"]).isdigit() else None,
         "down": int(r["下跌家数"]) if str(r["下跌家数"]).isdigit() else None,
         "leader": str(r["领涨股"]),
         "leader_pct": float(r["领涨股-涨跌幅"]) if r["领涨股-涨跌幅"] not in ("", None) else None}
        for _, r in df.iterrows()
    ]


def fetch_concept_sina() -> list[dict]:
    """新浪概念板块行情（175 个，主题口径；单位是手与万元，转亿）。"""
    df = ak.stock_sector_spot(indicator="概念")
    out = []
    for _, r in df.iterrows():
        out.append({
            "name": str(r["板块"]),
            "n": int(r["公司家数"]),
            "pct": float(r["涨跌幅"]),
            "amount_yi": round(float(r["总成交额"]) / 1e4, 1),  # 新浪单位万元 → 亿
            "leader": str(r["股票名称"]),
            "leader_pct": float(r["个股-涨跌幅"]),
        })
    return out


def fetch_snapshot(date: str) -> dict:
    """抓当日快照。

    只有东财涨停池系列支持历史日期；乐咕情绪、同花顺行业、新浪概念是**实时
    接口**，抓历史日期会存进当天的数据、污染持续性分析。所以历史快照只存
    涨停池/炸板池，实时榜只在当天快照里抓。
    """
    from datetime import date as _date

    is_today = date == _date.today().strftime("%Y%m%d")
    snap: dict[str, Any] = {"date": date, "errors": []}

    if is_today:
        try:
            snap["market"] = fetch_market()
        except Exception as e:
            snap["errors"].append(f"market: {type(e).__name__}: {str(e)[:100]}")

    try:
        snap["limit_up"] = fetch_limit_up(date)
    except Exception as e:
        snap["errors"].append(f"limit_up: {type(e).__name__}: {str(e)[:100]}")

    try:
        snap["broken"] = fetch_broken(date)
    except Exception as e:
        snap["errors"].append(f"broken: {type(e).__name__}: {str(e)[:100]}")

    if is_today:
        try:
            snap["industry_ths"] = fetch_industry_ths()
        except Exception as e:
            snap["errors"].append(f"industry_ths: {type(e).__name__}: {str(e)[:100]}")

        try:
            snap["concept_sina"] = fetch_concept_sina()
        except Exception as e:
            snap["errors"].append(f"concept_sina: {type(e).__name__}: {str(e)[:100]}")
    else:
        snap["_note"] = "历史快照：仅涨停池/炸板池（实时榜无历史参数，当日快照才含）"

    return snap


def save_snapshot(snap: dict) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = history_path(snap["date"])
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
