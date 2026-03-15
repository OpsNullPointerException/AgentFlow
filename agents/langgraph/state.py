"""LangGraph Agent 状态定义"""

from typing_extensions import TypedDict, Annotated
from typing import Any, Optional, List, Dict
from langchain_core.messages import BaseMessage
from datetime import datetime


class ExecutionStep(TypedDict):
    """单个执行步骤"""
    step_type: str  # "tool_call", "observation", "thought", etc.
    tool_name: Optional[str]
    tool_input: Optional[str]
    tool_output: Optional[str]
    timestamp: datetime
    duration: float


class AgentState(TypedDict):
    """Agent执行的完整状态"""

    # 输入相关
    user_input: str
    user_id: str
    agent_id: str
    conversation_id: Optional[str]

    # Agent循环状态
    agent_scratchpad: str  # 历史思考过程
    intermediate_steps: List[tuple]  # (AgentAction, str) 对列表
    iteration: int  # 当前迭代次数
    max_iterations: int  # 最大迭代数

    # 工具执行状态
    current_tool: Optional[str]  # 当前正在执行的工具
    tools_used: List[str]  # 使用过的所有工具
    execution_steps: List[ExecutionStep]  # 详细的执行步骤

    # 结果和评测
    final_answer: Optional[str]  # 最终答案
    evaluation_result: Optional[dict]  # 评测结果
    eval_passed: bool  # 是否通过评测
    eval_score: float  # 评测分数（0-1）

    # 错误和重试
    error_message: Optional[str]
    retry_count: int  # 重试次数

    # 记忆和上下文
    chat_history: List[BaseMessage]  # 聊天历史
    memory_context: Optional[str]  # 记忆提取的上下文

    # 观察脱敏
    observations: List[str]  # 原始观察
    masked_observations: List[str]  # 脱敏后的观察

    # 元信息
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    total_duration: float

    # ========== 多路径路由相关字段 ==========

    # 意图识别和路由
    intent_type: Optional[str]  # "knowledge" / "data" / "hybrid" / None

    # 知识路径字段
    clarified_terms: List[Dict[str, str]]  # [{"term": "A厂商", "meaning": "..."}]

    # 数据路径字段
    time_range: Optional[Dict[str, str]]  # {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
    relevant_tables: List[str]  # 相关的数据库表名
    relevant_fields: Dict[str, List[str]]  # {table_name: [field1, field2, ...]}
    field_samples: Dict[str, List[Any]]  # {table.field: [sample1, sample2, ...]} 字段采样值

    # 查询和结果
    sql_result: Optional[str]  # SQL查询结果
    explanation: Optional[str]  # 自然语言解释


def create_initial_state(
    user_input: str,
    user_id: str,
    agent_id: str,
    conversation_id: Optional[str] = None,
    max_iterations: int = 10
) -> AgentState:
    """创建初始Agent状态"""
    from datetime import datetime

    return {
        "user_input": user_input,
        "user_id": user_id,
        "agent_id": agent_id,
        "conversation_id": conversation_id,
        "agent_scratchpad": "",
        "intermediate_steps": [],
        "iteration": 0,
        "max_iterations": max_iterations,
        "current_tool": None,
        "tools_used": [],
        "execution_steps": [],
        "final_answer": None,
        "evaluation_result": None,
        "eval_passed": False,
        "eval_score": 0.0,
        "error_message": None,
        "retry_count": 0,
        "chat_history": [],
        "memory_context": None,
        "observations": [],
        "masked_observations": [],
        "start_time": datetime.now(),
        "end_time": None,
        "total_duration": 0.0,
        # 多路径路由字段初始化
        "intent_type": None,
        "clarified_terms": [],
        "time_range": None,
        "relevant_tables": [],
        "relevant_fields": {},
        "field_samples": {},
        "sql_result": None,
        "explanation": None,
    }
