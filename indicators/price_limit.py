"""涨跌停幅度与归一化 K 线实体。

出货形态判定里的「大阴线」必须按板块涨跌停幅度归一化，不能直接用百分比。
《主力出货的 5 种典型方式》原话：「这是 20 厘米的票，它 5% 相当于普通票的
2.5%」——同一个 -5%，在主板是半根跌停，在创业板只有四分之一。

另一个必须归一化的理由来自实测：中国中铁 2014-12-22 是文稿点名的标准 S1，
当日 change_pct 只有 -3.35%，光看涨跌幅根本筛不出来；但它开 7.45 收 6.63，
实体 -11.01%，是一根一倍跌停幅度的光头光脚大阴线（文稿称「一字断头，从涨停板
直接一笔单子砸到 1% 点几」）。所以：

    「大阴线」= 实体（open → close），不是涨跌幅（昨收 → close）

实体口径同时解决了文稿反复强调的另一件事——「所有的假阴真阳都当阴线处理」。
假阴真阳指收盘低于开盘但高于昨收，按实体算天然为负，无需额外规则。
"""
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------- 板块涨跌停幅度
# 制度变更有明确生效日，历史回溯必须按当日制度取值，否则 2013 年的创业板案例
# 会被按 20% 归一化而严重低估。
# 科创板开市即 20%；创业板注册制改革 2020-08-24 起 20%；
# 北交所 2021-11-15 开市即 30%（此前精选层同为 30%，这里不单独区分）。
STAR_20PCT_SINCE = "2019-07-22"
CHINEXT_20PCT_SINCE = "2020-08-24"
BSE_30PCT_SINCE = "2020-07-27"

DEFAULT_LIMIT_PCT = 10.0
ST_LIMIT_PCT = 5.0


def board_limit_pct(code: str, date: Optional[str] = None,
                    name: Optional[str] = None) -> float:
    """该股在指定日期的涨跌停幅度（百分比，如 10.0 表示 ±10%）。

    Args:
        code: 6 位标准股票代码
        date: 交易日 'YYYY-MM-DD' 或 'YYYYMMDD'。为 None 时按现行制度取值。
        name: 股票名称，用于识别 ST / *ST（5% 限制）。

    Note:
        ST 判定依赖传入的**当前**名称，而 stock_base_info 只存当前名称。
        因此回溯历史时，一只现已摘帽的票在被 ST 期间会按 10% 归一化（偏低估），
        反之现已戴帽的票在正常期间会按 5% 归一化（偏高估）。已知局限，
        影响面仅限 ST 股，不为此单独维护历史名称表。
    """
    if name and "ST" in name.upper():
        return ST_LIMIT_PCT

    code = str(code).zfill(6)
    day = _normalize(date)

    # 北交所：8xxxxx 与 430xxx
    if code.startswith(("83", "87", "88", "43", "92")):
        return 30.0 if day >= BSE_30PCT_SINCE else DEFAULT_LIMIT_PCT

    # 科创板
    if code.startswith(("688", "689")):
        return 20.0 if day >= STAR_20PCT_SINCE else DEFAULT_LIMIT_PCT

    # 创业板
    if code.startswith(("300", "301", "302")):
        return 20.0 if day >= CHINEXT_20PCT_SINCE else DEFAULT_LIMIT_PCT

    return DEFAULT_LIMIT_PCT


def _normalize(date: Optional[str]) -> str:
    """把 'YYYYMMDD' / 'YYYY-MM-DD' / date / Timestamp 统一成 'YYYY-MM-DD'。

    None 视为「今天及以后」，用一个远期日期使所有制度变更都已生效。
    """
    if date is None:
        return "9999-12-31"
    s = str(date)[:10]
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


def add_price_limit_to_dataframe(
    df: pd.DataFrame,
    code: str,
    name: Optional[str] = None,
    inplace: bool = False,
) -> Optional[pd.DataFrame]:
    """给 DataFrame 加涨跌停幅度与归一化涨跌列。

    新增列：

        limit_pct   当日涨跌停幅度（百分比）
        body_pct    实体涨跌幅 (close/open - 1) * 100
        body_norm   归一化实体 = body_pct / limit_pct。-1.0 即一根满幅跌停实体
        chg_norm    归一化涨跌幅 = change_pct / limit_pct

    `body_norm` 是出货判定的主尺子：跨板块、跨年代可比。
    """
    target = df if inplace else df.copy()

    dates = target["date"].astype(str)
    target["limit_pct"] = [board_limit_pct(code, d, name) for d in dates]

    body_pct = (target["close"] / target["open"] - 1) * 100
    target["body_pct"] = body_pct.where(target["open"] > 0, 0.0).round(2)
    target["body_norm"] = (target["body_pct"] / target["limit_pct"]).round(3)

    if "change_pct" in target.columns:
        target["chg_norm"] = (target["change_pct"] / target["limit_pct"]).round(3)

    return None if inplace else target


# ---------------------------------------------------------------- ST 幅度的数据推断
# stock_base_info 只存当前名称，回溯历史时无法知道某只票在 2013 年是否戴帽。
# 用涨跌幅分布反推：若窗口内完全没有超过 5.3% 的波动，却出现过多次贴近 5% 的
# 波动，那这段时间它的涨跌停就是 ±5%。
ST_HIT_LOW = 4.8
ST_HIT_HIGH = 5.2
ST_EXCEED = 5.3
ST_MIN_HITS = 2


def refine_limit_by_history(df: pd.DataFrame, lookback: int = 250) -> pd.Series:
    """按历史涨跌幅分布把规则推出的 limit_pct 修正为 5%（识别 ST 区间）。

    只做「下调至 5」这一个方向的修正，且要求证据充分：窗口内无一根超过 5.3%，
    同时至少两根贴在 5% 上。这样一只一年都没波动超过 5% 的冷门大盘股
    （没有贴 5% 的记录）不会被误判成 ST——那种误判会让 body_norm 翻倍，
    凭空造出 S1 信号。

    Returns:
        修正后的 limit_pct Series（与 df 同索引）。
    """
    limit = df["limit_pct"].copy()
    if "change_pct" not in df.columns:
        return limit

    absolute = df["change_pct"].abs()
    exceed = (absolute > ST_EXCEED).rolling(lookback, min_periods=20).sum()
    hits = absolute.between(ST_HIT_LOW, ST_HIT_HIGH).rolling(
        lookback, min_periods=20).sum()

    is_st = (exceed == 0) & (hits >= ST_MIN_HITS)
    return limit.where(~is_st, ST_LIMIT_PCT)
