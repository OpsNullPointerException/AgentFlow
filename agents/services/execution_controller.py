"""
Agent执行控制器 - 增强的错误恢复和容错机制
"""

import time
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum
from loguru import logger


class ExecutionStrategy(Enum):
    """执行策略"""

    AGGRESSIVE = "aggressive"  # 遇到错误直接失败
    CONSERVATIVE = "conservative"  # 重试多次，使用降级方案
    ADAPTIVE = "adaptive"  # 根据错误类型动态调整


class ErrorRecoveryAction(Enum):
    """错误恢复行动"""

    RETRY = "retry"  # 重试
    FALLBACK = "fallback"  # 降级
    SKIP = "skip"  # 跳过（继续下一步）
    ABORT = "abort"  # 中止


@dataclass
class ExecutionConfig:
    """Agent执行配置"""

    max_iterations: int = 10
    timeout: float = 120.0
    strategy: ExecutionStrategy = ExecutionStrategy.CONSERVATIVE

    # 工具相关
    tool_max_retries: int = 3
    tool_timeout: float = 30.0
    tool_fallback_enabled: bool = True

    # LLM相关
    llm_max_retries: int = 2
    llm_timeout: float = 30.0

    # 恢复相关
    auto_recovery_enabled: bool = True
    circuit_breaker_threshold: int = 5
    context_reset_on_failure: bool = True


class ExecutionController:
    """Agent执行控制器 - 管理执行、错误恢复、超时等"""

    def __init__(self, config: Optional[ExecutionConfig] = None):
        """
        初始化执行控制器

        Args:
            config: 执行配置
        """
        self.config = config or ExecutionConfig()
        self.iteration_count = 0
        self.error_count = 0
        self.start_time: Optional[float] = None
        self.recovery_log: list = []

    def is_timeout(self) -> bool:
        """检查是否超时"""
        if not self.start_time:
            return False

        elapsed = time.time() - self.start_time
        is_timeout = elapsed > self.config.timeout

        if is_timeout:
            logger.warning(f"执行超时: {elapsed:.2f}s > {self.config.timeout}s")

        return is_timeout

    def can_continue(self) -> bool:
        """检查是否可以继续执行"""
        # 检查迭代次数
        if self.iteration_count >= self.config.max_iterations:
            logger.warning(
                f"达到最大迭代次数: {self.iteration_count}/{self.config.max_iterations}"
            )
            return False

        # 检查超时
        if self.is_timeout():
            return False

        # 根据策略检查错误计数
        if self.config.strategy == ExecutionStrategy.AGGRESSIVE:
            if self.error_count > 0:
                logger.warning("激进策略：检测到错误，停止执行")
                return False

        elif self.config.strategy == ExecutionStrategy.CONSERVATIVE:
            if self.error_count >= self.config.circuit_breaker_threshold:
                logger.warning(
                    f"保守策略：错误次数过多({self.error_count})，停止执行"
                )
                return False

        return True

    def handle_error(
        self,
        error: Exception,
        context: Dict[str, Any],
        recovery_options: Optional[Dict[str, Any]] = None,
    ) -> ErrorRecoveryAction:
        """
        处理错误，决定恢复行动

        Args:
            error: 发生的异常
            context: 执行上下文（工具名、输入等）
            recovery_options: 恢复选项

        Returns:
            建议的恢复行动
        """
        self.error_count += 1
        recovery_options = recovery_options or {}

        logger.error(
            f"执行错误 (计数: {self.error_count}/{self.config.circuit_breaker_threshold}): "
            f"{type(error).__name__}: {str(error)[:100]}"
        )

        # 根据错误类型决定恢复策略
        action = self._determine_recovery_action(error, context)

        # 记录恢复日志
        self.recovery_log.append(
            {
                "iteration": self.iteration_count,
                "error_type": type(error).__name__,
                "error_msg": str(error)[:200],
                "context": context,
                "action": action.value,
            }
        )

        logger.info(f"错误恢复行动: {action.value}")

        return action

    def _determine_recovery_action(
        self, error: Exception, context: Dict[str, Any]
    ) -> ErrorRecoveryAction:
        """根据错误类型确定恢复行动"""

        error_type = type(error).__name__
        is_tool_error = context.get("error_location") == "tool"
        is_llm_error = context.get("error_location") == "llm"

        # 超时错误
        if "Timeout" in error_type or "timeout" in str(error).lower():
            logger.info("超时错误 → 重试")
            return ErrorRecoveryAction.RETRY

        # 认证错误（不应重试）
        if isinstance(error, (PermissionError, ValueError)):
            if "auth" in str(error).lower() or "permission" in str(error).lower():
                logger.info("认证错误 → 中止")
                return ErrorRecoveryAction.ABORT

        # 工具错误
        if is_tool_error:
            if self.config.tool_fallback_enabled:
                logger.info("工具错误 → 尝试降级")
                return ErrorRecoveryAction.FALLBACK
            else:
                logger.info("工具错误 → 重试")
                return ErrorRecoveryAction.RETRY

        # LLM错误
        if is_llm_error:
            logger.info("LLM错误 → 重试")
            return ErrorRecoveryAction.RETRY

        # 默认：根据策略决定
        if self.config.strategy == ExecutionStrategy.AGGRESSIVE:
            return ErrorRecoveryAction.ABORT
        else:
            return ErrorRecoveryAction.RETRY

    def execute_with_recovery(
        self,
        operation: Callable,
        operation_name: str,
        context: Optional[Dict[str, Any]] = None,
        max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        执行操作，带自动错误恢复

        Args:
            operation: 要执行的操作（返回结果）
            operation_name: 操作名称
            context: 执行上下文
            max_retries: 最大重试次数

        Returns:
            执行结果 {'success': bool, 'result': Any, 'error': str}
        """
        context = context or {}
        max_retries = max_retries or 3
        attempt = 0

        while attempt < max_retries:
            try:
                attempt += 1
                logger.info(f"执行操作: {operation_name} (尝试#{attempt}/{max_retries})")

                result = operation()

                logger.info(f"操作成功: {operation_name}")
                return {"success": True, "result": result, "error": None}

            except Exception as e:
                action = self.handle_error(e, context)

                if action == ErrorRecoveryAction.RETRY:
                    if attempt < max_retries:
                        delay = 0.5 * (2 ** (attempt - 1))  # 指数退避
                        logger.info(f"等待{delay:.1f}秒后重试...")
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"重试次数已用尽: {operation_name}")
                        return {
                            "success": False,
                            "result": None,
                            "error": f"重试失败: {str(e)}",
                        }

                elif action == ErrorRecoveryAction.FALLBACK:
                    logger.info("无法恢复，使用降级方案")
                    return {
                        "success": False,
                        "result": None,
                        "error": f"操作失败，已切换到降级模式: {str(e)}",
                    }

                elif action == ErrorRecoveryAction.SKIP:
                    logger.info("跳过此操作，继续执行")
                    return {
                        "success": False,
                        "result": None,
                        "error": f"操作已跳过: {str(e)}",
                    }

                else:  # ABORT
                    logger.error(f"执行中止: {operation_name}")
                    return {
                        "success": False,
                        "result": None,
                        "error": f"执行失败: {str(e)}",
                    }

        return {
            "success": False,
            "result": None,
            "error": f"操作{operation_name}失败",
        }

    def get_recovery_report(self) -> Dict[str, Any]:
        """获取恢复报告"""
        elapsed = (
            time.time() - self.start_time if self.start_time else 0
        )

        return {
            "iterations": self.iteration_count,
            "errors": self.error_count,
            "elapsed_time": elapsed,
            "timeout": self.config.timeout,
            "is_timeout": self.is_timeout(),
            "recovery_log": self.recovery_log,
            "can_continue": self.can_continue(),
        }
