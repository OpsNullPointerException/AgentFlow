"""LangChain Agent执行器实现"""

import time
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from langchain.agents import AgentExecutor
from .executor_base import BaseAgentExecutor, AgentExecutorResult
from .tools import ToolRegistry
from .smart_memory import SmartMemoryManager
from .execution_trace import ExecutionTrace
from .observation_masking import ObservationMasker
from ..models import Agent

logger = logging.getLogger(__name__)


class LangChainAgentExecutor(BaseAgentExecutor):
    """LangChain Agent执行器 - 包装原有的AgentExecutor"""

    def __init__(
        self,
        agent_executor: AgentExecutor,
        execution_trace: ExecutionTrace,
        agent_config: Agent,
    ):
        """
        Args:
            agent_executor: LangChain AgentExecutor实例
            execution_trace: 执行追踪器
            agent_config: Agent配置
        """
        self._executor = agent_executor
        self._execution_trace = execution_trace
        self._agent_config = agent_config
        self._start_time = time.time()
        self._execution_steps = []
        self._tools_used = []

    def invoke(self, user_input: str) -> AgentExecutorResult:
        """执行Agent

        Args:
            user_input: 用户输入

        Returns:
            AgentExecutorResult
        """
        try:
            start_time = time.time()

            # 调用原有的AgentExecutor
            result = self._executor.invoke({"input": user_input})

            duration = time.time() - start_time

            # 从ExecutionTrace提取信息
            tool_sequence = self._execution_trace.get_tool_sequence()
            tools_used = list({step["tool"] for step in tool_sequence if step["tool"]})

            # 获取详细的执行步骤
            execution_steps = self._execution_trace.get_detailed_trace()

            # 确保执行步骤是可序列化的
            try:
                import json
                json.dumps(execution_steps)  # 测试序列化
            except (TypeError, ValueError) as e:
                logger.warning(f"执行步骤无法序列化，使用摘要版本: {e}")
                summary = self._execution_trace.get_summary()
                execution_steps = [summary]

            return AgentExecutorResult(
                output=result.get("output", ""),
                tools_used=tools_used,
                execution_steps=execution_steps,
                execution_time=duration
            )

        except Exception as e:
            logger.error(f"LangChain Agent执行失败: {e}")
            raise

    @property
    def memory(self):
        """获取记忆管理器"""
        return self._executor.memory

    @property
    def tools(self) -> List:
        """获取工具列表"""
        return self._executor.tools

    def get_execution_trace(self) -> Dict[str, Any]:
        """获取执行追踪信息"""
        return self._execution_trace.export(format="detailed")
