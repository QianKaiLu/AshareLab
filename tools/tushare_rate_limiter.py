import time
import threading
import tushare as ts
from config import TUSHARE_TOKENS

class TokenRateLimiter:
    def __init__(self, max_calls: int, period: int):
        self.max_calls = max_calls
        self.period = period
        self.lock = threading.Lock()
        self.call_timestamps = []

    def acquire(self):
        while True:
            with self.lock:
                now = time.time()
                self.call_timestamps = [
                    ts for ts in self.call_timestamps if now - ts < self.period
                ]

                if len(self.call_timestamps) < self.max_calls:
                    self.call_timestamps.append(now)
                    return

                sleep_time = self.period - (now - self.call_timestamps[0])

            time.sleep(max(sleep_time, 1))


_rate_limiters = {
    token: TokenRateLimiter(max_calls=45, period=60)
    for token in TUSHARE_TOKENS
}

_tokens = list(TUSHARE_TOKENS)
_global_lock = threading.Lock()


def tushare_token_rate_limiter() -> str:
    while True:
        with _global_lock:
            for token in _tokens:
                limiter = _rate_limiters[token]

                now = time.time()
                recent_calls = [
                    ts for ts in limiter.call_timestamps
                    if now - ts < limiter.period
                ]

                if len(recent_calls) < limiter.max_calls:
                    limiter.acquire()
                    ts.set_token(token)
                    return token
                
        time.sleep(1)


def test_limiter():
    for i in range(500):
        token = tushare_token_rate_limiter()
        print(f"[{time.strftime('%X')}] Using token: {token}")


if __name__ == "__main__":
    test_limiter()
