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
    """Agent执行的完整状态 - 4层 + 元数据架构"""

    # ========== Group 1: 会话上下文 (6字段) ==========
    # 生命周期：全程保持不变，输入层
    user_input: str
    user_id: str
    agent_id: str
    conversation_id: Optional[str]
    memory_context: Optional[str]  # 历史对话上下文（属于输入，不是中间结果）

    # ========== Group 2: 执行追踪 (3字段) ==========
    # 生命周期：贯穿全程，LangGraph核心
    messages: Annotated[list[BaseMessage], "aggregated messages"]
    tools_used: List[str]
    execution_steps: List[ExecutionStep]

    # ========== Group 3: 任务执行 (8字段) ==========
    # 生命周期：按pipeline填充（意图→中间→结果）
    # 结构：意图识别 → 知识路径 → 数据路径 → 查询结果
    intent_type: Optional[str]  # "knowledge" / "data" / "hybrid"
    clarified_terms: List[Dict[str, str]]  # [{"term": "A", "meaning": "..."}]
    time_range: Optional[Dict[str, str]]  # {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
    relevant_tables: List[str]
    relevant_fields: Dict[str, List[str]]  # {table_name: [field1, field2, ...]}
    field_samples: Dict[str, List[Any]]  # {table.field: [sample1, sample2, ...]}
    sql_result: Optional[str]
    explanation: Optional[str]

    # ========== Group 4: 评测诊断 (9字段) ==========
    # 生命周期：最后阶段填充，结果判断和错误处理
    final_answer: Optional[str]
    evaluation_result: Optional[dict]
    eval_passed: bool
    eval_score: float
    error_message: Optional[str]
    error_diagnosis: Optional[str]  # "syntax_error" / "no_results" / "field_not_exists" / "timeout" / "invalid_answer"
    error_category: Optional[str]  # "retryable_logic_error" / "permanent_error" / "temporary_error"
    retry_count: int
    retry_strategy: Optional[str]  # "regenerate_sql" / "reprobe_fields" / "rediscover_schema" / "requery_knowledge"

    # ========== Metadata: 时间信息 (3字段) ==========
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    total_duration: float


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
        # ========== Group 1: 会话上下文 ==========
        "user_input": user_input,
        "user_id": user_id,
        "agent_id": agent_id,
        "conversation_id": conversation_id,
        "memory_context": None,

        # ========== Group 2: 执行追踪 ==========
        "messages": [],
        "tools_used": [],
        "execution_steps": [],

        # ========== Group 3: 任务执行 ==========
        "intent_type": None,
        "clarified_terms": [],
        "time_range": None,
        "relevant_tables": [],
        "relevant_fields": {},
        "field_samples": {},
        "sql_result": None,
        "explanation": None,

        # ========== Group 4: 评测诊断 ==========
        "final_answer": None,
        "evaluation_result": None,
        "eval_passed": False,
        "eval_score": 0.0,
        "error_message": None,
        "error_diagnosis": None,
        "error_category": None,
        "retry_count": 0,
        "retry_strategy": None,

        # ========== Metadata: 时间信息 ==========
        "start_time": datetime.now(),
        "end_time": None,
        "total_duration": 0.0,
    }
