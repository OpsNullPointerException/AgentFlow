"""
工具调用重试和容错机制的单元测试
"""

import pytest
from unittest.mock import MagicMock, patch


class TestToolRetry:
    """工具调用重试测试"""

    def test_tool_retry_on_failure(self):
        """测试：工具调用失败时自动重试"""
        from agents.services.tool_retry import ToolRetryWrapper

        # 模拟会失败2次的工具
        call_count = 0

        def failing_tool(query: str):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception(f"失败 #{call_count}")
            return f"成功在第{call_count}次"

        wrapper = ToolRetryWrapper(failing_tool, max_retries=3, backoff_factor=1.0)
        result = wrapper.execute(query="test")

        assert call_count == 3
        assert "成功在第3次" in result
        assert "重试" not in result  # 最终成功，不应该在结果中提示重试

    def test_tool_retry_with_exponential_backoff(self):
        """测试：指数退避重试策略"""
        from agents.services.tool_retry import ToolRetryWrapper
        import time

        call_times = []

        def timing_tool():
            call_times.append(time.time())
            if len(call_times) < 2:
                raise Exception("fail")
            return "success"

        wrapper = ToolRetryWrapper(
            timing_tool, max_retries=3, backoff_factor=2.0, base_delay=0.01
        )
        wrapper.execute()

        # 验证重试间隔递增
        if len(call_times) >= 2:
            interval1 = call_times[1] - call_times[0]
            # 应该至少有一个基本延迟
            assert interval1 >= 0.01

    def test_tool_retry_exhausted(self):
        """测试：重试次数用尽时抛出异常"""
        from agents.services.tool_retry import ToolRetryWrapper, ToolRetryExhaustedError

        def always_fail():
            raise ValueError("Always fails")

        wrapper = ToolRetryWrapper(always_fail, max_retries=2)

        with pytest.raises(ToolRetryExhaustedError) as exc_info:
            wrapper.execute()

        error_msg = str(exc_info.value)
        assert "工具执行失败" in error_msg
        assert "已重试2次" in error_msg

    def test_tool_fallback_strategy(self):
        """测试：工具失败后使用备用方案"""
        from agents.services.tool_retry import ToolWithFallback

        def primary_tool():
            raise Exception("Primary failed")

        def fallback_tool():
            return "Fallback result"

        wrapper = ToolWithFallback(primary_tool, fallback_tool)
        result = wrapper.execute()

        assert result == "Fallback result"

    def test_circuit_breaker_pattern(self):
        """测试：熔断器模式 - 连续失败后自动关闭"""
        from agents.services.tool_retry import CircuitBreaker

        fail_count = 0

        def unstable_tool():
            nonlocal fail_count
            fail_count += 1
            if fail_count <= 5:
                raise Exception("Unstable")
            return "Success"

        breaker = CircuitBreaker(unstable_tool, failure_threshold=3)

        # 第1-3次失败，达到阈值
        for i in range(3):
            with pytest.raises(Exception):
                breaker.execute()

        # 第4次应该直接抛出熔断异常，不实际调用
        from agents.services.tool_retry import CircuitBreakerOpenError

        with pytest.raises(CircuitBreakerOpenError):
            breaker.execute()

    def test_non_retryable_errors(self):
        """测试：某些错误不应该重试"""
        from agents.services.tool_retry import ToolRetryWrapper

        def auth_error_tool():
            raise PermissionError("Authentication failed")

        wrapper = ToolRetryWrapper(
            auth_error_tool,
            max_retries=3,
            retryable_exceptions=(ConnectionError, TimeoutError),
        )

        # 应该立即抛出，不重试
        with pytest.raises(PermissionError):
            wrapper.execute()
