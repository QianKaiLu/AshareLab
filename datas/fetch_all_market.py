import akshare as ak
import sqlite3
import pandas as pd
from pathlib import Path
from tools.log import get_fetch_logger
from tools.stock_tools import get_exchange_by_code
from tools.tools import ms_timestamp_to_date
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Any
from datetime import datetime, timedelta
from datas.create_database import DB_PATH, DAILY_BAR_TABLE, EARLIEST_DATE, delete_table_if_exists, create_daily_bar_table
from datas.query_stock import query_daily_bars, query_latest_bars, get_latest_date_with_data
from tools.export import export_bars_to_csv
import time
from contextlib import closing
from ai.ai_kbar_analyses import analyze_kbar_data_openai
from tools.markdown_lab import save_md_to_file_name, render_markdown_to_image_file_name
from datas.query_stock import get_stock_info_by_code
from datas.fetch_stock_bars import MARKED_CLOSE_HOUR, logger, fetch_daily_bar_from_akshare

from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import threading

def worker_fetch_and_queue(code: str, result_queue: Queue):
    """只负责拉数据，不入库"""
    df = fetch_daily_bar_from_akshare(code)
    if df is not None and not df.empty:
        result_queue.put(df)

def database_writer(result_queue: Queue, stop_event: threading.Event):
    """单独线程串行写入 DB"""
    while not stop_event.is_set() or not result_queue.empty():
        try:
            df = result_queue.get(timeout=1)
            save_daily_bars_to_database(df)  # 你的入库函数
            result_queue.task_done()
        except Exception:
            break

# 主流程
def fetch_all_stocks_parallel(stock_codes: list):
    result_queue = Queue(maxsize=20)  # 限流防爆内存
    stop_event = threading.Event()

    # 启动写入线程（唯一写入者）
    writer_thread = threading.Thread(target=database_writer, args=(result_queue, stop_event))
    writer_thread.start()

    # 多线程拉数据
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(worker_fetch_and_queue, code, result_queue): code
            for code in stock_codes
        }
        for future in tqdm(as_completed(futures), total=len(futures)):
            code = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error(f"Failed to fetch {code}: {e}")

    # 等待队列清空
    result_queue.join()
    stop_event.set()
    writer_thread.join()



