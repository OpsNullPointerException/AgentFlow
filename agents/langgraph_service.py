"""LangGraph Agent Service - 替代LangChainAgentService"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from langchain_core.language_models import BaseLLM
from langchain_core.tools import BaseTool

from agents.langgraph import create_agent_graph, create_initial_state, AgentState

logger = logging.getLogger(__name__)


class LangGraphAgentService:
    """使用LangGraph的Agent服务，替代原LangChainAgentService"""

    def __init__(
        self,
        llm: BaseLLM,
        tools: List[BaseTool],
        checkpointer_path: str = ":memory:"
    ):
        self.llm = llm
        self.tools = tools

        # 构建Agent图
        self.agent_graph = create_agent_graph(
            llm=llm,
            tools=tools,
            checkpointer_path=checkpointer_path
        )

    def execute_agent(
        self,
        agent_id: str,
        user_input: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        test_case: Optional[Dict[str, Any]] = None,
        max_iterations: int = 10
    ) -> Dict[str, Any]:
        """执行Agent并返回结果"""

        execution_id = f"{agent_id}:{conversation_id or 'new'}"
        logger.info(f"Executing agent {agent_id} for user {user_id}: {user_input}")

        try:
            # 创建初始状态
            state = create_initial_state(
                user_input=user_input,
                user_id=user_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                max_iterations=max_iterations
            )

            # 添加test_case如果提供
            if test_case:
                state["test_case"] = test_case

            # 调用Agent图
            config = {"configurable": {"thread_id": execution_id}}
            try:
                result_state = self.agent_graph.invoke(state, config=config)
            except TypeError:
                # 如果不支持config参数，直接调用invoke
                result_state = self.agent_graph.invoke(state)

            # 构建返回结果
            return {
                "success": True,
                "agent_id": agent_id,
                "user_id": user_id,
                "user_input": user_input,
                "agent_output": result_state.get("final_answer", ""),
                "tools_used": result_state.get("tools_used", []),
                "execution_time": result_state.get("total_duration", 0.0),
                "error_message": result_state.get("error_message", ""),
                "status": "completed",
            }

        except Exception as e:
            logger.error(f"Agent execution error: {e}", exc_info=True)

            return {
                "success": False,
                "agent_id": agent_id,
                "user_id": user_id,
                "user_input": user_input,
                "agent_output": "",
                "tools_used": [],
                "execution_time": 0.0,
                "error_message": str(e),
                "status": "failed",
            }
