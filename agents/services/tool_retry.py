"""
工具调用重试和容错机制

提供自动重试、降级、熔断等容错能力
"""

import time
from typing import Callable, Any, Optional, Type, Tuple
from functools import wraps
from enum import Enum
from loguru import logger


class CircuitBreakerState(Enum):
    """熔断器状态"""

    CLOSED = "closed"  # 正常
    OPEN = "open"  # 熔断
    HALF_OPEN = "half_open"  # 半开（测试恢复）


class ToolRetryExhaustedError(Exception):
    """重试次数已用尽异常"""

    pass


class CircuitBreakerOpenError(Exception):
    """熔断器打开异常"""

    pass


class ToolRetryWrapper:
    """工具调用重试包装器"""

    def __init__(
        self,
        tool: Callable,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        base_delay: float = 0.5,
        retryable_exceptions: Tuple[Type[Exception], ...] = (
            Exception,
        ),  # 哪些异常可以重试
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
                logger.error(f"不可重试的异常: {e}")
                raise

        # 重试已用尽
        error_msg = (
            f"工具执行失败，已重试{self.max_retries}次，"
            f"最后错误: {str(self.last_error)}"
        )
        logger.error(error_msg)
        raise ToolRetryExhaustedError(error_msg)


class ToolWithFallback:
    """带降级方案的工具"""

    def __init__(
        self,
        primary_tool: Callable,
        fallback_tool: Optional[Callable] = None,
        fallback_value: Optional[Any] = None,
    ):
        """
        初始化降级工具

        Args:
            primary_tool: 主工具
            fallback_tool: 降级工具（主工具失败时调用）
            fallback_value: 默认返回值（如果没有降级工具）
        """
        self.primary_tool = primary_tool
        self.fallback_tool = fallback_tool
        self.fallback_value = fallback_value

    def execute(self, *args, **kwargs) -> Any:
        """
        执行工具，失败时使用降级方案

        Returns:
            主工具结果或降级结果
        """
        try:
            logger.info("执行主工具")
            result = self.primary_tool(*args, **kwargs)
            return result

        except Exception as e:
            logger.warning(f"主工具失败: {e}，尝试使用降级方案")

            if self.fallback_tool:
                try:
                    logger.info("执行降级工具")
                    result = self.fallback_tool(*args, **kwargs)
                    logger.info("降级工具成功")
                    return result
                except Exception as fallback_error:
                    logger.error(f"降级工具也失败: {fallback_error}")

            if self.fallback_value is not None:
                logger.info(f"使用默认返回值: {self.fallback_value}")
                return self.fallback_value

            raise


class CircuitBreaker:
    """熔断器模式 - 保护故障工具"""

    def __init__(
        self,
        tool: Callable,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ):
        """
        初始化熔断器

        Args:
            tool: 要保护的工具
            failure_threshold: 失败次数阈值，超过则打开熔断器
            recovery_timeout: 恢复超时时间（秒）
        """
        self.tool = tool
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.success_count = 0

    def execute(self, *args, **kwargs) -> Any:
        """
        执行工具，使用熔断保护

        Raises:
            CircuitBreakerOpenError: 熔断器已打开
        """
        # 检查是否应该半开（尝试恢复）
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                logger.info("熔断器进入半开状态，尝试恢复")
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
            else:
                raise CircuitBreakerOpenError(
                    f"熔断器已打开，工具不可用。"
                    f"请在{self.recovery_timeout}秒后重试"
                )

        try:
            result = self.tool(*args, **kwargs)

            # 成功
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= 2:
                    logger.info("熔断器恢复，回到正常状态")
                    self.state = CircuitBreakerState.CLOSED
                    self.failure_count = 0

            return result

        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            logger.warning(f"工具执行失败 (计数: {self.failure_count}/{self.failure_threshold}): {e}")

            if self.failure_count >= self.failure_threshold:
                logger.error("失败次数达到阈值，打开熔断器")
                self.state = CircuitBreakerState.OPEN

            raise

    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试恢复"""
        if self.last_failure_time is None:
            return True

        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.recovery_timeout

    def get_state(self) -> dict:
        """获取熔断器状态"""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time,
        }


def retry_tool(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    工具函数装饰器 - 为任何函数添加重试能力

    使用示例：
        @retry_tool(max_retries=3)
        def my_tool(query):
            # 可能失败的操作
            return result
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retry_wrapper = ToolRetryWrapper(
                lambda: func(*args, **kwargs),
                max_retries=max_retries,
                backoff_factor=backoff_factor,
                retryable_exceptions=retryable_exceptions,
            )
            return retry_wrapper.execute()

        return wrapper

    return decorator
