"""
工具调用重试机制

提供自动重试能力，应对临时故障（超时、连接失败等）
"""

import time
from typing import Callable, Any
from loguru import logger


class ToolRetryExhaustedError(Exception):
    """重试次数已用尽异常"""
    pass


class ToolRetryWrapper:
    """工具调用重试包装器"""

    def __init__(
        self,
        tool: Callable,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        base_delay: float = 0.5,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    ):
        """
        初始化重试包装器

        Args:
            tool: 要包装的工具函数
            max_retries: 最大重试次数
            backoff_factor: 退避因子（指数退避）
            base_delay: 基础延迟时间（秒）
            retryable_exceptions: 可重试的异常类型
        """
        self.tool = tool
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.base_delay = base_delay
        self.retryable_exceptions = retryable_exceptions
        self.attempt_count = 0
        self.last_error = None

    def execute(self, *args, **kwargs) -> Any:
        """
        执行工具，带重试机制

        Returns:
            工具执行结果

        Raises:
            ToolRetryExhaustedError: 重试次数已用尽
        """
        self.attempt_count = 0

        while self.attempt_count <= self.max_retries:
            try:
                self.attempt_count += 1
                logger.info(f"执行工具（尝试#{self.attempt_count}/{self.max_retries + 1}）")

                result = self.tool(*args, **kwargs)
                logger.info(f"工具执行成功，用时{self.attempt_count}次尝试")

                return result

            except self.retryable_exceptions as e:
                self.last_error = e
                logger.warning(f"工具执行失败（尝试#{self.attempt_count}）: {str(e)}")

                if self.attempt_count > self.max_retries:
                    break

                # 计算延迟时间（指数退避）
                delay = self.base_delay * (self.backoff_factor ** (self.attempt_count - 1))
                logger.info(f"等待{delay:.2f}秒后重试...")
                time.sleep(delay)

            except Exception as e:
                # 不可重试的异常，直接抛出
                logger.error(f"工具执行失败（不可重试的异常）: {str(e)}")
                raise

        # 重试次数用尽
        error_msg = f"工具执行失败，已重试{self.max_retries}次: {str(self.last_error)}"
        logger.error(error_msg)
        raise ToolRetryExhaustedError(error_msg)
