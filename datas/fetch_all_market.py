from tqdm import tqdm
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datas.fetch_stock_bars import MARKED_CLOSE_HOUR, logger, fetch_daily_bar_from_akshare, save_daily_bars_to_database
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import threading
from datas.stock_index_list import hs300_code_list

def fetch_stock_bars_parallel(stock_codes: pd.Series):
    result_queue = Queue(maxsize=20)
    stop_event = threading.Event()

    writer_thread = threading.Thread(target=database_writer, args=(result_queue, stop_event))
    writer_thread.start()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(worker_fetch_stock_and_queue, code, result_queue): code
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

def worker_fetch_stock_and_queue(code: str, result_queue: Queue) -> bool:
    try:
        df = fetch_daily_bar_from_akshare(code)
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
        except Exception:
            continue
        
        try:
            save_daily_bars_to_database(df)
        finally:
            result_queue.task_done()

    while not result_queue.empty():
        try:
            df = result_queue.get_nowait()
            save_daily_bars_to_database(df)
            result_queue.task_done()
        except Exception:
            break

if __name__ == "__main__":
    fetch_stock_bars_parallel(hs300_code_list())