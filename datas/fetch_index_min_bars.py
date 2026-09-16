"""指数分钟线抓取与周期合成。

数据源：**新浪** `CN_MarketData.getKLineData`（2026-09-17 实测可用）。

    东财 `index_zh_a_hist_min_em`  连接层被拒（老问题，08-24 就记录过）
    腾讯 `kline/mkline`            重定向到 web3.ifzq.gtimg.cn，该域名连不通

新浪支持 scale = 5 / 15 / 30 / 60 / 240，**不支持 120**。所以本模块：

- **只抓 30 分钟**存库（`index_bars_min` 表，period=30）
- 60 / 120 由 `aggregate_bars()` 在读时合成

为什么不把 60 也单独抓：新浪原生 60 分钟与「由 30 分钟合成的 60 分钟」若并存，
两者会有细微差异（边界对齐、含午休的处理不同），反而制造「同一指标两个值」的麻烦。
**一个来源，一套口径。**

## 合成的关键：必须按交易时段分组

A 股一天 4 小时 = 240 分钟，但**中间休市 1.5 小时**（11:30-13:00）。所以不能简单按
固定的 120 分钟窗口切——那样会切出 12:30 / 14:30 / 16:30 这种跨午休的边界，
最后一根只含 1 根 30 分钟 bar。

正确的分组是按**上午 / 下午两个时段**各自成组：

    30 分钟（Sina 的标签是 bar 的**结束**时刻）：
        上午 10:00 10:30 11:00 11:30    下午 13:30 14:00 14:30 15:00
    60 分钟：  每 2 根一组  → 10:30 11:30 14:00 15:00
    120 分钟： 每 4 根一组  → 11:30 15:00

用法:
    python -m datas.fetch_index_min_bars              # 抓上证
    python -m datas.fetch_index_min_bars sh000300     # 指定指数
"""
from __future__ import annotations

import sys
from typing import Optional

import pandas as pd
import requests

from datas.create_database import INDEX_MIN_TABLE, get_db_connection
from tools.log import get_fetch_logger

logger = get_fetch_logger()

BASE_PERIOD = 30            # 入库的基础粒度（分钟）
SUPPORTED_PERIODS = (30, 60, 120)
SINA_URL = ("http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "CN_MarketData.getKLineData")
MAX_DATALEN = 5000          # 实测 5000 根可回溯约 2.5 年
REQUEST_TIMEOUT = 25

# 默认只跟踪上证——分钟数据量比日线大一个量级，按需再扩
DEFAULT_SYMBOLS = ("sh000001",)
MORNING_CUTOFF = "11:30"    # 上午时段的最后一根；之后的算下午


def fetch_min_bars(symbol: str, datalen: int = MAX_DATALEN) -> Optional[pd.DataFrame]:
    """抓 symbol 的 30 分钟 bar。取不到返回 None。"""
    try:
        resp = requests.get(
            SINA_URL,
            params={"symbol": symbol, "scale": BASE_PERIOD, "ma": "no",
                    "datalen": datalen},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        logger.warning(f"{symbol} 分钟线抓取失败: {type(e).__name__}: {e}")
        return None

    if not rows:
        logger.warning(f"{symbol} 分钟线返回空（新浪不支持该 symbol 或该 scale）")
        return None

    df = pd.DataFrame(rows)
    need = {"day", "open", "high", "low", "close", "volume"}
    if not need.issubset(df.columns):
        logger.warning(f"{symbol} 分钟线列不符: {list(df.columns)}")
        return None

    df = df.rename(columns={"day": "dt"})
    df["dt"] = pd.to_datetime(df["dt"])
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    df = (df.dropna(subset=["open", "high", "low", "close"])
            .sort_values("dt").drop_duplicates("dt", keep="last").reset_index(drop=True))
    df["symbol"] = symbol
    df["period"] = BASE_PERIOD
    return df[["symbol", "period", "dt", "open", "high", "low", "close", "volume"]]


def aggregate_bars(df: pd.DataFrame, target_period: int,
                   require_full: bool = False) -> pd.DataFrame:
    """把 30 分钟 bar 合成 60 / 120 分钟。

    **按交易时段分组**（上午 / 下午各自成组），不按固定时间窗口切——理由见模块
    docstring。`require_full=True` 时丢弃不足整组的 bar（半日市会产生这种），
    默认保留并在 `bars` 列里标出实际根数，让调用方自己判断。
    """
    if target_period not in SUPPORTED_PERIODS:
        raise ValueError(f"不支持的周期 {target_period}，可选 {SUPPORTED_PERIODS}")
    if target_period == BASE_PERIOD:
        return df.copy()
    if df.empty:
        return df.copy()

    n = target_period // BASE_PERIOD
    d = df.copy()
    d["dt"] = pd.to_datetime(d["dt"])
    d = d.sort_values("dt").reset_index(drop=True)
    d["_date"] = d["dt"].dt.date
    # 上午 = 结束时刻不晚于 11:30
    d["_am"] = d["dt"].dt.strftime("%H:%M") <= MORNING_CUTOFF
    # 同一 (日期, 时段) 内顺序编号，每 n 根归一组
    d["_i"] = d.groupby(["_date", "_am"]).cumcount()
    d["_g"] = d["_i"] // n

    out = (d.groupby(["_date", "_am", "_g"], sort=True)
             .agg(dt=("dt", "last"), open=("open", "first"), high=("high", "max"),
                  low=("low", "min"), close=("close", "last"),
                  volume=("volume", "sum"), bars=("close", "size"))
             .reset_index(drop=True)
             .sort_values("dt").reset_index(drop=True))

    if require_full:
        out = out[out["bars"] == n].reset_index(drop=True)
    out["symbol"] = df["symbol"].iloc[0] if "symbol" in df.columns else ""
    out["period"] = target_period
    return out[["symbol", "period", "dt", "open", "high", "low", "close",
                "volume", "bars"]]


def save_min_bars_to_database(df: pd.DataFrame) -> int:
    """UPSERT 写入。返回写入行数。"""
    if df is None or df.empty:
        return 0
    write = df.copy()
    write["dt"] = pd.to_datetime(write["dt"]).dt.strftime("%Y-%m-%d %H:%M")

    def upsert(table, cursor, keys, data_iter):
        cols = ", ".join(keys)
        ph = ", ".join(f":{k}" for k in keys)
        sets = ", ".join(f"{c} = excluded.{c}" for c in keys
                         if c not in ("symbol", "period", "dt"))
        sql = (f"INSERT INTO {table.name} ({cols}) VALUES ({ph}) "
               f"ON CONFLICT (symbol, period, dt) DO UPDATE SET {sets};")
        cursor.executemany(sql, ({k: v for k, v in zip(keys, row)} for row in data_iter))

    with get_db_connection() as conn:
        write.to_sql(name=INDEX_MIN_TABLE, con=conn, if_exists="append",
                     index=False, method=upsert, chunksize=2000)
        conn.commit()
    return len(write)


def update_symbol(symbol: str) -> dict:
    """抓一只并入库。返回统计。"""
    df = fetch_min_bars(symbol)
    if df is None or df.empty:
        return {"symbol": symbol, "ok": False, "rows": 0}
    rows = save_min_bars_to_database(df)
    span = f"{df['dt'].iloc[0]:%Y-%m-%d %H:%M} ~ {df['dt'].iloc[-1]:%Y-%m-%d %H:%M}"
    logger.info(f"{symbol}: 抓 {len(df)} 根 30 分钟（{span}），写入 {rows} 行")
    return {"symbol": symbol, "ok": True, "rows": rows,
            "span": span, "last": df["dt"].iloc[-1]}


def update_all(symbols=DEFAULT_SYMBOLS) -> dict:
    out = [update_symbol(s) for s in symbols]
    return {"更新": len(out), "成功": sum(1 for r in out if r["ok"]), "明细": out}


if __name__ == "__main__":
    args = sys.argv[1:] or list(DEFAULT_SYMBOLS)
    for r in update_all(args)["明细"]:
        print(r)
