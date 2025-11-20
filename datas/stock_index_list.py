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

DATABASE_DIR = Path(__file__).parent.parent / "database"

hs300_list_path = DATABASE_DIR / "hs300_stock_list.csv"
csi500_list_path = DATABASE_DIR / "csi500_stock_list.csv"
dummy_path = DATABASE_DIR / ".dummy"

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


def fetch_index_stock_list():
    """Fetch and save the latest HS300 and CSI500 constituent stock lists.

    Retrieves data via akshare, renames columns for consistency, saves to CSV,
    and updates a dummy file's timestamp on success.
    """
    done = True
    column_mapping = {
        "品种代码": "code",
        "品种名称": "name",
        "纳入日期": "list_date"
    }
    
    logger.info("Updating HS300 lists...")
    df_300 = ak.index_stock_cons(symbol="399300")
    if not df_300.empty:
        df_300 = df_300.rename(columns=column_mapping)
        df_300.to_csv(hs300_list_path, index=False)
        logger.info(f"Done with {len(df_300)} entries.")
    else:
        done = False

    logger.info("Updating CSI500 lists...")
    df_500 = ak.index_stock_cons(symbol="399905")
    if not df_500.empty:
        df_500 = df_500.rename(columns=column_mapping)
        df_500.to_csv(csi500_list_path, index=False)
        logger.info(f"Done with {len(df_500)} entries.")
    else:
        done = False
        
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


if __name__ == "__main__":
    update_index_stock_list(force_update=True)