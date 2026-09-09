"""市场环境分析的当日数据抓取。

独立工具，不依赖 portfolio / hunters。数据源（2026-09-09 实测可用）：

    乐咕市场活跃度      涨跌家数、真实涨停/跌停、活跃度      仅当天
    东财涨停/炸板池     连板数、封单、所属行业               支持历史日期
    东财昨日涨停池      算晋级率与昨日涨停溢价（赚钱效应）   支持历史日期
    东财 push2delay     504 概念 + 496 行业，带 BK 代码       仅当天
    大小票创新高        本地日线库算，沪深300 vs 中证2000     可任意回溯

板块榜用 push2delay 域名：push2 主域名对板块接口断连，delay 域名正常，
且与涨停池同属东财口径（避免多口径打架）。同花顺/新浪作降级备份。

输出：market/history/YYYY-MM-DD.json，入 git，供环比与持续性分析。
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

import akshare as ak
import pandas as pd
import requests

REPO = Path(__file__).resolve().parent.parent
DB_PATH = REPO / "database" / "ashare_data.db"
INDEX_DIR = REPO / "datas" / "index_lists"

# push2delay：板块接口在 push2 主域名断连，delay 域名可用
EM_BOARD_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
EM_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
}
# 非题材板块，会污染主题榜（宽基/风格/统计类）
BOARD_BLACKLIST = ("HS300", "沪深300", "上证50", "中证", "融资融券", "基金重仓",
                   "昨日涨停", "昨日连板", "机构重仓", "预盈预增", "AH股", "京津冀",
                   "含B股", "含H股", "创业成份", "微盘股", "标准普尔", "MSCI")

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


PAGE_SIZE = 100  # 接口每页硬上限，pz 传更大也只回 100，必须翻页


def _em_boards(fs: str, kind: str) -> list[dict]:
    """东财板块榜（push2delay）。fs=m:90+t:3 概念 / m:90+t:2 行业。

    翻页取全量（概念约 504 个、行业约 496 个）。f6 成交额单位是元；
    f3 在 fltt=2 下已是百分数，旧格式是放大 100 倍的整数，两者都兼容。
    """
    rows: list[dict] = []
    total = None
    for page in range(1, 12):          # 上限 1100 个板块，够用
        params = {
            "pn": page, "pz": PAGE_SIZE, "po": 1, "np": 1, "fltt": 2, "invt": 2,
            "fid": "f3", "fs": fs,
            "fields": "f2,f3,f6,f12,f14,f104,f105,f128,f140",
        }
        r = requests.get(EM_BOARD_URL, params=params, headers=EM_HEADERS, timeout=15)
        r.raise_for_status()
        data = (r.json() or {}).get("data") or {}
        diff = data.get("diff") or []
        batch = diff if isinstance(diff, list) else list(diff.values())
        if not batch:
            break
        rows.extend(batch)
        total = data.get("total") or total
        if total and len(rows) >= total:
            break

    out = []
    for it in rows:
        name = str(it.get("f14") or "")
        if not name or any(b in name for b in BOARD_BLACKLIST):
            continue
        pct = it.get("f3")
        amt = it.get("f6")
        out.append({
            "code": str(it.get("f12") or ""),
            "name": name,
            "kind": kind,
            # fltt=2 时 f3 已是百分数；兼容整数放大 100 倍的旧格式
            "pct": round(float(pct) / (100 if abs(float(pct)) > 100 else 1), 2)
                   if pct not in (None, "-") else None,
            "amount_yi": round(float(amt) / 1e8, 1) if amt not in (None, "-") else None,
            "up": it.get("f104"),
            "down": it.get("f105"),
            "leader": str(it.get("f128") or ""),
            "leader_code": str(it.get("f140") or ""),
        })
    return out


def fetch_boards_em() -> dict[str, list[dict]]:
    """概念 + 行业两个板块榜（东财口径，已过滤非题材板块）。"""
    return {
        "concept": _em_boards("m:90+t:3", "concept"),
        "industry": _em_boards("m:90+t:2", "industry"),
    }


def fetch_money_effect(date: str) -> dict:
    """赚钱效应：晋级率 + 昨日涨停今日溢价。

    这是「打板资金实际赚不赚钱」的直接度量，比涨停家数更本质。
    溢价用**中位数**作主指标——均值会被少数连板股拉高（实测 09-09
    均值 +1.11% 而中位 -0.60%，方向相反）。
    """
    prev = ak.stock_zt_pool_previous_em(date=date)
    if prev is None or prev.empty:
        return {"prev_zt_count": 0}
    today = ak.stock_zt_pool_em(date=date)
    today_codes = set(today["代码"]) if today is not None and not today.empty else set()

    chg = pd.to_numeric(prev["涨跌幅"], errors="coerce").dropna()
    promoted = prev[prev["代码"].isin(today_codes)]
    n = len(prev)
    return {
        "prev_zt_count": int(n),
        "promote_count": int(len(promoted)),
        "promote_rate": round(len(promoted) / n * 100, 1) if n else None,
        "premium_median": round(float(chg.median()), 2) if len(chg) else None,
        "premium_mean": round(float(chg.mean()), 2) if len(chg) else None,
        "red_ratio": round(float((chg > 0).mean() * 100), 1) if len(chg) else None,
    }


def _index_members(filename: str) -> set[str]:
    path = INDEX_DIR / filename
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {r["code"].strip().split(".")[0].zfill(6)
                for r in csv.DictReader(f) if r.get("code")}


def fetch_newhigh_divergence(date: str, window: int = 20) -> dict:
    """大小票分歧：沪深300 与 中证2000 的创 N 日新高家数（modoo 复盘法）。

    「中证 2000 的 20 日新高看游资对小票炒作的态度，沪深 300 创 20 日新高
    代表机构们的看法」——两拨资金各自在多大范围上做突破。

    纯本地日线库计算，不依赖外部接口，可任意回溯。口径为**收盘价创新高**
    （收盘 = 近 window 日最高收盘）；行情软件若用最高价口径家数会略多。
    指数成分用当前名单快照，回溯早期数据有成分变动偏差。
    """
    day = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if "-" not in date else date
    hs300 = _index_members("hs300_stock_list.csv")
    csi2000 = _index_members("csi2000_stock_list.csv")
    if not hs300 or not csi2000 or not DB_PATH.exists():
        return {"error": "缺少指数成分名单或行情库"}

    conn = sqlite3.connect(DB_PATH)
    try:
        dates = [r[0] for r in conn.execute(
            "select distinct date from stock_bars_daily_qfq where date <= ? "
            "order by date desc limit ?", (day, window))]
        if len(dates) < window:
            return {"error": f"{day} 之前不足 {window} 个交易日"}
        start = dates[-1]
        df = pd.read_sql(
            "select code, date, close from stock_bars_daily_qfq "
            "where date >= ? and date <= ?", conn, params=(start, day))
    finally:
        conn.close()

    if df.empty:
        return {"error": f"{day} 无行情数据"}
    piv = df.pivot(index="date", columns="code", values="close").sort_index()
    if len(piv) < window:
        return {"error": f"{day} 数据不足 {window} 日"}
    last = piv.iloc[-1]
    is_nh = last >= piv.max()          # 收盘创窗口内新高

    def stat(members: set[str]) -> tuple[int, int]:
        cols = [c for c in is_nh.index if c in members]
        return int(is_nh[cols].sum()), len(cols)

    n3, t3 = stat(hs300)
    n2, t2 = stat(csi2000)
    p3 = round(n3 / t3 * 100, 1) if t3 else None
    p2 = round(n2 / t2 * 100, 1) if t2 else None
    lean = None
    if p3 is not None and p2 is not None:
        gap = p2 - p3
        lean = "小票占优" if gap > 2 else ("大票占优" if gap < -2 else "均衡")
    return {
        "window": window,
        "date": str(piv.index[-1])[:10],
        "hs300_newhigh": n3, "hs300_total": t3, "hs300_pct": p3,
        "csi2000_newhigh": n2, "csi2000_total": t2, "csi2000_pct": p2,
        "lean": lean,
    }


def fetch_snapshot(date: str) -> dict:
    """抓当日快照。

    只有东财涨停池系列支持历史日期；乐咕情绪、同花顺行业、新浪概念是**实时
    接口**，抓历史日期会存进当天的数据、污染持续性分析。所以历史快照只存
    涨停池/炸板池，实时榜只在当天快照里抓。
    """
    from datetime import date as _date

    is_today = date == _date.today().strftime("%Y%m%d")
    snap: dict[str, Any] = {"date": date, "errors": []}

    def grab(key: str, fn) -> None:
        try:
            snap[key] = fn()
        except Exception as e:
            snap["errors"].append(f"{key}: {type(e).__name__}: {str(e)[:100]}")

    # 支持历史日期的源：回溯补抓即可拿到环比与持续性数据
    grab("limit_up", lambda: fetch_limit_up(date))
    grab("broken", lambda: fetch_broken(date))
    grab("money_effect", lambda: fetch_money_effect(date))
    grab("newhigh", lambda: fetch_newhigh_divergence(date))

    # 只有当天的源：实时接口无历史参数，抓历史日期会存进当天数据、污染分析
    if is_today:
        grab("market", fetch_market)
        grab("boards_em", fetch_boards_em)
        grab("industry_ths", fetch_industry_ths)      # 降级备份
        grab("concept_sina", fetch_concept_sina)      # 降级备份
    else:
        snap["_note"] = ("历史快照：含涨停池/炸板池/赚钱效应/大小票分歧；"
                         "板块榜与情绪总览是实时接口，仅当日快照含")

    return snap


def save_snapshot(snap: dict) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = history_path(snap["date"])
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
