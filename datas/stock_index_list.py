import akshare as ak
import pandas as pd
from pathlib import Path
from tools.log import get_fetch_logger
from tools.stock_tools import get_exchange_by_code
from tools.times import ms_timestamp_to_date
from typing import Optional, Any
from datetime import datetime, timedelta
from tools.export import export_bars_to_csv
from datas.query_stock import get_stock_info_by_code
from tools.stock_tools import to_std_code

logger = get_fetch_logger()

# 指数成分股名单属于参考数据，不入库；放 datas/index_lists/ 并纳入 git
# （database/ 整个被 gitignore，且 30 天刷新的名单有版本回溯价值）
INDEX_LIST_DIR = Path(__file__).parent / "index_lists"

hs300_list_path = INDEX_LIST_DIR / "hs300_stock_list.csv"
csi500_list_path = INDEX_LIST_DIR / "csi500_stock_list.csv"
csi2000_list_path = INDEX_LIST_DIR / "csi2000_stock_list.csv"
csi_a500_list_path = INDEX_LIST_DIR / "csi_a500_stock_list.csv"
dummy_path = INDEX_LIST_DIR / ".dummy"

update_interval_days = 30  # update every 30 days

def needs_update(file_path: Path) -> bool:
    """Check if a file needs to be updated based on its modification time.

    Args:
        file_path: Path to the file to check.

    Returns:
        True if the file doesn't exist or was last modified more than 
        `update_interval_days` ago; False otherwise.
    """
    if not file_path.exists():
        return True
    last_modified_time = datetime.fromtimestamp(file_path.stat().st_mtime)
    if datetime.now() - last_modified_time > timedelta(days=update_interval_days):
        return True
    return False


def update_index_stock_list(force_update: bool = False):
    """Update index constituent stock lists (HS300 & CSI500) if needed.

    Uses a dummy file's timestamp to track last update time. Skips update
    if within the interval unless `force_update` is True.

    Args:
        force_update: If True, bypass the time check and fetch fresh data.
    """
    if force_update or needs_update(dummy_path):
        fetch_index_stock_list()
    else:
        logger.info("Index stock lists are up to date. No update needed.")


# 指数代码 → (输出路径, 期望成分数)。期望数用于校验抓取完整性。
INDEX_SPECS = (
    ("000300", hs300_list_path, 300, "沪深300"),
    ("000905", csi500_list_path, 500, "中证500"),
    ("932000", csi2000_list_path, 2000, "中证2000"),
    ("000510", csi_a500_list_path, 500, "中证A500"),
)


def fetch_index_stock_list():
    """抓取并保存指数成分名单。数据源是**中证指数公司官方**（csindex）。

    **不要换回 `ak.index_stock_cons()`。** 那个接口（东财源）返回的行数看着对
    （沪深300 给 300 行、中证2000 给 2000 行），但**大量重复、同时漏掉真实成分**：
    2026-09-17 实测，沪深300 的 300 行里只有 287 个唯一代码，中证2000 的 2000 行里
    只有 699 个唯一代码。而官方源给出的 300 / 2000 只，**库里全都有行情**。

    这个缺陷静默影响过多个下游：创 20 日新高的分母（曾报 287/699 而非 300/2000）、
    `hunter/hunt_pools.py` 的三个选股池、广度分析与回测。

    写成 `code,name,list_date` 三列，其中 `list_date` 是**名单快照日期**——官方源不
    提供「纳入日期」，所以这个字段的语义与旧版不同。消费方（`*_code_list()`、
    `market/fetch.py:_index_members`）只读 `code` 列。
    """
    done = True
    for symbol, path, expect, name in INDEX_SPECS:
        logger.info(f"Updating {name} lists...")
        try:
            df = ak.index_stock_cons_csindex(symbol=symbol)
        except Exception as e:
            logger.error(f"{name} 抓取失败: {type(e).__name__}: {e}")
            done = False
            continue

        if df is None or df.empty or "成分券代码" not in df.columns:
            logger.error(f"{name} 返回为空或列不符: {list(df.columns) if df is not None else None}")
            done = False
            continue

        out = pd.DataFrame({
            "code": df["成分券代码"].astype(str).str.zfill(6),
            "name": df["成分券名称"].astype(str),
            "list_date": df["日期"].astype(str) if "日期" in df.columns else "",
        })
        uniq = out["code"].nunique()
        if uniq < expect:
            # 宁可整批放弃也不要写一份残缺名单——它会被当成权威数据用很久
            logger.error(f"{name} 只取到 {uniq} 个唯一代码（期望 {expect}），放弃本次写入")
            done = False
            continue

        out.to_csv(path, index=False)
        logger.info(f"Done with {len(out)} rows / {uniq} unique codes.")

    if done:
        # Update the dummy file's timestamp to mark successful update
        dummy_path.touch()


def hs300_code_list() -> pd.Series:
    """Get a pandas Series of HS300 constituent stock codes.

    Triggers an update if the local list is outdated or missing.

    Returns:
        A Series containing stock codes (e.g., '600000'), or empty Series if failed.
    """
    update_index_stock_list()
    if hs300_list_path.exists():
        df = pd.read_csv(hs300_list_path, dtype={"code": "string"})
        return df["code"].map(to_std_code)
    else:
        logger.warning("HS300 stock list file does not exist.")
        return pd.Series()


def csi500_code_list() -> pd.Series:
    """Get a pandas Series of CSI500 constituent stock codes.

    Triggers an update if the local list is outdated or missing.

    Returns:
        A Series containing stock codes (e.g., '600000'), or empty Series if failed.
    """
    update_index_stock_list()
    if csi500_list_path.exists():
        df = pd.read_csv(csi500_list_path, dtype={"code": "string"})
        return df["code"].map(to_std_code)
    else:
        logger.warning("CSI500 stock list file does not exist.")
        return pd.Series()

def csi2000_code_list() -> pd.Series:
    """Get a pandas Series of CSI2000 constituent stock codes.

    Triggers an update if the local list is outdated or missing.

    Returns:
        A Series containing stock codes (e.g., '600000'), or empty Series if failed.
    """
    update_index_stock_list()
    if csi2000_list_path.exists():
        df = pd.read_csv(csi2000_list_path, dtype={"code": "string"})
        return df["code"].map(to_std_code)
    else:
        logger.warning("CSI2000 stock list file does not exist.")
        return pd.Series()

def csi_a500_code_list() -> pd.Series:
    """Get a pandas Series of CSIA500 constituent stock codes.

    Triggers an update if the local list is outdated or missing.

    Returns:
        A Series containing stock codes (e.g., '600000'), or empty Series if failed.
    """
    update_index_stock_list()
    if csi_a500_list_path.exists():
        df = pd.read_csv(csi_a500_list_path, dtype={"code": "string"})
        return df["code"].map(to_std_code)
    else:
        logger.warning("CSIA500 stock list file does not exist.")
        return pd.Series()

if __name__ == "__main__":
    update_index_stock_list(force_update=True)