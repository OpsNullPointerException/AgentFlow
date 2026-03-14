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
from langchain.schema import AgentAction, AgentFinish
from langchain.callbacks.base import BaseCallbackHandler
from langchain_community.llms import Tongyi
from django.conf import settings
from django.utils import timezone
import dashscope
from loguru import logger

from ..models import Agent, AgentExecution, AgentMemory
from ..schemas.agent import AgentExecutionOut, AgentStreamResponse
from .tools import ToolRegistry
from qa.services.llm_service import LLMService
from .execution_trace import ExecutionTrace
from .observation_masking import ObservationMasker
from .smart_memory import SmartMemoryManager


# ============== 默认系统提示词 ==============

DEFAULT_SYSTEM_PROMPT = """Answer the following questions as best you can. You have access to the following tools:

{tools}

【工具介绍】
1. **document_search** - 搜索知识库
   用于查找概念定义、业务术语、字段映射、状态代码含义
   当遇到中文术语、行业黑话、代码时，先用此工具澄清

2. **schema_query** - 查询数据库表结构
   输入'tables'获取所有表名，或输入表名获取字段清单和类型
   在SQL查询前的准备工作中使用

3. **sql_query** - 执行SQL查询
   仅支持SELECT查询（自动执行安全检查）
   用于获取具体数据

4. **convert_relative_time** - 相对时间转换
   将"昨天、上周、近30天"等转换为具体日期范围
   返回 {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
   当用户提及相对时间时必须使用

【输出格式 - 必须严格遵守】
Use the following format:

Question: the input question you must answer
Thought: [你的思考过程和分析步骤]
Action: [选择的工具名称，必须是上面工具列表中的一个]
Action Input: [工具的输入参数，必须是有效的JSON格式]
Observation: [工具的执行结果]
... (可以 Thought/Action/Action Input/Observation 循环多次)
Thought: I now know the final answer
Final Answer: [最终答案，用中文总结，包含查询理解、探测步骤、关键数据和业务解释]

【工具调用严格约束】
✓ Action 必须是 [document_search, schema_query, sql_query, convert_relative_time] 之一
✓ Action Input 必须是有效的 JSON 格式
✓ 每个工具调用都要等待 Observation 结果
✓ 禁止跳过探测步骤直接执行主查询

【查询工作流 - 必须严格按顺序执行】

Step 1: 理解意图
- Thought: 用户想查什么？是知识问题还是数据查询？
- 涉及哪些业务术语或字段？

Step 2: 术语澄清（如需要）
- 对于可能有歧义的中文术语、代码、状态值
- Action: document_search
- 直到确定对应的数据库字段名和预期的值范围

Step 3: 时间转换（如提到相对时间）
- 用户提及相对时间（昨天、上周、近30天等）
- Action: convert_relative_time
- 转换为具体日期范围

Step 4: 查看表结构
- Action: schema_query
- Input: "tables" 或表名
- 确认字段是否存在、类型是否合适

Step 5: 字段值探测（关键！）
- 对于不确定取值的字段，先执行轻量级探测SQL
- Action: sql_query
- Input: SELECT DISTINCT 字段名 LIMIT 10
- 确认实际存在的值格式、范围、后缀等

Step 6: 生成并执行主查询
- 基于前面的信息，生成准确的SQL
- Action: sql_query
- 确保字段名、值、条件都正确

Step 7: 解释结果
- Final Answer: 用自然语言总结查询结果
- 说明查询的含义、数据来源、数据量等

【字段值处理规则】

**中文术语/行业黑话：**
- Thought: 需要澄清XX的含义
- Action: document_search
- 例：用户说"A厂商"，先查知识库了解对应的数据库代码
- 然后用轻量SQL探测该代码是否有数据

**名称可能有后缀：**
- Thought: 需要确认字段值的实际格式
- Action: sql_query with SELECT DISTINCT
- 例：城市名可能含"市"后缀，先 SELECT DISTINCT LIMIT 10 确认格式

**枚举值不确定：**
- Thought: 需要获取所有可能的值
- Action: sql_query with SELECT DISTINCT
- 再按用户条件筛选

**时间范围处理：**
- Thought: 用户提到相对时间，需要转换
- Action: convert_relative_time
- 再用 BETWEEN 或 >= 等条件查询

【SQL查询约束】
✓ 必须明确指定SELECT的字段，禁止SELECT *
✓ 必须带WHERE条件进行过滤（除非查全表）
✓ 字符串值加引号，时间值用标准格式(YYYY-MM-DD)
✓ 对于维度字段（如VIN、用户ID），只允许COUNT/COUNT DISTINCT
✓ 避免全表扫描，先 DISTINCT 确认值，再主查询
✓ GROUP BY 时字段要一致

【SQL优化原则】
✓ 先执行轻量级探测SQL（LIMIT、DISTINCT），确认值存在
✓ 避免大数据量的JOIN，必要时分步查询
✓ 使用索引字段作为WHERE条件

【错误恢复】
- SQL报错时：检查字段名（schema_query）→ 检查值（SELECT DISTINCT）→ 修正语法 → 重试
- 无查询结果时：检查WHERE条件是否过严 → 尝试扩大条件范围 → 用轻量SQL确认数据是否存在

【安全约束】
✗ 禁止INSERT、UPDATE、DELETE、DROP、ALTER、CREATE等写操作
✗ 禁止访问敏感字段：密码、密钥、个人隐私信息
✗ 禁止不合理的JOIN导致笛卡尔积

Begin!

Question: {input}
Thought:{agent_scratchpad}"""


class AgentCallbackHandler(ExecutionTrace, BaseCallbackHandler):
    """
    Agent执行回调处理器 - 结合ExecutionTrace和LangChain回调

    直接继承ExecutionTrace，既提供执行追踪功能，又实现LangChain的回调接口。
    这样消除了ExecutionTrace和Handler的冗余，统一了事件记录。

    支持的回调：
    - on_agent_action(): Agent选择工具时触发
    - on_agent_finish(): Agent完成推理时触发
    - on_tool_start(): 工具开始执行时触发
    - on_tool_end(): 工具完成执行时触发
    - on_tool_error(): 工具执行出错时触发
    """

    def __init__(self, execution_id: str, agent_id: str = None, user_input: str = None):
        # 初始化ExecutionTrace（父类）
        ExecutionTrace.__init__(self, execution_id, agent_id, user_input)
        # 初始化BaseCallbackHandler
        BaseCallbackHandler.__init__(self)
        # 追踪状态
        self.current_tool = None
        self.current_tool_start_time = None

    def on_agent_action(self, action: AgentAction, **kwargs) -> None:
        """Agent选择工具时的回调"""
        logger.info(f"Agent选择工具: {action.tool}")
        self.add_tool_selection_step(
            candidates=list(kwargs.get("available_tools", [action.tool])),
            selected=action.tool,
            reasoning=str(action.tool_input),
            metadata={"agent_action": True}
        )
        self.current_tool = action.tool

    def on_agent_finish(self, finish: AgentFinish, **kwargs) -> None:
        """Agent完成推理时的回调"""
        logger.info(f"Agent完成推理")
        output = finish.return_values.get("output", "")
        self.add_final_answer(
            answer=output,
            metadata={"return_values": finish.return_values}
        )
        self.finish()

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:
        """工具开始执行时的回调"""
        logger.info(f"工具开始执行: {self.current_tool}")
        self.current_tool_start_time = time.time()
        self.add_tool_execution_start(
            tool_name=self.current_tool or "unknown",
            tool_input={"input": input_str},
            metadata={"serialized": serialized}
        )

    def on_tool_end(self, output: str, **kwargs) -> None:
        """工具完成执行时的回调"""
        logger.info(f"工具完成执行: {self.current_tool}")
        duration = time.time() - self.current_tool_start_time if self.current_tool_start_time else 0

        # 应用观察掩码压缩输出
        masked_output = ObservationMasker.mask_observation(
            self.current_tool or "unknown",
            output,
            max_length=500
        )

        # 记录压缩效果
        if len(masked_output) < len(output):
            ObservationMasker.estimate_token_reduction(
                self.current_tool or "unknown",
                output,
                masked_output
            )

        # 记录工具执行结束（使用压缩后的输出）
        self.add_tool_execution_end(
            tool_name=self.current_tool or "unknown",
            tool_output=masked_output,
            duration=duration,
            metadata={"output_length": len(masked_output), "original_length": len(output)}
        )

    def on_tool_error(self, error: Exception, **kwargs) -> None:
        """工具执行出错时的回调"""
        logger.error(f"工具执行出错: {str(error)}")
        self.add_tool_error(
            tool_name=self.current_tool or "unknown",
            error=str(error),
            metadata={"error_type": type(error).__name__}
        )

    # 导出方法保持兼容性
    def get_execution_trace(self) -> "AgentCallbackHandler":
        """返回自身（现在既是ExecutionTrace也是Handler）"""
        return self

    def get_trace_summary(self) -> dict:
        """获取执行追踪摘要"""
        return self.get_summary()

    def get_trace_detailed(self) -> dict:
        """获取执行追踪详情"""
        return self.export(format="detailed")


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
        """创建记忆组件 - 统一使用SmartMemoryManager"""
        try:
            memory_config = agent_config.memory_config or {}

            # 统一使用SmartMemoryManager - 支持通过配置调整行为
            memory = SmartMemoryManager(
                max_messages=memory_config.get("max_messages", 20),
                importance_threshold=memory_config.get("importance_threshold", 0.3),
                max_tokens=memory_config.get("max_tokens", 2000),
            )

            # 从数据库加载历史记忆
            if conversation_id:
                self._load_memory_from_db(agent_config.id, conversation_id, memory)
                logger.info(f"已从数据库加载Agent {agent_config.id} 对话 {conversation_id} 的记忆")

            return memory

        except Exception as e:
            logger.error(f"创建记忆组件失败: {e}")
            # 返回默认记忆
            return SmartMemoryManager()

    def _load_memory_from_db(self, agent_id: str, conversation_id: int, memory: SmartMemoryManager):
        """从数据库加载记忆到LangChain记忆组件"""
        try:
            from ..models import AgentMemory

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

    def _save_memory_to_db(self, agent_id: str, conversation_id: int, user_id: int, memory: SmartMemoryManager):
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

            # 根据代理类型创建不同的Agent
            if agent_config.agent_type == "react":
                # ReAct Agent
                from langchain import hub

                prompt = hub.pull("hwchase17/react")
                # 使用自定义 system_prompt 或默认 prompt
                system_prompt = agent_config.system_prompt if agent_config.system_prompt else DEFAULT_SYSTEM_PROMPT
                prompt.template = system_prompt + "\n\n" + prompt.template

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
                system_prompt = agent_config.system_prompt if agent_config.system_prompt else DEFAULT_SYSTEM_PROMPT
                prompt.template = system_prompt + "\n\n" + prompt.template

                agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)

            # 创建AgentExecutor - 优化速度配置
            agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                memory=memory,
                verbose=False,  # 关闭详细输出提高速度
                max_iterations=10,  # 增加最大迭代次数，允许更复杂的推理
                max_execution_time=120,  # 2分钟超时，给智能体更多时间
                callbacks=callbacks,  # 直接传递callbacks列表
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

            # 创建回调处理器 - 传入agent_id和user_input用于ExecutionTrace
            callback_handler = AgentCallbackHandler(execution_id, agent_id, user_input)

            # 创建Agent执行器
            agent_executor = self._create_agent_executor(agent_config, conversation_id, callback_handler)

            logger.info(f"开始执行Agent {agent_id}: {user_input}")

            # 执行Agent
            result = agent_executor.invoke({"input": user_input})

            # 计算执行时间
            execution_time = time.time() - start_time

            # 更新执行记录
            execution.agent_output = result.get("output", "")
            # 使用ExecutionTrace的详细追踪信息
            execution_trace = callback_handler.get_execution_trace()
            execution.execution_steps = execution_trace.get_detailed_trace()

            # 提取工具使用列表
            tool_sequence = execution_trace.get_tool_sequence()
            execution.tools_used = list({step["tool"] for step in tool_sequence if step["tool"]})

            execution.status = "completed"
            execution.execution_time = execution_time
            execution.completed_at = datetime.now()

            # 确保执行步骤是可序列化的
            try:
                import json

                json.dumps(execution.execution_steps)  # 测试序列化
            except (TypeError, ValueError) as e:
                logger.warning(f"执行步骤无法序列化，使用摘要版本: {e}")
                # 使用执行追踪的摘要
                summary = execution_trace.get_summary()
                execution.execution_steps = [summary]

            execution.save()

            # 自动评测（如果test_case可用）
            self._evaluate_execution(execution)

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

    def _evaluate_execution(self, execution: AgentExecution):
        """自动评测执行结果"""
        try:
            from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

            # 从用户输入中提取关键词
            keywords = self._extract_keywords_from_input(execution.user_input)

            # 构建测试用例
            test_case = {
                "expected": {
                    "keywords": keywords,
                    "min_length": 30,
                    "max_length": 5000,
                    "should_NOT_contain": [],
                    "expected_tools": execution.tools_used or [],
                }
            }

            evaluator = RuleBasedEvaluator()
            eval_result = evaluator.evaluate(execution, test_case)

            execution.evaluation_score = eval_result["score"]
            execution.evaluation_details = eval_result["details"]
            execution.evaluation_passed = eval_result["passed"]
            execution.evaluation_report = eval_result["reasoning"]

            execution.save(update_fields=["evaluation_score", "evaluation_details", "evaluation_passed", "evaluation_report"])

            logger.info(f"执行 {execution.id} 评测完成：得分={eval_result['score']:.2f}，通过={eval_result['passed']}")

        except Exception as e:
            logger.warning(f"执行评测失败: {e}")
            # 评测失败不影响主流程

    def _extract_keywords_from_input(self, user_input: str) -> list:
        """从用户输入中提取关键词"""
        import re

        # 分词
        words = re.findall(r'\w+', user_input)

        # 停用词列表
        stopwords = {'的', '和', '在', '是', '了', '个', '到', '对', '被', '我', '你', '他', '这', '那', '一'}

        # 过滤停用词和过短词汇
        keywords = [w for w in words if w not in stopwords and len(w) > 1]

        # 去重并排序，最多保留10个关键词
        return list(dict.fromkeys(keywords))[:10]

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
