from tqdm import tqdm
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datas.fetch_stock_bars import MARKED_CLOSE_HOUR, logger, fetch_daily_bar_from_akshare, fetch_daily_bar_from_tushare, save_daily_bars_to_database
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import threading
from datas.stock_index_list import hs300_code_list, csi500_code_list
from datetime import datetime, timedelta
from datas.query_stock import get_latest_date_with_data, query_all_stock_code_list
from datas.create_database import DB_PATH, DAILY_BAR_TABLE, EARLIEST_DATE, get_db_connection
import tushare as ts

def fetch_stock_bars_parallel(stock_codes: pd.Series, source: str = "akshare"):
    result_queue = Queue(maxsize=20)
    stop_event = threading.Event()

    writer_thread = threading.Thread(target=database_writer, args=(result_queue, stop_event))
    writer_thread.start()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(worker_fetch_stock_and_queue, code, result_queue, source): code
            for code in stock_codes
        }
        success_count = 0
        all_count = len(futures)
        for future in tqdm(as_completed(futures.keys()), total=len(futures)):
            code = futures[future]
            try:
                if future.result():
                    success_count += 1
            except Exception as e:
                logger.error(f"Failed to fetch {code}: {e}")       
        logger.info(f"🎉 Fetched {success_count}/{all_count} stocks' daily bars.")
        
    result_queue.join()
    stop_event.set()
    writer_thread.join()

def worker_fetch_stock_and_queue(code: str, result_queue: Queue, source: str = "akshare") -> bool:
    latest_date = get_latest_date_with_data(code)
    previous_day = pd.to_datetime(EARLIEST_DATE)

    if latest_date is not None:
        now = datetime.now()
        if now.hour >= MARKED_CLOSE_HOUR:
            to_date = now
        else:
            to_date = (now - timedelta(days=1))

        if latest_date.date() >= to_date.date():
            logger.info(f"No update needed for {code}, latest date {latest_date.date()} is up-to-date.")
            return True
        previous_day = latest_date - pd.Timedelta(days=30)
        
    try:
        df = None
        if source == "akshare":
            df = fetch_daily_bar_from_akshare(code=code, from_date=previous_day.strftime("%Y%m%d"))
        elif source == "tushare":
            df = fetch_daily_bar_from_tushare(code=code, from_date=previous_day.strftime("%Y%m%d"))
        if df is not None and not df.empty:
            result_queue.put(df)
            return True
        return False
    except Exception as e:
        logger.error(f"Error fetching data for {code}: {e}")
        return False

def database_writer(result_queue: Queue, stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            df = result_queue.get(timeout=0.5)
            try:
                save_daily_bars_to_database(df)
            except Exception as e:
                logger.error(f"Failed to save data to database: {e}")
            finally:
                result_queue.task_done()
        except Exception:
            continue

    while True:
        try:
            df = result_queue.get_nowait()
            try:
                save_daily_bars_to_database(df)
            except Exception as e:
                logger.error(f"Failed to save leftover data: {e}")
            finally:
                result_queue.task_done()
        except Exception:
            break

if __name__ == "__main__":
    fetch_stock_bars_parallel(query_all_stock_code_list(), source="tushare")