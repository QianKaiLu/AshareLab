from tqdm import tqdm
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datas.fetch_stock_bars import (
    logger,
    fetch_daily_bar_from_akshare,
    fetch_daily_bar_from_tushare,
    save_daily_bars_to_database,
    ExDividendDetected,
)
from queue import Queue
import threading
from datetime import datetime, timedelta
from datas.query_stock import get_latest_date_by_code, query_all_stock_code_list, query_latest_bars
from datas.create_database import DB_PATH, DAILY_BAR_TABLE, EARLIEST_DATE, get_db_connection
from tools.stock_tools import latest_trade_day

# 东财 / tushare 都扛不住高并发，8 workers 无间隔会把接口打崩（RemoteDisconnected）
REQUEST_DELAY = 0.5  # seconds between requests to avoid burst rate limits
FETCH_WORKERS = 3


def fetch_stock_bars_parallel(stock_codes, source: str = "tushare") -> list:
    """
    并行抓取股票日线并写入库。返回失败的股票代码列表，供下一轮兜底重试。
    source: "tushare"（默认，增量更新主源）/ "akshare"（兜底）。
    """
    result_queue = Queue(maxsize=50)
    stop_event = threading.Event()

    writer_thread = threading.Thread(target=database_writer, args=(result_queue, stop_event))
    writer_thread.start()

    failed_codes = []
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
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
                else:
                    failed_codes.append(code)
            except Exception as e:
                logger.error(f"Failed to fetch {code}: {e}")
                failed_codes.append(code)
        logger.info(f"Fetched {success_count}/{all_count} stocks")

    result_queue.join()
    stop_event.set()
    writer_thread.join()
    return failed_codes


def worker_fetch_stock_and_queue(code: str, result_queue: Queue, source: str = "tushare") -> bool:
    latest_date = get_latest_date_by_code(code)
    if latest_date is not None:
        to_date = latest_trade_day()
        if latest_date.date() >= to_date:
            return True

    # 注意：get_latest_date_by_code 对无数据的股票返回 EARLIEST_DATE 而非 None，
    # 所以「全量缺口」必须以实际查库为准
    last_bars = query_latest_bars(code, n=1)
    has_data = not last_bars.empty

    if not has_data and source != "akshare":
        # 全量缺口：库中无锚点，tushare 缩放方案不可用，只能走 qfq 源（akshare）。
        # tushare 轮跳过，留给 akshare 轮统一补。
        return False

    # 打散突发请求，避免瞬间压垮接口（仅对真正要发请求的股票）
    time.sleep(REQUEST_DELAY)

    try:
        df = None
        if not has_data:
            df = fetch_daily_bar_from_akshare(code=code, from_date=EARLIEST_DATE)
        elif source == "akshare":
            df = fetch_daily_bar_from_akshare(code=code, from_date=latest_date.strftime("%Y%m%d"))
        else:
            last_adjusted_close = float(last_bars['close'].iloc[-1])
            try:
                df = fetch_daily_bar_from_tushare(
                    code=code, from_date=latest_date.strftime("%Y%m%d"),
                    last_adjusted_close=last_adjusted_close)
            except ExDividendDetected as e:
                # 除权使库中整条历史的复权基准失效，补增量会在锚点处留下断层，
                # 必须用 qfq 源从头重取覆盖历史。
                logger.warning(f"{e}，改走 akshare qfq 全量重取")
                df = fetch_daily_bar_from_akshare(code=code, from_date=EARLIEST_DATE)
        if df is not None and not df.empty:
            result_queue.put(df)
            return True
        return False
    except Exception as e:
        logger.error(f"Error fetching {code}: {e}")
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
    start_time = time.time()

    failed = fetch_stock_bars_parallel(query_all_stock_code_list(), source="tushare")

    # retry failed ones via akshare
    if failed:
        fetch_stock_bars_parallel(failed, source="akshare")

    total_seconds = time.time() - start_time
    logger.info(f"Used: {total_seconds:.2f} seconds ({timedelta(seconds=total_seconds)})")
