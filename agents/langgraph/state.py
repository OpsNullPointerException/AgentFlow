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
    """Agent执行的完整状态 - 精简版（LangGraph ToolNode架构）"""

    # 输入相关
    user_input: str
    user_id: str
    agent_id: str
    conversation_id: Optional[str]

    # LangGraph消息链
    messages: Annotated[list[BaseMessage], "aggregated messages"]

    # 工具执行追踪
    tools_used: List[str]
    execution_steps: List[ExecutionStep]

    # 结果和评测
    final_answer: Optional[str]
    evaluation_result: Optional[dict]
    eval_passed: bool
    eval_score: float

    # 错误和重试
    error_message: Optional[str]
    error_diagnosis: Optional[str]  # "syntax_error" / "no_results" / "field_not_exists" / "timeout" / "invalid_answer" / "evaluation_failed"
    error_category: Optional[str]  # "retryable_logic_error" / "permanent_error" / "temporary_error"
    retry_count: int
    retry_strategy: Optional[str]  # "regenerate_sql" / "reprobe_fields" / "rediscover_schema" / "requery_knowledge" / "give_up"

    # 记忆和上下文
    memory_context: Optional[str]

    # 元信息
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    total_duration: float

    # ========== 多路径路由相关字段 ==========

    # 意图识别
    intent_type: Optional[str]  # "knowledge" / "data" / "hybrid"

    # 知识路径
    clarified_terms: List[Dict[str, str]]  # [{"term": "A厂商", "meaning": "..."}]

    # 数据路径
    time_range: Optional[Dict[str, str]]  # {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
    relevant_tables: List[str]
    relevant_fields: Dict[str, List[str]]  # {table_name: [field1, field2, ...]}
    field_samples: Dict[str, List[Any]]  # {table.field: [sample1, sample2, ...]}

    # 查询结果
    sql_result: Optional[str]
    explanation: Optional[str]


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
        "messages": [],
        "tools_used": [],
        "execution_steps": [],
        "final_answer": None,
        "evaluation_result": None,
        "eval_passed": False,
        "eval_score": 0.0,
        "error_message": None,
        "error_diagnosis": None,
        "error_category": None,
        "retry_count": 0,
        "retry_strategy": None,
        "memory_context": None,
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
