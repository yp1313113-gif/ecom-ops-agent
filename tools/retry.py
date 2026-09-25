"""指数退避重试 + 轻量熔断器。

面试口径：
    "给工具调用加上'二次重试 + 熔断降级'机制，
     让外部 API 不稳时不直接抛出崩溃给用户。"
"""
from __future__ import annotations

import time
import logging
from functools import wraps
from typing import Callable

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
):
    """指数退避重试装饰器。

    Example:
        @retry_with_backoff(max_retries=2, initial_delay=0.1)
        def fetch_remote_price(...): ...
    """
    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_err = None
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except retry_on as e:
                    last_err = e
                    if attempt == max_retries - 1:
                        logger.warning(f"[{fn.__name__}] 重试 {max_retries} 次仍失败：{e}")
                        break
                    logger.info(f"[{fn.__name__}] 第 {attempt + 1} 次失败 {e}，{delay:.2f}s 后重试")
                    time.sleep(delay)
                    delay *= backoff_factor
            raise last_err
        return wrapper
    return decorator


class CircuitBreaker:
    """简单熔断器：连续失败 N 次后熔断 M 秒，期间短路直接抛错。

    用法：
        cb = CircuitBreaker(threshold=3, reset_seconds=10)
        if cb.allow():
            try:
                ...  # 真实调用
                cb.record_success()
            except Exception:
                cb.record_failure()
                raise
    """

    def __init__(self, threshold: int = 3, reset_seconds: float = 10.0):
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self._fail_count = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if time.time() - self._opened_at > self.reset_seconds:
            # 半开：放一枪试试
            self._opened_at = None
            self._fail_count = 0
            return True
        return False

    def record_success(self) -> None:
        self._fail_count = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._fail_count += 1
        if self._fail_count >= self.threshold:
            self._opened_at = time.time()
            logger.warning(f"熔断器已触发，将在 {self.reset_seconds}s 后半开")
