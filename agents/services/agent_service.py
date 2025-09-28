"""
基于LangChain的智能代理服务
"""

import time
import json
from typing import Any, Dict, List, Optional, AsyncIterator
from datetime import datetime

from langchain.agents import AgentExecutor, create_react_agent, create_openai_functions_agent
from langchain.agents.agent import AgentOutputParser
from langchain.agents.react.base import ReActDocstoreAgent
from langchain.agents.structured_chat.base import StructuredChatAgent
from langchain.agents.conversational.base import ConversationalAgent
from langchain.memory import ConversationBufferWindowMemory, ConversationSummaryBufferMemory
from langchain.schema import AgentAction, AgentFinish
from langchain.callbacks.base import BaseCallbackHandler
from langchain.callbacks.manager import CallbackManager
from langchain_community.llms import Tongyi
from django.conf import settings
from django.utils import timezone
import dashscope
from loguru import logger

from ..models import Agent, AgentExecution, AgentMemory
from ..schemas.agent import AgentExecutionOut, AgentStreamResponse
from .tools import ToolRegistry
from qa.services.llm_service import LLMService


class AgentCallbackHandler(BaseCallbackHandler):
    """
    Agent执行回调处理器

    继承自 BaseCallbackHandler，必须使用LangChain规定的特定函数名：

    Agent相关回调：
    - on_agent_action(): Agent决定执行某个工具时触发
    - on_agent_finish(): Agent完成整个推理过程时触发

    工具相关回调：
    - on_tool_start(): 工具开始执行时触发
    - on_tool_end(): 工具执行完成时触发
    - on_tool_error(): 工具执行出错时触发

    LLM相关回调：
    - on_llm_start(): LLM开始生成时触发
    - on_llm_end(): LLM生成完成时触发
    - on_llm_error(): LLM生成出错时触发

    Chain相关回调：
    - on_chain_start(): Chain开始执行时触发
    - on_chain_end(): Chain执行完成时触发
    - on_chain_error(): Chain执行出错时触发
    """

    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        self.steps = []
        self.current_step = None

    def on_agent_action(self, action: AgentAction, **kwargs) -> None:
        """
        Agent执行动作时的回调 - 函数名必须是 on_agent_action
        当Agent决定使用某个工具时会触发此回调
        """
        logger.info(f"Agent动作: {action.tool} - {action.tool_input}")
        step = {
            "step_type": "action",
            "step_name": action.tool,
            "input_data": {"tool_input": action.tool_input},
            "timestamp": datetime.now().isoformat(),
        }
        self.steps.append(step)
        self.current_step = step

    def on_agent_finish(self, finish: AgentFinish, **kwargs) -> None:
        """
        Agent完成时的回调 - 函数名必须是 on_agent_finish
        当Agent完成整个推理过程并给出最终答案时触发
        """
        logger.info(f"Agent完成: {finish.return_values}")
        step = {
            "step_type": "finish",
            "step_name": "final_answer",
            "output_data": finish.return_values,
            "timestamp": datetime.now().isoformat(),
        }
        self.steps.append(step)

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
        """
        工具开始执行时的回调 - 函数名必须是 on_tool_start
        当Agent调用工具开始执行时触发
        """
        if self.current_step:
            self.current_step["tool_start_time"] = time.time()

    def on_tool_end(self, output: str, **kwargs) -> None:
        """
        工具执行结束时的回调 - 函数名必须是 on_tool_end
        当工具执行完成并返回结果时触发
        """
        if self.current_step:
            self.current_step["output_data"] = {"tool_output": output}
            if "tool_start_time" in self.current_step:
                duration = time.time() - self.current_step["tool_start_time"]
                self.current_step["duration"] = duration

    def on_tool_error(self, error: Exception, **kwargs) -> None:
        """
        工具执行出错时的回调 - 函数名必须是 on_tool_error
        当工具执行过程中发生错误时触发
        """
        logger.error(f"工具执行出错: {error}")
        if self.current_step:
            self.current_step["error"] = str(error)
            self.current_step["status"] = "error"


class AgentService:
    """智能代理服务"""

    def __init__(self):
        self.llm_service = LLMService()

    def _create_llm(self, agent_config: Agent):
        """创建LLM实例"""
        try:
            # 配置DashScope
            api_key = settings.DASHSCOPE_API_KEY
            if not api_key:
                raise ValueError("DASHSCOPE_API_KEY未配置")

            dashscope.api_key = api_key

            # 使用通义千问LLM - 优化速度配置
            llm = Tongyi(
                model_name="qwen-turbo",  # 强制使用最快的模型
                temperature=0.1,  # 降低随机性，提高响应速度
                top_p=0.8,
                max_tokens=1000,  # 限制输出长度
                dashscope_api_key=api_key,
            )
            return llm
        except Exception as e:
            logger.error(f"创建LLM失败: {e}")
            raise

    def _create_memory(self, agent_config: Agent, conversation_id: Optional[int] = None):
        """创建记忆组件"""
        try:
            memory_type = agent_config.memory_type
            memory_config = agent_config.memory_config or {}

            # 创建基础记忆组件
            if memory_type == "buffer_window":
                memory = ConversationBufferWindowMemory(
                    k=memory_config.get("window_size", 5), memory_key="chat_history", return_messages=True
                )
            elif memory_type == "summary_buffer":
                llm = self._create_llm(agent_config)
                memory = ConversationSummaryBufferMemory(
                    llm=llm,
                    max_token_limit=memory_config.get("max_token_limit", 2000),
                    memory_key="chat_history",
                    return_messages=True,
                )
            else:
                # 默认使用buffer_window
                memory = ConversationBufferWindowMemory(k=5, memory_key="chat_history", return_messages=True)

            # 从数据库加载历史记忆
            if conversation_id:
                self._load_memory_from_db(agent_config.id, conversation_id, memory)
                logger.info(f"已从数据库加载Agent {agent_config.id} 对话 {conversation_id} 的记忆")

            return memory

        except Exception as e:
            logger.error(f"创建记忆组件失败: {e}")
            # 返回默认记忆
            return ConversationBufferWindowMemory(k=5, memory_key="chat_history", return_messages=True)

    def _load_memory_from_db(self, agent_id: str, conversation_id: int, memory):
        """从数据库加载记忆到LangChain记忆组件"""
        try:
            from ..models import AgentMemory
            from langchain.schema import HumanMessage, AIMessage

            # 查询该对话的记忆记录
            memory_records = AgentMemory.objects.filter(
                agent_id=agent_id, conversation_id=conversation_id, memory_key="chat_history"
            ).order_by("created_at")

            for record in memory_records:
                # 恢复聊天历史
                chat_history = record.memory_data.get("messages", [])
                for msg in chat_history:
                    if msg.get("type") == "human":
                        memory.chat_memory.add_user_message(msg.get("content", ""))
                    elif msg.get("type") == "ai":
                        memory.chat_memory.add_ai_message(msg.get("content", ""))

            logger.info(f"从数据库加载了 {len(memory_records)} 条记忆记录")

        except Exception as e:
            logger.error(f"从数据库加载记忆失败: {e}")

    def _save_memory_to_db(self, agent_id: str, conversation_id: int, user_id: int, memory):
        """保存记忆到数据库"""
        try:
            from ..models import AgentMemory

            # 获取当前聊天历史
            chat_history = []
            if hasattr(memory, "chat_memory") and hasattr(memory.chat_memory, "messages"):
                for msg in memory.chat_memory.messages:
                    if hasattr(msg, "type"):
                        chat_history.append({"type": msg.type, "content": msg.content})
                    else:
                        # 兼容不同的消息格式
                        msg_type = "human" if "Human" in str(type(msg)) else "ai"
                        chat_history.append(
                            {"type": msg_type, "content": str(msg.content) if hasattr(msg, "content") else str(msg)}
                        )

            # 更新或创建记忆记录
            memory_record, created = AgentMemory.objects.update_or_create(
                agent_id=agent_id,
                conversation_id=conversation_id,
                memory_key="chat_history",
                defaults={"user_id": user_id, "memory_data": {"messages": chat_history}},
            )

            action = "创建" if created else "更新"
            logger.info(f"{action}了Agent {agent_id} 对话 {conversation_id} 的记忆记录")

        except Exception as e:
            logger.error(f"保存记忆到数据库失败: {e}")

    def _create_agent_executor(
        self,
        agent_config: Agent,
        conversation_id: Optional[int] = None,
        callback_handler: Optional[AgentCallbackHandler] = None,
    ) -> AgentExecutor:
        """创建Agent执行器"""
        try:
            # 创建LLM
            llm = self._create_llm(agent_config)

            # 创建工具
            tools = ToolRegistry.get_tools_by_names(agent_config.available_tools)
            if not tools:
                logger.warning("没有可用工具，使用默认工具")
                tools = [ToolRegistry.get_tool("document_search")]

            # 创建记忆
            memory = self._create_memory(agent_config, conversation_id)

            # 创建回调管理器
            callbacks = []
            if callback_handler:
                callbacks.append(callback_handler)
            callback_manager = CallbackManager(callbacks) if callbacks else None

            # 根据代理类型创建不同的Agent
            if agent_config.agent_type == "react":
                # ReAct Agent
                from langchain import hub

                prompt = hub.pull("hwchase17/react")
                prompt.template = agent_config.system_prompt + "\n\n" + prompt.template

                agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)

            elif agent_config.agent_type == "openai_functions":
                # OpenAI Functions Agent
                from langchain import hub

                prompt = hub.pull("hwchase17/openai-functions-agent")

                agent = create_openai_functions_agent(llm=llm, tools=tools, prompt=prompt)

            elif agent_config.agent_type == "structured_chat":
                # Structured Chat Agent
                agent = StructuredChatAgent.from_llm_and_tools(llm=llm, tools=tools, prefix=agent_config.system_prompt)

            elif agent_config.agent_type == "conversational":
                # Conversational Agent
                agent = ConversationalAgent.from_llm_and_tools(llm=llm, tools=tools, prefix=agent_config.system_prompt)

            else:
                # 默认使用ReAct
                from langchain import hub

                prompt = hub.pull("hwchase17/react")
                prompt.template = agent_config.system_prompt + "\n\n" + prompt.template

                agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)

            # 创建AgentExecutor - 优化速度配置
            agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                memory=memory,
                verbose=False,  # 关闭详细输出提高速度
                max_iterations=10,  # 增加最大迭代次数，允许更复杂的推理
                max_execution_time=120,  # 2分钟超时，给智能体更多时间
                callback_manager=callback_manager,
                early_stopping_method="force",  # 使用支持的停止方法
                handle_parsing_errors=True,
            )

            return agent_executor

        except Exception as e:
            logger.error(f"创建Agent执行器失败: {e}")
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

            # 创建回调处理器
            callback_handler = AgentCallbackHandler(execution_id)

            # 创建Agent执行器
            agent_executor = self._create_agent_executor(agent_config, conversation_id, callback_handler)

            logger.info(f"开始执行Agent {agent_id}: {user_input}")

            # 执行Agent
            result = agent_executor.invoke({"input": user_input})

            # 计算执行时间
            execution_time = time.time() - start_time

            # 更新执行记录
            execution.agent_output = result.get("output", "")
            execution.execution_steps = callback_handler.steps
            execution.tools_used = list(
                {step.get("step_name", "") for step in callback_handler.steps if step.get("step_type") == "action"}
            )
            execution.status = "completed"
            execution.execution_time = execution_time
            execution.completed_at = datetime.now()

            # 确保执行步骤是可序列化的
            try:
                import json

                json.dumps(execution.execution_steps)  # 测试序列化
            except (TypeError, ValueError) as e:
                logger.warning(f"执行步骤无法序列化，将使用简化版本: {e}")
                # 创建简化的执行步骤
                execution.execution_steps = [
                    {
                        "step_type": "summary",
                        "step_name": "execution_summary",
                        "content": f"智能体执行了{len(callback_handler.steps)}个步骤",
                        "timestamp": datetime.now().isoformat(),
                    }
                ]

            execution.save()

            # 保存记忆到数据库
            if conversation_id:
                memory = agent_executor.memory
                self._save_memory_to_db(agent_id, conversation_id, user_id, memory)
                logger.info(f"已保存Agent {agent_id} 对话 {conversation_id} 的记忆到数据库")

            # 更新Agent统计
            agent_config.execution_count += 1
            agent_config.last_executed_at = datetime.now()
            agent_config.save()

            logger.info(f"Agent执行完成，耗时: {execution_time:.2f}秒")

            # 转换为输出Schema
            return AgentExecutionOut(
                id=str(execution.id),
                agent_id=agent_id,
                user_input=user_input,
                agent_output=execution.agent_output,
                execution_steps=execution.execution_steps,
                tools_used=execution.tools_used,
                status=execution.status,
                error_message=execution.error_message,
                execution_time=execution.execution_time,
                token_usage=execution.token_usage,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
            )

        except Agent.DoesNotExist:
            error_msg = f"Agent不存在或已禁用: {agent_id}"
            logger.error(error_msg)
            if execution_id:
                AgentExecution.objects.filter(id=execution_id).update(
                    status="failed", error_message=error_msg, completed_at=timezone.now()
                )
            raise ValueError(error_msg)

        except Exception as e:
            error_msg = f"Agent执行失败: {str(e)}"
            logger.error(error_msg)

            if execution_id:
                AgentExecution.objects.filter(id=execution_id).update(
                    status="failed",
                    error_message=error_msg,
                    execution_time=time.time() - start_time,
                    completed_at=timezone.now(),
                )

            raise

    def create_agent(self, agent_data: dict, user_id: int) -> Agent:
        """创建新的Agent"""
        try:
            agent_data["user_id"] = user_id
            agent = Agent.objects.create(**agent_data)
            logger.info(f"创建Agent成功: {agent.name}")
            return agent
        except Exception as e:
            logger.error(f"创建Agent失败: {e}")
            raise

    def update_agent(self, agent_id: str, update_data: dict, user_id: int) -> Agent:
        """更新Agent"""
        try:
            agent = Agent.objects.get(id=agent_id, user_id=user_id)
            for key, value in update_data.items():
                if value is not None:
                    setattr(agent, key, value)
            agent.save()
            logger.info(f"更新Agent成功: {agent.name}")
            return agent
        except Agent.DoesNotExist:
            raise ValueError(f"Agent不存在或无权限: {agent_id}")
        except Exception as e:
            logger.error(f"更新Agent失败: {e}")
            raise

    def delete_agent(self, agent_id: str, user_id: int):
        """删除Agent"""
        try:
            agent = Agent.objects.get(id=agent_id, user_id=user_id)
            agent.delete()
            logger.info(f"删除Agent成功: {agent_id}")
        except Agent.DoesNotExist:
            raise ValueError(f"Agent不存在或无权限: {agent_id}")
        except Exception as e:
            logger.error(f"删除Agent失败: {e}")
            raise

    def get_agent(self, agent_id: str, user_id: int) -> Agent:
        """获取Agent"""
        try:
            return Agent.objects.get(id=agent_id, user_id=user_id)
        except Agent.DoesNotExist:
            raise ValueError(f"Agent不存在或无权限: {agent_id}")

    def list_agents(self, user_id: int) -> List[Agent]:
        """获取用户的Agent列表"""
        return Agent.objects.filter(user_id=user_id).order_by("-updated_at")

    def get_execution_history(self, agent_id: str, user_id: int, limit: int = 50) -> List[AgentExecution]:
        """获取Agent执行历史"""
        return AgentExecution.objects.filter(agent_id=agent_id, user_id=user_id).order_by("-started_at")[:limit]

    def get_agent_memory(self, agent_id: str, conversation_id: int, user_id: int):
        """获取Agent的记忆记录"""
        try:
            from ..models import AgentMemory

            return AgentMemory.objects.filter(
                agent_id=agent_id, conversation_id=conversation_id, user_id=user_id
            ).order_by("-updated_at")
        except Exception as e:
            logger.error(f"获取Agent记忆失败: {e}")
            return []

    def clear_agent_memory(self, agent_id: str, conversation_id: Optional[int] = None, user_id: Optional[int] = None):
        """清理Agent记忆"""
        try:
            from ..models import AgentMemory

            filters = {"agent_id": agent_id}
            if conversation_id:
                filters["conversation_id"] = conversation_id
            if user_id:
                filters["user_id"] = user_id

            deleted_count = AgentMemory.objects.filter(**filters).delete()[0]
            logger.info(f"清理了 {deleted_count} 条Agent记忆记录")
            return deleted_count
        except Exception as e:
            logger.error(f"清理Agent记忆失败: {e}")
            return 0
