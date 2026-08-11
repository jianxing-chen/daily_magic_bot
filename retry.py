"""
通用指数退避重试工具
统一 Gemini 链 / DeepSeek / SMTP 三处重试逻辑
"""
import logging
import time
from typing import Callable, List

logger = logging.getLogger(__name__)


class RetryableError(Exception):
    """标记异常：临时错误，retry_with_backoff 会退避重试

    各调用方将自身识别出的临时错误（API 503/429、HTTP 5xx、
    SMTP 连接失败等）包装为此异常抛出；永久错误直接抛出原始异常。
    """


def retry_with_backoff(
    fn: Callable,
    waits: List[int],
    label: str = '',
    retryable: Callable[[Exception], bool] = None
):
    """带指数退避的重试执行

    共尝试 len(waits) + 1 次：每次失败且异常被判定为可重试时，
    按 waits 中的秒数退避后重试；重试耗尽或非可重试异常时抛出。

    Args:
        fn: 无参可调用对象，成功时返回结果
        waits: 各次重试前的等待秒数列表（如 [30, 60] 表示共尝试 3 次）
        label: 日志标签（如模型名/服务名）
        retryable: 可重试判断谓词，默认仅 RetryableError 可重试

    Returns:
        fn() 的返回值

    Raises:
        最后一次可重试异常（重试耗尽）或首次非可重试异常
    """
    if retryable is None:
        def retryable(e):
            return isinstance(e, RetryableError)

    attempts = len(waits) + 1
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as e:
            if not retryable(e):
                raise
            if attempt < attempts - 1:
                wait_time = waits[attempt]
                logger.warning(f"[{label}] 临时错误 (尝试 {attempt + 1}/{attempts}): {e}")
                logger.warning(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                logger.error(f"[{label}] 重试耗尽 ({attempts} 次)，抛出异常")
                raise
