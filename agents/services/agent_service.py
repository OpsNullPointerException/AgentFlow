"""
基于LangGraph的智能代理服务 - Django ORM集成层
"""

import time
import json
from typing import Any, Dict, List, Optional
from datetime import datetime

from langchain_community.llms import Tongyi
from django.conf import settings
import dashscope
from loguru import logger

from ..models import Agent, AgentExecution, AgentMemory
from ..schemas.agent import AgentExecutionOut, AgentStreamResponse
from agents.services.tools import ToolRegistry
from qa.services.llm_service import LLMService
from agents.langgraph import create_agent_graph, create_initial_state


class AgentService:
    """智能代理服务 - 直接使用LangGraph执行核心"""

    def __init__(self):
        """初始化AgentService"""
        self.llm_service = LLMService()

    def _create_llm(self, agent_config: Agent):
        """创建LLM实例"""
        try:
            api_key = settings.DASHSCOPE_API_KEY
            if not api_key:
                raise ValueError("DASHSCOPE_API_KEY未配置")

            dashscope.api_key = api_key

            llm = Tongyi(
                model_name="qwen-turbo",
                temperature=0.1,
                top_p=0.8,
                max_tokens=1000,
                dashscope_api_key=api_key,
            )
            return llm
        except Exception as e:
            logger.error(f"创建LLM失败: {e}")
            raise

    def execute_agent(
        self, agent_id: str, user_input: str, user_id: int, conversation_id: Optional[int] = None
    ) -> AgentExecutionOut:
        """执行Agent"""
        start_time = time.time()
        execution_id = None

        try:
            # 获取Agent配置
            agent_config = Agent.objects.get(id=agent_id, status="active")

            # 创建执行记录
            execution = AgentExecution.objects.create(
                agent_id=agent_id,
                conversation_id=conversation_id,
                user_id=user_id,
                user_input=user_input,
                status="running",
            )
            execution_id = str(execution.id)

            logger.info(f"开始执行Agent {agent_id}: {user_input}")

            # 创建LLM和工具
            llm = self._create_llm(agent_config)
            tools = ToolRegistry.get_tools_by_names(agent_config.available_tools)
            if not tools:
                logger.warning("没有可用工具，使用默认工具")
                tools = [ToolRegistry.get_tool("document_search")]

            # 直接执行LangGraph
            agent_graph = create_agent_graph(llm, tools, memory_manager=None)
            state = create_initial_state(
                user_input=user_input,
                user_id=str(user_id),
                agent_id=agent_id,
                conversation_id=str(conversation_id) if conversation_id else None,
                max_iterations=10
            )

            # 执行图
            result_state = agent_graph.invoke(state)

            # 计算执行时间
            execution_time = time.time() - start_time

            # 更新执行记录
            execution.agent_output = result_state.get("final_answer", "")

            # 转换execution_steps为可序列化格式（处理datetime对象）
            execution_steps = result_state.get("execution_steps", []) or []
            serialized_steps = []
            for step in execution_steps:
                if isinstance(step, dict):
                    # 转换datetime对象为ISO格式字符串
                    serialized_step = {
                        k: v.isoformat() if isinstance(v, datetime) else v
                        for k, v in step.items()
                    }
                    serialized_steps.append(serialized_step)
                else:
                    serialized_steps.append(step)

            execution.execution_steps = serialized_steps
            execution.tools_used = result_state.get("tools_used", [])
            execution.status = "completed"
            execution.execution_time = execution_time
            execution.completed_at = datetime.now()
            execution.error_message = result_state.get("error_message", "")

            # 确保执行步骤是可序列化的
            try:
                json.dumps(execution.execution_steps)
            except (TypeError, ValueError) as e:
                logger.warning(f"执行步骤无法序列化: {e}")
                execution.execution_steps = []

            execution.save()

            logger.info(f"Agent {agent_id} 执行完成，耗时 {execution_time:.2f}s")

            # 返回结果
            return AgentExecutionOut(
                id=execution.id,
                agent_id=agent_id,
                user_id=user_id,
                user_input=user_input,
                agent_output=execution.agent_output,
                tools_used=execution.tools_used,
                execution_steps=execution.execution_steps,
                status="completed",
                error_message="",
                execution_time=execution_time,
            )

        except Exception as e:
            logger.error(f"Agent {agent_id} 执行失败: {e}", exc_info=True)

            if execution_id:
                try:
                    execution = AgentExecution.objects.get(id=execution_id)
                    execution.status = "failed"
                    execution.error_message = str(e)
                    execution.save()
                except Exception as ex:
                    logger.error(f"保存失败状态失败: {ex}")

            execution_time = time.time() - start_time
            return AgentExecutionOut(
                id=execution_id,
                agent_id=agent_id,
                user_id=user_id,
                user_input=user_input,
                agent_output="",
                tools_used=[],
                execution_steps=[],
                status="failed",
                error_message=str(e),
                execution_time=execution_time,
            )

    def get_execution_history(
        self, agent_id: str, user_id: int, limit: int = 10
    ) -> List[AgentExecutionOut]:
        """获取Agent的执行历史"""
        try:
            executions = AgentExecution.objects.filter(
                agent_id=agent_id, user_id=user_id
            ).order_by("-created_at")[:limit]

            return [
                AgentExecutionOut(
                    id=ex.id,
                    agent_id=ex.agent_id,
                    user_id=ex.user_id,
                    user_input=ex.user_input,
                    agent_output=ex.agent_output,
                    tools_used=ex.tools_used,
                    execution_steps=ex.execution_steps,
                    status=ex.status,
                    error_message=ex.error_message,
                    execution_time=ex.execution_time,
                )
                for ex in executions
            ]
        except Exception as e:
            logger.error(f"获取执行历史失败: {e}")
            return []

    def create_agent(self, agent_data: Dict[str, Any], user_id: int) -> Agent:
        """创建Agent"""
        try:
            agent = Agent.objects.create(
                user_id=user_id,
                name=agent_data.get("name"),
                description=agent_data.get("description"),
                available_tools=agent_data.get("available_tools", []),
                memory_config=agent_data.get("memory_config", {}),
                status="active",
            )
            logger.info(f"创建Agent {agent.id}")
            return agent
        except Exception as e:
            logger.error(f"创建Agent失败: {e}")
            raise

    def update_agent(self, agent_id: str, update_data: Dict[str, Any], user_id: int) -> Agent:
        """更新Agent"""
        try:
            agent = Agent.objects.get(id=agent_id, user_id=user_id)
            for key, value in update_data.items():
                if key not in ["id", "user_id", "created_at"]:
                    setattr(agent, key, value)
            agent.save()
            logger.info(f"更新Agent {agent_id}")
            return agent
        except Exception as e:
            logger.error(f"更新Agent失败: {e}")
            raise

    def delete_agent(self, agent_id: str, user_id: int) -> bool:
        """删除Agent"""
        try:
            agent = Agent.objects.get(id=agent_id, user_id=user_id)
            agent.delete()
            logger.info(f"删除Agent {agent_id}")
            return True
        except Exception as e:
            logger.error(f"删除Agent失败: {e}")
            return False

    def get_agent(self, agent_id: str, user_id: int) -> Agent:
        """获取Agent信息"""
        try:
            return Agent.objects.get(id=agent_id, user_id=user_id)
        except Exception as e:
            logger.error(f"获取Agent失败: {e}")
            raise

    def list_agents(self, user_id: int) -> List[Agent]:
        """获取用户的所有Agent"""
        try:
            return list(Agent.objects.filter(user_id=user_id, status="active"))
        except Exception as e:
            logger.error(f"列表Agent失败: {e}")
            return []
