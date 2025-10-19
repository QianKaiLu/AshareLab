import akshare as ak
import sqlite3
import pandas as pd
from pathlib import Path
import json
from tools.log import get_fetch_logger
from tools.stock_tools import get_exchange_by_code
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

DB_PATH = Path(__file__).parent.parent / "database" / "ashare_data.db"
logger = get_fetch_logger()

FETCH_WORKERS = 20

def fetch_stock_infos(rebuild: bool = True):
    logger.info("Fetching A-share code list...")

    if rebuild:
        from datas.create_database import delete_table_if_exists, create_stock_info_table
        delete_table_if_exists("stock_base_info")
        create_stock_info_table()
        logger.info("Rebuilt stock_base_info table.")

    try:
        code_list_df = ak.stock_info_a_code_name()
    except Exception as e:
        logger.error(f"Fetching failed: {e}")
        return

    if code_list_df.empty:
        logger.error("Fetched data is empty.")
        return

    total_count = len(code_list_df)
    logger.info(f"Fetched {total_count} stocks, starting concurrent fetch...")

    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        futures = [executor.submit(worker_task, row) for row in code_list_df.itertuples()]
        success_count = 0
        for future in tqdm(as_completed(futures), total=total_count):
            success_count += future.result()

    logger.info(f"🎉 Finished: Success={success_count}, Failed={total_count - success_count}")

def worker_task(row_tuple) -> bool:
    """每个线程的任务函数，独立连接数据库"""
    row = row_tuple
    success = False
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        success = fetch_and_save_stock_info(row, cursor)
        conn.commit()
    except Exception as e:
        logger.error(f"Thread failed for {row.code}: {e}")
    finally:
        if conn:
            conn.close()
    return success

def fetch_and_save_stock_info(row, cursor) -> bool:
    code = str(row.code).zfill(6)
    name = row.name
    try:
        exchange_code, exchange_name = get_exchange_by_code(code)
    except ValueError as e:
        logger.error(f"Error fetching exchange code for {code}: {e}")
        return False

    symbol = f"{exchange_code}{code}"

    try:
        xueqiu_info = ak.stock_individual_basic_info_xq(symbol=symbol)
        if xueqiu_info.empty:
            logger.warning(f"No data returned from Xueqiu for {symbol}")
            return False

        required_cols = {'item', 'value'}
        if not required_cols.issubset(xueqiu_info.columns):
            missing = required_cols - set(xueqiu_info.columns)
            logger.error(f"Missing columns {missing} in response for {symbol}")
            return False

        data_dict = dict(zip(xueqiu_info['item'], xueqiu_info['value']))
        affiliate_industry = data_dict.get('affiliate_industry')
        idn_code = None
        idn_name = None
        if isinstance(affiliate_industry, dict):
            idn_code = affiliate_industry.get('ind_code')
            idn_name = affiliate_industry.get('ind_name')

        record = {
            'code': code,
            'exchange_code': exchange_code,
            'exchange_name': exchange_name,
            'name': name,
            'org_name_en': data_dict.get('org_name_en'),
            'org_short_name_en': data_dict.get('org_short_name_en'),
            'full_name': data_dict.get('org_name_cn'),
            'main_operation_business': data_dict.get('main_operation_business'),
            'operating_scope': data_dict.get('operating_scope'),
            'org_introduction': data_dict.get('org_cn_introduction'),
            'classi_name': data_dict.get('classi_name'),
            'list_date': data_dict.get('listed_date'),
            'idn_code': idn_code,
            'idn_name': idn_name,
        }

        sql = """
        INSERT OR REPLACE INTO stock_base_info (
            code, exchange_code, exchange_name, name, org_name_en, org_short_name_en,
            full_name, main_operation_business, operating_scope,
            org_introduction, classi_name, list_date, idn_code, idn_name
        ) VALUES (
            :code, :exchange_code, :exchange_name, :name, :org_name_en, :org_short_name_en,
            :full_name, :main_operation_business, :operating_scope,
            :org_introduction, :classi_name, :list_date, :idn_code, :idn_name
        )
        """
        cursor.execute(sql, record)  # ⚠️ 注意：这行在多线程中不能直接用同一个 cursor！

        return True

    except Exception as e:
        logger.error(f"Failed to process Xueqiu info for {symbol}: {e}")
        return False

if __name__ == "__main__":
    fetch_stock_infos(rebuild=True)