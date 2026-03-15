"""
基于LangGraph的智能代理服务
"""

import time
import json
from typing import Any, Dict, List, Optional, AsyncIterator
from datetime import datetime

from langchain_community.llms import Tongyi
from django.conf import settings
from django.utils import timezone
import dashscope
from loguru import logger

from ..models import Agent, AgentExecution, AgentMemory
from ..schemas.agent import AgentExecutionOut, AgentStreamResponse
from .tools import ToolRegistry
from qa.services.llm_service import LLMService
from .observation_masking import ObservationMasker
from .smart_memory import SmartMemoryManager
from agents.langgraph_graph import create_agent_graph
from agents.langgraph_state import create_initial_state


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


class AgentService:
    """智能代理服务 - 基于LangGraph"""

    def __init__(self):
        """初始化AgentService"""
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

            # SmartMemoryManager内置了记忆管理，这里仅作日志记录
            stats = memory.get_stats()

            memory_record, created = AgentMemory.objects.update_or_create(
                agent_id=agent_id,
                conversation_id=conversation_id,
                memory_key="chat_history",
                defaults={
                    "user_id": user_id,
                    "memory_data": {
                        "total_conversations": stats.get("total_conversations", 0),
                        "total_users": stats.get("total_users", 0),
                    }
                },
            )

            action = "创建" if created else "更新"
            logger.info(f"{action}了Agent {agent_id} 对话 {conversation_id} 的记忆记录")

        except Exception as e:
            logger.error(f"保存记忆到数据库失败: {e}")

    def _execute_langgraph(
        self,
        llm: Any,
        tools: List,
        memory_manager: Any,
        user_input: str,
    ) -> Dict[str, Any]:
        """直接执行LangGraph Agent"""
        try:
            start_time = time.time()

            # 创建初始状态
            state = create_initial_state(
                user_input=user_input,
                user_id="",
                agent_id="",
                conversation_id=None,
                max_iterations=10
            )

            # 创建Agent图
            agent_graph = create_agent_graph(llm, tools, memory_manager)

            # 执行Agent图
            result_state = agent_graph.invoke(state)

            duration = time.time() - start_time

            return {
                "output": result_state.get("final_answer", ""),
                "tools_used": result_state.get("tools_used", []),
                "execution_steps": result_state.get("execution_steps", []),
                "error_message": result_state.get("error_message", ""),
                "execution_time": duration,
                "memory": memory_manager,
            }

        except Exception as e:
            logger.error(f"LangGraph执行失败: {e}")
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

            # 创建LLM、工具、记忆
            llm = self._create_llm(agent_config)
            tools = ToolRegistry.get_tools_by_names(agent_config.available_tools)
            if not tools:
                logger.warning("没有可用工具，使用默认工具")
                tools = [ToolRegistry.get_tool("document_search")]
            memory = self._create_memory(agent_config, conversation_id)

            # 执行LangGraph Agent
            result = self._execute_langgraph(llm, tools, memory, user_input)

            # 计算执行时间
            execution_time = time.time() - start_time

            # 更新执行记录
            execution.agent_output = result["output"]
            execution.execution_steps = result["execution_steps"] or []
            execution.tools_used = result["tools_used"]
            execution.status = "completed"
            execution.execution_time = execution_time
            execution.completed_at = datetime.now()
            execution.error_message = result["error_message"] or ""

            # 确保执行步骤是可序列化的
            try:
                json.dumps(execution.execution_steps)
            except (TypeError, ValueError) as e:
                logger.warning(f"执行步骤无法序列化: {e}")
                execution.execution_steps = []

            execution.save()

            # 自动评测
            self._evaluate_execution(execution)

            # 保存记忆到数据库
            if conversation_id:
                self._save_memory_to_db(agent_id, conversation_id, user_id, result["memory"])
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
