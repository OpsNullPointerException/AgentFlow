"""Agent执行器基类 - 定义Agent执行的统一接口"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime


class AgentExecutorResult:
    """Agent执行结果数据类"""

    def __init__(
        self,
        output: str,
        tools_used: List[str],
        execution_steps: List[Dict[str, Any]],
        error_message: Optional[str] = None,
        execution_time: float = 0.0
    ):
        self.output = output
        self.tools_used = tools_used
        self.execution_steps = execution_steps
        self.error_message = error_message
        self.execution_time = execution_time


class BaseAgentExecutor(ABC):
    """Agent执行器基类 - LangChain和LangGraph都继承这个接口"""

    @abstractmethod
    def invoke(self, user_input: str) -> AgentExecutorResult:
        """执行Agent

        Args:
            user_input: 用户输入

        Returns:
            AgentExecutorResult: 包含输出、工具使用、执行步骤等的结果
        """
        pass

    @property
    @abstractmethod
    def memory(self):
        """获取记忆管理器"""
        pass

    @property
    @abstractmethod
    def tools(self) -> List:
        """获取工具列表"""
        pass

    @abstractmethod
    def get_execution_trace(self) -> Dict[str, Any]:
        """获取执行追踪信息"""
        pass
