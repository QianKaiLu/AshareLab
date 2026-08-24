import time
import threading
from typing import Optional

import tushare as ts

from config import TUSHARE_TOKENS


class TokenRateLimiter:
    def __init__(self, max_calls: int, period: int):
        self.max_calls = max_calls
        self.period = period
        self.lock = threading.Lock()
        self.call_timestamps = []

    def try_acquire(self) -> bool:
        """不阻塞地占用一个额度；额度已满返回 False。"""
        with self.lock:
            now = time.time()
            self.call_timestamps = [
                ts for ts in self.call_timestamps if now - ts < self.period
            ]

            if len(self.call_timestamps) < self.max_calls:
                self.call_timestamps.append(now)
                return True
            return False

    def acquire(self):
        while True:
            if self.try_acquire():
                return

            with self.lock:
                if self.call_timestamps:
                    sleep_time = self.period - (time.time() - self.call_timestamps[0])
                else:
                    sleep_time = 0

            time.sleep(max(sleep_time, 1))


# daily 等高频接口：每 token 45 次/分钟
_rate_limiters = {
    token: TokenRateLimiter(max_calls=45, period=60)
    for token in TUSHARE_TOKENS
}

# adj_factor / daily_basic 等低频接口官方限 1 次/分钟，实测该限制按 token 独立计算，
# 所以 N 个 token 每分钟可覆盖 N 个交易日。注意反复顶着限流请求会被惩罚性升级到 1 次/小时。
_slow_limiters = {
    token: TokenRateLimiter(max_calls=1, period=60)
    for token in TUSHARE_TOKENS
}

_tokens = list(TUSHARE_TOKENS)
_global_lock = threading.Lock()
_next_index = 0


def tushare_token_rate_limiter() -> str:
    """为高频接口取一个有额度的 token。

    从上次发牌的位置继续轮询：低频调用远达不到 45 次/分钟的上限，
    若每次都从头扫，永远只会用到 _tokens[0]，多 token 形同虚设。
    """
    global _next_index
    while True:
        with _global_lock:
            total = len(_tokens)
            for offset in range(total):
                index = (_next_index + offset) % total
                token = _tokens[index]

                if _rate_limiters[token].try_acquire():
                    _next_index = (index + 1) % total
                    ts.set_token(token)
                    return token

        time.sleep(1)


def tushare_slow_token() -> Optional[str]:
    """为低频接口取一个本分钟内未用过的 token；全部占满时返回 None，由调用方决定等待。"""
    with _global_lock:
        for token in _tokens:
            if _slow_limiters[token].try_acquire():
                return token
    return None


def test_limiter():
    for i in range(500):
        token = tushare_token_rate_limiter()
        print(f"[{time.strftime('%X')}] Using token: {token}")


if __name__ == "__main__":
    test_limiter()
