"""指数日线抓取：宽基指数池 → SQLite `index_bars_daily`。

设计要点：

- 指数代码带交易所前缀（`sh000001`），**全程绕开 `tools/stock_tools.py`**：
  `to_std_code('sh000001')` 会得到 `000001`，与平安银行撞车主键；`get_exchange_by_code`
  对 `000300` 误判深交所、对 `399300` 直接抛 `ValueError`。
- 每只指数配「主源 + 兜底源」。两个源各有静默失败模式：akshare 新浪的 `sh000985`
  数据停在 2016 却不报错、腾讯的 `bj899050` 只返回 1 根、腾讯对指数还有 2000 根上限。
  所以拿到数据必须过 `validate_index_bars`，尤其要校验新鲜度。
- 异常在本模块内吞掉、返回统计值给调用方打印 —— `daily_update.py` 里不写 try/except
  是既有风格（见 `datas/sync_stock_pool.py`）。
- 指数无复权、无换手率，字段与个股表语义不同，故独立成表；`amount` 当前两个源都不
  提供，是预留列。

用法:
    python -c "from datas.fetch_index_bars import update_all_indices; print(update_all_indices())"
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

import akshare as ak
import pandas as pd
import requests

from datas.create_database import (
    DAILY_BAR_TABLE,
    INDEX_BAR_TABLE,
    get_db_connection,
)
from datas.query_stock import get_earliest_index_date, query_index_latest_bars
from tools.log import get_fetch_logger

logger = get_fetch_logger()

AKSHARE = "akshare"
TENCENT = "tencent"

# 指数池：(symbol, 名称, 主源, 兜底源)
# 主源的选择依据是实测结果，不要凭直觉调换：
#   - sh000985 新浪源停在 2016-06-13，只能用腾讯
#   - bj899050 腾讯只返回 1 根，只能用新浪
#   - 其余新浪给全量历史，腾讯只给 2000 根（约 2018 年起），故新浪为主
# sh932000（中证2000）两个源都取不到，不纳入；小盘代理用 sz399303 国证2000。
INDEX_POOL: tuple[tuple[str, str, str, Optional[str]], ...] = (
    ("sh000001", "上证指数", AKSHARE, TENCENT),
    ("sz399001", "深证成指", AKSHARE, TENCENT),
    ("sz399006", "创业板指", AKSHARE, TENCENT),
    ("sh000688", "科创50", AKSHARE, TENCENT),
    ("bj899050", "北证50", AKSHARE, None),
    ("sh000300", "沪深300", AKSHARE, TENCENT),
    ("sh000905", "中证500", AKSHARE, TENCENT),
    ("sh000852", "中证1000", AKSHARE, TENCENT),
    ("sz399303", "国证2000", AKSHARE, TENCENT),
    ("sh000985", "中证全指", TENCENT, AKSHARE),
    ("sh000016", "上证50", AKSHARE, TENCENT),
    # 下面两个不是宽基，是**信号用的行业指数**，每日观察要用：
    #   证券公司 —— 「券商+沪深300+创业板共振」判据
    #   中证银行 —— 「大资金是否切防御」判据（弱市里资金切银行是典型动作）
    ("sz399975", "证券公司", AKSHARE, TENCENT),
    ("sz399986", "银行", AKSHARE, TENCENT),
)

# 默认基准：用户做中盘票，中证500 比上证更贴
DEFAULT_BENCHMARK = "sh000905"

REQUEST_DELAY = 0.5        # 指数间请求间隔，11 只串行够用
TENCENT_MAX_BARS = 2000    # 腾讯对指数有 2000 根上限，超过会报 param error
MIN_BARS = 60              # 少于这个根数视为数据不完整
MAX_DAILY_MOVE_PCT = 25.0  # 宽基指数单日不可能超过这个幅度
# 涨跌幅检查只作用于这个日期之后。1996-12-16 起 A 股才有 10% 涨跌停，
# 此前指数动辄翻倍——上证 1992-05-21 取消涨跌幅限制当天单日 +105%，
# 那是真实历史，不是脏数据（早期误判过一次，丢掉了上证 8726 根里的 6726 根）。
MOVE_CHECK_FROM = "1997-01-01"

TENCENT_URL = (
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    "?_var=kline_dayqfq&param={symbol},day,,,{bars},qfq"
)

BAR_COLUMNS = ["symbol", "date", "open", "close", "high", "low",
               "volume", "amount", "change_pct", "price_change"]


def get_index_name(symbol: str) -> str:
    """按 symbol 取指数中文名，池子里没有则返回 symbol 本身。"""
    for sym, name, _, _ in INDEX_POOL:
        if sym == symbol:
            return name
    return symbol


def _reference_trade_date() -> Optional[str]:
    """取个股表 MAX(date) 作为「最新交易日」基准。

    `tools/stock_tools.py:latest_trade_day()` 不处理节假日，长假期间会返回非交易日；
    个股表的 MAX(date) 才是真实交易日历（`market/cli.py` 也是这么反推的）。
    """
    try:
        with get_db_connection() as conn:
            row = conn.execute(f"SELECT MAX(date) FROM {DAILY_BAR_TABLE}").fetchone()
        return str(row[0]) if row and row[0] else None
    except Exception as e:
        logger.warning(f"取交易日基准失败（将跳过新鲜度校验）: {e}")
        return None


def _finalize(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """统一成标准列、date 转 datetime64、按日期升序去重，并算出涨跌幅。"""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    for col in ("open", "close", "high", "low", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["amount"] = pd.NA
    df["price_change"] = df["close"].diff()
    df["change_pct"] = df["close"].pct_change() * 100
    df["symbol"] = symbol
    return df.reset_index(drop=True)[BAR_COLUMNS]


def fetch_index_bars_from_akshare(symbol: str) -> Optional[pd.DataFrame]:
    """新浪源。注意：该接口**没有日期参数**，每次都返回全量历史（约 8700 根）。"""
    try:
        df = ak.stock_zh_index_daily(symbol=symbol)
    except Exception as e:
        logger.warning(f"{symbol} akshare 取数失败: {type(e).__name__}: {e}")
        return None

    if df is None or df.empty:
        return None
    if "date" not in df.columns or "close" not in df.columns:
        logger.warning(f"{symbol} akshare 返回的列不符合预期: {list(df.columns)}")
        return None
    return _finalize(df, symbol)


def fetch_index_bars_from_tencent(
    symbol: str, bars: int = TENCENT_MAX_BARS
) -> Optional[pd.DataFrame]:
    """腾讯源。返回数组顺序是 [日期, 开, 收, 高, 低, 量] —— 开收高低，不是开高低收。

    指数走 data[symbol]["day"]，个股才走 "qfqday"（指数无复权）。
    """
    url = TENCENT_URL.format(symbol=symbol, bars=bars)
    try:
        resp = requests.get(
            url, timeout=20,
            headers={"Referer": "https://gu.qq.com/",
                     "User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        payload = json.loads(resp.text.split("=", 1)[1])
    except Exception as e:
        logger.warning(f"{symbol} 腾讯取数失败: {type(e).__name__}: {e}")
        return None

    node = (payload.get("data") or {}).get(symbol) or {}
    rows = node.get("day") or node.get("qfqday") or []
    if not rows:
        return None

    df = pd.DataFrame(
        [r[:6] for r in rows],
        columns=["date", "open", "close", "high", "low", "volume"],
    )
    # 腾讯指数成交量单位是「手」，新浪是「股」。实测三个指数所有日期比值精确为
    # 100.0000，统一乘 100 对齐新浪口径，否则主源/兜底源切换会污染 volume 序列。
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce") * 100
    return _finalize(df, symbol)


_FETCHERS = {
    AKSHARE: fetch_index_bars_from_akshare,
    TENCENT: fetch_index_bars_from_tencent,
}


def validate_index_bars(
    df: Optional[pd.DataFrame], symbol: str, reference_date: Optional[str] = None
) -> tuple[bool, str]:
    """校验一份指数日线是否可信。返回 (是否通过, 原因)。

    第 4 条（新鲜度）是防静默出错的核心：新浪的 sh000985 停在 2016 却不报错，
    只有拿个股表的 MAX(date) 对一下才能发现。
    """
    if df is None or df.empty:
        return False, "无数据"
    if len(df) < MIN_BARS:
        return False, f"仅 {len(df)} 根，少于 {MIN_BARS}"

    dates = df["date"]
    if dates.duplicated().any():
        return False, "日期有重复"
    if not dates.is_monotonic_increasing:
        return False, "日期未严格递增"

    o, c, h, low = df["open"], df["close"], df["high"], df["low"]
    if (df[["open", "close", "high", "low"]] <= 0).any().any():
        return False, "存在非正的 OHLC"
    if (h + 1e-6 < pd.concat([o, c], axis=1).max(axis=1)).any():
        return False, "high 小于开收"
    if (low - 1e-6 > pd.concat([o, c], axis=1).min(axis=1)).any():
        return False, "low 大于开收"

    last_date = dates.iloc[-1].strftime("%Y-%m-%d")
    if reference_date and last_date < reference_date:
        return False, f"数据陈旧，最新仅到 {last_date}（基准 {reference_date}）"

    recent = df[df["date"] >= pd.Timestamp(MOVE_CHECK_FROM)]
    moves = recent["change_pct"].dropna()
    if not moves.empty and moves.abs().max() > MAX_DAILY_MOVE_PCT:
        return False, f"单日涨跌 {moves.abs().max():.1f}% 超出宽基指数合理区间"

    return True, f"{len(df)} 根，至 {last_date}"


def fetch_index_bars(
    symbol: str, reference_date: Optional[str] = None
) -> tuple[Optional[pd.DataFrame], str, str]:
    """按主源 → 兜底源依次尝试，返回 (数据, 实际用的源, 说明)。

    主源数据不合格（含陈旧）就换兜底源，两源都不合格则取根数多的那份并说明原因 ——
    源滞后一天不该让整个日更失败。
    """
    sources = [s for _, sym, s, fb in INDEX_POOL if sym == symbol for s in (s, fb)]
    if not sources:
        sources = [AKSHARE, TENCENT]

    best: Optional[pd.DataFrame] = None
    best_note = ""
    tried: list[str] = []

    for source in sources:
        if source is None:
            continue
        df = _FETCHERS[source](symbol)
        ok, note = validate_index_bars(df, symbol, reference_date)
        tried.append(f"{source}:{note}")
        if ok:
            return df, source, note
        if df is not None and not df.empty and (best is None or len(df) > len(best)):
            best, best_note = df, f"{source}:{note}"

    return best, "", "; ".join(tried) if tried else "无可用源"


def save_index_bars_to_database(df: pd.DataFrame, symbol: str) -> int:
    """增量写入：只写库中锚点之后的 bar，返回写入行数。

    首根新 bar 的涨跌幅要用库里的锚点收盘价算 —— 数据源不提供涨跌幅，而
    `_finalize` 里算的是「本次抓取序列内」的 diff，跨批次会断。
    """
    if df is None or df.empty:
        return 0

    tail = query_index_latest_bars(symbol, 1)
    if tail.empty:
        anchor_date, anchor_close = None, None
    else:
        anchor_date = tail["date"].iloc[-1].strftime("%Y-%m-%d")
        anchor_close = float(tail["close"].iloc[-1])

    earliest_db = get_earliest_index_date(symbol)
    write_df = df.copy()

    if anchor_date and earliest_db is not None \
            and write_df["date"].iloc[0] < earliest_db:
        # 源这次提供了比库里更早的历史（例如主源修好后回退过兜底源）。
        # 此时必须整段覆盖重写，否则旧的那段永远补不回来——增量只写更新的 bar。
        # 整段写时 change_pct 用序列自身的 diff（_finalize 已算好），首根仍为 NULL。
        logger.info(f"{symbol} 源提供更早历史（{write_df['date'].iloc[0].date()} < "
                    f"库中 {earliest_db.date()}），整段覆盖")
    else:
        if anchor_date:
            write_df = write_df[write_df["date"] > pd.Timestamp(anchor_date)]
        if write_df.empty:
            return 0
        if anchor_close:
            prev = anchor_close
            for idx in write_df.index:
                close = float(write_df.at[idx, "close"])
                write_df.at[idx, "price_change"] = round(close - prev, 4)
                write_df.at[idx, "change_pct"] = round((close / prev - 1) * 100, 4)
                prev = close
        else:
            # 首次导入：没有锚点，首根涨跌幅无从计算
            write_df.iloc[0, write_df.columns.get_loc("price_change")] = pd.NA
            write_df.iloc[0, write_df.columns.get_loc("change_pct")] = pd.NA

    write_df = write_df.round({"open": 4, "close": 4, "high": 4, "low": 4})
    write_df["date"] = write_df["date"].dt.strftime("%Y-%m-%d")
    write_df = write_df.astype(object).where(pd.notna(write_df), None)

    def upsert_method(table, cursor, keys, data_iter):
        columns = ", ".join(keys)
        placeholders = ", ".join([f":{key}" for key in keys])
        assignments = ", ".join([
            f"{col} = excluded.{col}" for col in keys
            if col not in ("symbol", "date")
        ])
        sql = f"""
            INSERT INTO {table.name} ({columns})
            VALUES ({placeholders})
            ON CONFLICT (symbol, date) DO UPDATE SET
            {assignments};
        """
        cursor.executemany(sql, ({k: v for k, v in zip(keys, row)} for row in data_iter))

    with get_db_connection() as conn:
        write_df.to_sql(
            name=INDEX_BAR_TABLE,
            con=conn,
            if_exists="append",
            index=False,
            method=upsert_method,
            chunksize=2000,
        )
        conn.commit()

    return len(write_df)


def update_all_indices(reference_date: Optional[str] = None) -> dict[str, Any]:
    """抓取并写入全部指数。异常逐个吞掉，返回统计供调用方打印。"""
    reference = reference_date or _reference_trade_date()
    stats: dict[str, Any] = {
        "total": len(INDEX_POOL),
        "ok": 0,
        "stale": [],
        "failed": [],
        "rows": 0,
        "sources": {},
    }

    for i, (symbol, name, _, _) in enumerate(INDEX_POOL):
        if i:
            time.sleep(REQUEST_DELAY)
        try:
            df, source, note = fetch_index_bars(symbol, reference)
            if df is None or df.empty:
                logger.warning(f"指数 {symbol} {name}: {note}")
                stats["failed"].append(f"{symbol}({name})")
                continue

            written = save_index_bars_to_database(df, symbol)
            stats["rows"] += written
            stats["sources"][symbol] = source or "兜底"

            last = df["date"].iloc[-1].strftime("%Y-%m-%d")
            if reference and last < reference:
                stats["stale"].append(f"{symbol}({name}) 至 {last}")
                logger.warning(f"指数 {symbol} {name}: 落后于基准 {reference}，仅到 {last}")
            else:
                stats["ok"] += 1
            logger.info(f"指数 {symbol} {name}: {note}，写入 {written} 行"
                        + (f"（源 {source}）" if source else "（兜底）"))
        except Exception as e:
            logger.error(f"指数 {symbol} {name} 处理异常: {e}", exc_info=True)
            stats["failed"].append(f"{symbol}({name})")

    return stats


if __name__ == "__main__":
    print(update_all_indices())
