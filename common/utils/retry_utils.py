"""
重试工具，提供错误重试装饰器和相关功能
"""

import time
import functools
from typing import Callable, Any, List, Optional, Type
from loguru import logger


def retry(
    max_tries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: List[Type[Exception]] = None,
    on_retry: Optional[Callable] = None,
):
    """
    重试装饰器

    Args:
        max_tries: 最大重试次数，包括第一次尝试
        delay: 首次重试前等待的秒数
        backoff_factor: 退避因子，每次重试等待时间 = delay * (backoff_factor ^ (retry_count - 1))
        exceptions: 需要捕获的异常类型列表，默认捕获所有异常
        on_retry: 重试前调用的回调函数，参数为 (exception, try_number, max_tries)

    Returns:
        装饰器函数
    """
    if exceptions is None:
        exceptions = [Exception]

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tries = 0
            _delay = delay

            while tries < max_tries:
                tries += 1

                try:
                    return func(*args, **kwargs)
                except tuple(exceptions) as e:
                    if tries == max_tries:
                        logger.error(f"达到最大重试次数 {max_tries}，最终失败: {str(e)}")
                        raise

                    if on_retry:
                        on_retry(e, tries, max_tries)

                    logger.warning(f"尝试 {tries}/{max_tries} 失败: {str(e)}，将在 {_delay:.2f} 秒后重试")
                    time.sleep(_delay)
                    _delay *= backoff_factor

            # 这里实际上不应该到达，因为如果所有重试都失败了，会在上面的异常处理中抛出
            return None

        return wrapper

    return decorator


def log_retry(exception: Exception, try_number: int, max_tries: int) -> None:
    """重试前的日志记录回调函数"""
    logger.warning(f"操作失败 (尝试 {try_number}/{max_tries}): {str(exception)}")


class RetryableError(Exception):
    """可重试的错误基类"""

    pass
