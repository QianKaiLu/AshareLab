from tqdm import tqdm
import pandas as pd
import time
from concurrent.futures import (ProcessPoolExecutor, ThreadPoolExecutor,
                                as_completed)
from datas.fetch_stock_bars import (
    logger,
    fetch_daily_bar_from_akshare,
    fetch_daily_bar_from_sina,
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

# 全量重建专用的进程数。为什么是进程不是线程，见 fetch_full_history_parallel。
FULL_FETCH_WORKERS = 4


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
                    last_adjusted_close=last_adjusted_close,
                    anchor_date=latest_date.strftime("%Y%m%d"))
            except ExDividendDetected as e:
                # 除权使库中整条历史的复权基准失效，补增量会在锚点处留下断层，
                # 必须用 qfq 源从头重取覆盖历史。
                #
                # **必须走新浪，不能用 fetch_daily_bar_from_akshare。** 后者优先东财，
                # 而东财的 qfq 是**减法式**（原价 − 累计分红），分红累计超过早期股价
                # 时整段历史会变负——000708 累计分红 8.74 元 > 2005 年股价 5.23 元，
                # 2005~2018 全段被压成负数并 UPSERT 覆盖了旧数据（2026-09-17 实测）。
                # 新浪是乘法式（× 复权因子），恒为正。
                #
                # 也不用 baostock：虽然同为乘法式且更权威，但它**非线程安全**，
                # 而这里是 3 线程池（FETCH_WORKERS）。
                logger.warning(f"{e}，改走新浪 qfq 全量重取")
                df = fetch_daily_bar_from_sina(code=code, from_date=EARLIEST_DATE)
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


def _fetch_full_history_worker(code: str):
    """子进程入口：抓一只股票的全量前复权历史。

    必须是模块顶层函数（spawn 靠 pickle 传引用），且**只抓不写**——
    写库统一回主进程，沿用本模块「单写者」的原始设计。
    """
    try:
        df = fetch_daily_bar_from_sina(code=code, from_date=EARLIEST_DATE)
    except Exception as e:
        logger.warning(f"{code} 全量抓取异常: {type(e).__name__}: {e}")
        return code, None
    return code, df


def fetch_full_history_parallel(stock_codes, workers: int = FULL_FETCH_WORKERS) -> list:
    """多进程全量抓取（新浪 qfq 全历史），主进程入库。返回失败的代码列表。

    **为什么用进程而不是本模块其它地方的线程**：akshare 的新浪行情接口内部用
    py_mini_racer（V8）算复权因子，而 V8 实例不是线程安全的——多线程并发调用会
    直接 FATAL 掉整个进程（实测 3 线程跑 200 只必崩，栈顶是
    `address_pool_manager.cc(67) Check failed: !pool->IsInitialized()`）。
    每进程独立持有 V8 实例则完全稳定且更快：实测 4 进程单只 0.077s、120/120 成功、
    无限流；对照单线程 0.351s、3 线程直接崩。

    **必须用 spawn，不能用 fork**：fork 会让子进程继承父进程的 V8 状态，
    实测进程池崩掉（BrokenProcessPool）。因此调用方入口脚本要有
    `if __name__ == "__main__"` 保护——spawn 会 `import __main__`，
    没有保护就会递归重跑整个脚本。

    北交所不在此函数的覆盖范围内（新浪不支持 8xxxxx/4xxxxx/92xxxx），
    由调用方另行处理。
    """
    failed: list[str] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_fetch_full_history_worker, code): code
                   for code in stock_codes}
        for future in tqdm(as_completed(futures), total=len(futures)):
            code = futures[future]
            try:
                _, df = future.result()
            except Exception as e:
                logger.error(f"{code} 子进程失败: {type(e).__name__}: {e}")
                failed.append(code)
                continue
            if df is None or df.empty:
                failed.append(code)
                continue
            # 写库返回 0（被闸门拒 / 过滤后为空）同样算失败：
            # 抓到了不等于入库了，只看抓取结果会漏报（重建时实测丢过 3 只）
            if not save_daily_bars_to_database(df):
                logger.error(f"{code}: 抓取成功但未入库")
                failed.append(code)
    return failed


if __name__ == "__main__":
    start_time = time.time()

    failed = fetch_stock_bars_parallel(query_all_stock_code_list(), source="tushare")

    # retry failed ones via akshare
    if failed:
        fetch_stock_bars_parallel(failed, source="akshare")

    total_seconds = time.time() - start_time
    logger.info(f"Used: {total_seconds:.2f} seconds ({timedelta(seconds=total_seconds)})")
