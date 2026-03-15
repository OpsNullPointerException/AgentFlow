"""LangGraph Agent执行器实现"""

import time
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from .executor_base import BaseAgentExecutor, AgentExecutorResult
from ..memory.smart_memory_manager import SmartMemoryManager
from ..evaluation.rule_based_evaluator import RuleBasedEvaluator

logger = logging.getLogger(__name__)


class LangGraphAgentExecutor(BaseAgentExecutor):
    """LangGraph Agent执行器"""

    def __init__(
        self,
        llm: Any,
        tools: List,
        memory_manager: Optional[SmartMemoryManager] = None,
        agent_config: Optional[Any] = None,
    ):
        """
        Args:
            llm: 语言模型
            tools: 工具列表
            memory_manager: 记忆管理器
            agent_config: Agent配置
        """
        from agents.langgraph_graph import create_agent_graph
        from agents.langgraph_state import create_initial_state

        self.llm = llm
        self._tools = tools
        self._memory_manager = memory_manager or SmartMemoryManager(memory_type="smart")
        self._agent_config = agent_config
        self._create_initial_state = create_initial_state

        # 创建Agent图
        self.agent_graph = create_agent_graph(llm, tools, self._memory_manager)

    def invoke(self, user_input: str) -> AgentExecutorResult:
        """执行Agent

        Args:
            user_input: 用户输入

        Returns:
            AgentExecutorResult
        """
        try:
            start_time = time.time()

            # 创建初始状态
            state = self._create_initial_state(
                user_input=user_input,
                user_id="",  # 由调用者传入
                agent_id="",  # 由调用者传入
                conversation_id=None,
                max_iterations=10
            )

            # 调用Agent图
            result_state = self.agent_graph.invoke(state)

            duration = time.time() - start_time

            return AgentExecutorResult(
                output=result_state.get("final_answer", ""),
                tools_used=result_state.get("tools_used", []),
                execution_steps=result_state.get("execution_steps", []),
                error_message=result_state.get("error_message", ""),
                execution_time=duration
            )

        except Exception as e:
            logger.error(f"LangGraph Agent执行失败: {e}")
            raise

    @property
    def memory(self):
        """获取记忆管理器"""
        return self._memory_manager

    @property
    def tools(self) -> List:
        """获取工具列表"""
        return self._tools

    def get_execution_trace(self) -> Dict[str, Any]:
        """获取执行追踪信息"""
        # LangGraph可以直接返回execution_steps
        return {"type": "langgraph", "tools_used": self._tools}
