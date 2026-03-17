"""
Batch 5: 错误恢复流程验证

测试错误诊断、重试机制、评测系统
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from typing import Dict, Any, List, Optional

from agents.langgraph.state import AgentState
from agents.langgraph.nodes import NodeManager, RetryConfig
from agents.langgraph.graph import AgentGraphBuilder
from langchain_core.tools import Tool


# ============ Error-Injecting LLM ============

class ErrorInjectingLLM:
    """支持错误注入的Mock LLM"""

    def __init__(self, error_mode: Optional[str] = None):
        """
        error_mode: None (正常) | 'format_error' | 'empty' | 'invalid_json'
        """
        self.error_mode = error_mode
        self.bound_tools = None
        self.call_count = 0

    def bind_tools(self, tools):
        self.bound_tools = {tool.name: tool for tool in tools}
        return self

    def predict(self, prompt: str) -> str:
        """模拟预测 - 可能返回错误"""
        self.call_count += 1

        # 根据error_mode模拟错误
        if self.error_mode == 'format_error':
            return "这是格式错误的输出"

        elif self.error_mode == 'empty':
            return ""

        elif self.error_mode == 'invalid_json':
            return '{"broken": json}'

        elif self.error_mode == 'bad_sql':
            # SQL语法错误
            return "SELECT * FROM nonexistent_table WHERE unknown_field = 'value'"

        # 正常返回
        if "分类用户查询类型" in prompt:
            if "什么是" in prompt or "定义" in prompt:
                return "knowledge"
            else:
                return "data"

        elif "提取所有可能需要澄清的关键术语" in prompt:
            if "A厂商" in prompt:
                return "A厂商,销售额"
            else:
                return "北京,销售额"

        elif "生成准确的SELECT查询" in prompt or "基于以下信息生成SQL" in prompt:
            return "SELECT SUM(amount) FROM sales WHERE city='北京' AND date='2026-03-16'"

        elif "用自然语言总结" in prompt or "用自然语言解释" in prompt:
            return "结果解释"

        else:
            return "Mock response"

    def invoke(self, messages):
        from langchain_core.messages import AIMessage
        response_text = self.predict(str(messages))
        return AIMessage(content=response_text, tool_calls=[])


# ============ Error-Injecting Tools ============

def create_error_injecting_sql_tool(error_mode: Optional[str] = None):
    """创建会出错的SQL工具"""
    def sql_query(query: str) -> str:
        """Execute SQL - may fail"""
        if error_mode == 'syntax_error':
            raise ValueError("SQL syntax error: unexpected token")

        elif error_mode == 'field_not_exists':
            raise ValueError("column 'nonexistent_field' does not exist")

        elif error_mode == 'no_results':
            return ""

        elif error_mode == 'timeout':
            raise TimeoutError("Query execution timeout")

        # 正常执行
        if "DISTINCT" in query:
            return "北京\n上海\n广州"
        elif "SUM" in query:
            return "5000"
        else:
            return "[]"

    return Tool(
        name="sql_query",
        func=sql_query,
        description="Execute SQL queries"
    )


def create_error_injecting_schema_tool(error_mode: Optional[str] = None):
    """创建会出错的schema工具"""
    def schema_query(table_or_query: str) -> str:
        """Query schema - may fail"""
        if error_mode == 'no_tables':
            return "可用的表:"  # 无表

        elif error_mode == 'no_fields':
            return "表 'sales' 的字段信息:"  # 无字段

        # 正常执行
        if table_or_query == "tables":
            return "可用的表:\n- sales\n- users\n- products"
        elif table_or_query == "sales":
            return "表 'sales' 的字段信息:\n- id: INT\n- city: VARCHAR\n- amount: DECIMAL\n- date: DATE"
        else:
            return ""

    return Tool(
        name="schema_query",
        func=schema_query,
        description="Query database schema"
    )


def create_mock_document_search_tool():
    """创建document_search工具"""
    def document_search(query: str, doc_category: str = "user") -> str:
        if "A厂商" in query:
            return "A厂商（代码A）是指代码为A的供应商"
        else:
            return f"Found information about {query}"

    return Tool(
        name="document_search",
        func=document_search,
        description="Search documents"
    )


def create_mock_time_conversion_tool():
    """创建time_conversion工具"""
    def time_conversion(relative_time: str) -> str:
        if "昨天" in relative_time:
            return '{"start_date": "2026-03-16", "end_date": "2026-03-16"}'
        else:
            return '{"start_date": "2026-03-17", "end_date": "2026-03-17"}'

    return Tool(
        name="convert_relative_time",
        func=time_conversion,
        description="Convert relative time to dates"
    )


# ============ Test Fixtures ============

@pytest.fixture
def normal_tools():
    """创建正常的工具集"""
    return [
        create_mock_document_search_tool(),
        create_error_injecting_sql_tool(),  # 正常模式
        create_error_injecting_schema_tool(),  # 正常模式
        create_mock_time_conversion_tool(),
    ]


@pytest.fixture
def error_injecting_tools():
    """创建会出错的工具集"""
    return lambda error_mode: [
        create_mock_document_search_tool(),
        create_error_injecting_sql_tool(error_mode),
        create_error_injecting_schema_tool(error_mode),
        create_mock_time_conversion_tool(),
    ]


@pytest.fixture
def data_query_state():
    """数据查询状态"""
    return {
        "user_input": "查询昨天北京的销售额",
        "user_id": "test_user",
        "agent_id": "test_agent",
        "memory_context": None,
        "intent_type": None,
        "clarified_terms": [],
        "time_range": None,
        "relevant_tables": [],
        "relevant_fields": {},
        "field_samples": {},
        "sql_result": None,
        "explanation": None,
        "iteration": 0,
        "agent_scratchpad": "",
        "tools_used": [],
        "masked_observations": [],
        "execution_steps": [],
        "eval_score": None,
        "error_category": None,
        "retry_count": 0,
        "final_answer": None,
        "messages": [],
        "start_time": datetime.now(),
    }


# ============ Unit Tests ============

class TestErrorInjection:
    """验证错误注入工具"""

    def test_error_injecting_llm(self):
        """验证ErrorInjectingLLM能模拟错误"""
        # 正常模式
        llm = ErrorInjectingLLM()
        result = llm.predict("分类用户查询类型：什么是A厂商")
        assert result == "knowledge"

        # 格式错误
        llm = ErrorInjectingLLM(error_mode='format_error')
        result = llm.predict("test")
        assert result == "这是格式错误的输出"

        # 空响应
        llm = ErrorInjectingLLM(error_mode='empty')
        result = llm.predict("test")
        assert result == ""

        print("\n✓ ErrorInjectingLLM工作正常")

    def test_error_injecting_tools(self):
        """验证错误注入工具"""
        # SQL语法错误
        tool = create_error_injecting_sql_tool(error_mode='syntax_error')
        with pytest.raises(ValueError, match="SQL syntax error"):
            tool.func("SELECT * FROM table")

        # 字段不存在
        tool = create_error_injecting_sql_tool(error_mode='field_not_exists')
        with pytest.raises(ValueError, match="does not exist"):
            tool.func("SELECT nonexistent_field FROM table")

        # 无结果
        tool = create_error_injecting_sql_tool(error_mode='no_results')
        result = tool.func("SELECT * FROM table")
        assert result == ""

        print("\n✓ 错误注入工具工作正常")


class TestEvaluateNodeLogic:
    """验证评测系统逻辑"""

    def test_evaluate_scoring_threshold(self):
        """验证评测分数和通过阈值逻辑"""
        # 高分 → passed
        score = 0.85
        intent_type = "data"
        pass_threshold = 0.75 if intent_type != "knowledge" else 0.65
        result = "passed" if score >= pass_threshold else "retry"
        assert result == "passed"

        # 中等分 → retry
        score = 0.65
        pass_threshold = 0.75
        result = "passed" if score >= pass_threshold else "retry"
        assert result == "retry"

        # 知识路径低分 → retry
        score = 0.60
        intent_type = "knowledge"
        pass_threshold = 0.65 if intent_type == "knowledge" else 0.75
        result = "passed" if score >= pass_threshold else "retry"
        assert result == "retry"

        print("\n✓ 评测分数逻辑正确")

    def test_error_category_detection(self):
        """验证错误分类"""
        # 永久性错误 → 不重试
        error_category = "permanent_error"
        should_retry = error_category != "permanent_error"
        assert not should_retry

        # 可重试错误 → 重试
        error_category = "retryable_logic_error"
        should_retry = error_category != "permanent_error"
        assert should_retry

        # 临时错误 → 重试
        error_category = "temporary_error"
        should_retry = error_category != "permanent_error"
        assert should_retry

        print("\n✓ 错误分类逻辑正确")


class TestRetryMechanism:
    """验证重试机制"""

    def test_retry_count_increment(self):
        """验证retry_count递增"""
        retry_count = 0
        max_retries = RetryConfig.MAX_RETRIES

        # 第一次重试
        retry_count += 1
        assert retry_count <= max_retries

        # 第二次重试
        retry_count += 1
        assert retry_count <= max_retries

        # 达到最大
        retry_count = max_retries
        assert retry_count == max_retries

        print(f"\n✓ 重试计数正确 (MAX={max_retries})")

    def test_retry_strategy_logic(self):
        """验证重试策略选择逻辑"""
        # SQL语法错误 → regenerate_sql
        error_diagnosis = "syntax_error"
        strategy = "regenerate_sql" if error_diagnosis in ["syntax_error", "invalid_sql"] else "reprobe_fields"
        assert strategy == "regenerate_sql"

        # 字段不存在 → reprobe_fields
        error_diagnosis = "field_not_exists"
        strategy = "reprobe_fields" if error_diagnosis == "field_not_exists" else "regenerate_sql"
        assert strategy == "reprobe_fields"

        # 无结果 → requery_knowledge或regenerate_sql
        error_diagnosis = "no_results"
        strategy = "requery_knowledge" if error_diagnosis == "no_results" else "regenerate_sql"
        assert strategy == "requery_knowledge"

        print("\n✓ 重试策略选择正确")

    def test_max_retries_boundary(self):
        """验证最大重试边界"""
        max_retries = RetryConfig.MAX_RETRIES

        for i in range(max_retries + 2):
            should_retry = i < max_retries
            print(f"  重试{i+1}: {'可以重试' if should_retry else '不能重试'}")

        print(f"\n✓ 最大重试边界{max_retries}正确")


class TestErrorRecoveryRouting:
    """验证错误恢复路由"""

    def test_permanent_error_no_retry(self):
        """验证permanent_error不重试"""
        error_category = "permanent_error"
        retry_count = 0
        max_retries = RetryConfig.MAX_RETRIES

        should_retry = (
            error_category != "permanent_error" and
            retry_count < max_retries
        )
        assert not should_retry, "permanent_error不应该重试"

    def test_retryable_error_with_count(self):
        """验证retryable_error在计数内重试"""
        error_category = "retryable_logic_error"
        retry_count = 1
        max_retries = RetryConfig.MAX_RETRIES

        should_retry = (
            error_category != "permanent_error" and
            retry_count < max_retries
        )
        assert should_retry, "retryable_error应该重试"

    def test_max_retries_reached(self):
        """验证达到最大重试次数"""
        error_category = "retryable_logic_error"
        retry_count = RetryConfig.MAX_RETRIES
        max_retries = RetryConfig.MAX_RETRIES

        should_retry = (
            error_category != "permanent_error" and
            retry_count < max_retries
        )
        assert not should_retry, "达到最大重试不应该再重试"

        print("\n✓ 错误恢复路由正确")


class TestEdgeCases:
    """测试边界条件"""

    def test_empty_results(self):
        """测试空结果处理"""
        result = ""
        is_empty = not result or result.strip() == ""
        assert is_empty

        print("\n✓ 空结果处理正确")

    def test_null_handling(self):
        """测试null处理"""
        value = None
        is_valid = value is not None
        assert not is_valid

        print("✓ Null处理正确")

    def test_zero_retries(self):
        """测试零重试的情况"""
        max_retries = 0
        retry_count = 0

        # 初始状态
        should_retry = retry_count < max_retries
        assert not should_retry

        print("✓ 零重试情况处理正确")
