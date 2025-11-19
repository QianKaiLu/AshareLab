import time
import threading

class TushareRateLimiter:
    def __init__(self, max_calls: int, period: int = 60):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = threading.Lock()

    def acquire(self, block: bool = True) -> bool:
        with self.lock:
            now = time.time()
            self.calls = [t for t in self.calls if now - t < self.period]

            if len(self.calls) < self.max_calls:
                self.calls.append(now)
                return True
            else:
                oldest_call = self.calls[0]
                wait_time = self.period - (now - oldest_call)

                if not block:
                    return False
                if wait_time > 0:
                    time.sleep(wait_time)

                now = time.time()
                self.calls = [t for t in self.calls if now - t < self.period]
                self.calls.append(now)
                return True

_tushare_limiter = None
_limiter_lock = threading.Lock()

def get_tushare_limiter(max_calls: int = 48, period: int = 60) -> TushareRateLimiter:
    global _tushare_limiter
    with _limiter_lock:
        if _tushare_limiter is None:
            _tushare_limiter = TushareRateLimiter(max_calls=max_calls, period=period)
    return _tushare_limiter
