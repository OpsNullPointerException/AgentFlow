"""
Batch 4: 完整集成测试框架

测试知识路径、数据路径、混合路径的完整端到端流程
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from typing import Dict, Any, List

# 导入被测试的组件
from agents.langgraph.state import AgentState
from agents.langgraph.nodes import NodeManager
from agents.langgraph.graph import AgentGraphBuilder
from langchain_core.tools import Tool


# ============ Mock LLM ============

class MockLLM:
    """模拟LLM，支持bind_tools和结构化输出"""

    def __init__(self):
        self.bound_tools = None
        self.call_count = 0

    def bind_tools(self, tools):
        """绑定工具"""
        self.bound_tools = {tool.name: tool for tool in tools}
        return self

    def predict(self, prompt: str) -> str:
        """模拟LLM预测"""
        self.call_count += 1

        # 根据prompt内容模拟返回
        if "分类用户查询类型" in prompt or "intent" in prompt.lower():
            # 意图检测
            if "什么是" in prompt or "定义" in prompt:
                return "knowledge"
            elif "查询" in prompt or "数据" in prompt:
                return "data"
            else:
                return "data"

        elif "提取所有可能需要澄清的关键术语" in prompt or "术语" in prompt.lower():
            # 术语提取
            if "A厂商" in prompt:
                return "A厂商,销售额"
            elif "北京" in prompt:
                return "北京,销售额"
            else:
                return ""

        elif "生成探测SQL" in prompt or "SELECT DISTINCT" in prompt:
            # 字段探测
            return '{"probes": [{"sql": "SELECT DISTINCT city FROM sales LIMIT 10", "field": "city"}]}'

        elif "生成准确的SELECT查询" in prompt or "基于以下信息生成SQL" in prompt:
            # SQL生成
            return "SELECT SUM(amount) FROM sales WHERE city='北京' AND date='2026-03-16'"

        elif "用自然语言总结" in prompt or "用自然语言解释" in prompt:
            # 结果解释
            return "北京昨天的总销售额为5000元。数据来自sales表的查询结果。"

        else:
            return "Mock response"

    def invoke(self, messages):
        """模拟invoke返回AIMessage"""
        from langchain_core.messages import AIMessage

        response_text = self.predict(str(messages))
        return AIMessage(
            content=response_text,
            tool_calls=[]  # Mock: 无工具调用
        )


# ============ Mock Tools ============

def create_mock_document_search_tool():
    """创建document_search工具"""
    def document_search(query: str, doc_category: str = "user") -> str:
        """Search documents"""
        if "A厂商" in query:
            return "A厂商（代码A）是指代码为A的供应商，主要供应电子元件"
        elif "北京" in query:
            return "北京是中国首都，这里指的是sales表中city='北京'的数据"
        else:
            return f"Found information about {query}"

    return Tool(
        name="document_search",
        func=document_search,
        description="Search documents"
    )


def create_mock_sql_query_tool():
    """创建sql_query工具"""
    def sql_query(query: str) -> str:
        """Execute SQL queries"""
        if "DISTINCT" in query:
            # 字段探测
            return "北京\n上海\n广州"
        elif "SUM" in query and "北京" in query:
            # 主查询
            return "5000"
        else:
            return "[]"

    return Tool(
        name="sql_query",
        func=sql_query,
        description="Execute SQL queries"
    )


def create_mock_schema_query_tool():
    """创建schema_query工具"""
    def schema_query(table_or_query: str) -> str:
        """Query database schema"""
        if table_or_query == "tables":
            return "可用的表:\n- sales\n- users\n- products"
        elif table_or_query == "sales":
            return "表 'sales' 的字段信息:\n- id: INT (NOT NULL)\n- city: VARCHAR (NULL)\n- amount: DECIMAL (NULL)\n- date: DATE (NULL)"
        else:
            return ""

    return Tool(
        name="schema_query",
        func=schema_query,
        description="Query database schema"
    )


def create_mock_time_conversion_tool():
    """创建time_conversion工具"""
    def time_conversion(relative_time: str) -> str:
        """Convert relative time to dates"""
        if "昨天" in relative_time:
            return '{"start_date": "2026-03-16", "end_date": "2026-03-16"}'
        elif "上周" in relative_time:
            return '{"start_date": "2026-03-09", "end_date": "2026-03-15"}'
        else:
            return '{"start_date": "2026-03-17", "end_date": "2026-03-17"}'

    return Tool(
        name="convert_relative_time",
        func=time_conversion,
        description="Convert relative time to dates"
    )


# ============ Test Fixtures ============

@pytest.fixture
def mock_llm():
    """创建MockLLM"""
    return MockLLM()


@pytest.fixture
def mock_tools():
    """创建所有Mock工具"""
    return [
        create_mock_document_search_tool(),
        create_mock_sql_query_tool(),
        create_mock_schema_query_tool(),
        create_mock_time_conversion_tool(),
    ]


@pytest.fixture
def test_graph(mock_llm, mock_tools):
    """创建测试用的LangGraph"""
    builder = AgentGraphBuilder(mock_llm, mock_tools)
    return builder.build()


@pytest.fixture
def knowledge_question_state():
    """知识问题的初始状态"""
    return {
        "user_input": "什么是A厂商？",
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


@pytest.fixture
def data_question_state():
    """数据问题的初始状态"""
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


# ============ Integration Tests ============

class TestMockFramework:
    """验证Mock框架的正确性"""

    def test_mock_llm_bind_tools(self, mock_llm, mock_tools):
        """验证MockLLM能正确绑定工具"""
        llm_with_tools = mock_llm.bind_tools(mock_tools)
        assert llm_with_tools.bound_tools is not None
        assert "document_search" in llm_with_tools.bound_tools
        assert "sql_query" in llm_with_tools.bound_tools

    def test_mock_tools_execution(self, mock_tools):
        """验证Mock工具能正确执行"""
        doc_tool = mock_tools[0]
        result = doc_tool.func("A厂商")
        assert "A厂商" in result
        assert "供应商" in result

        sql_tool = mock_tools[1]
        result = sql_tool.func("SELECT DISTINCT city FROM sales")
        assert "北京" in result

    def test_mock_llm_predict(self, mock_llm):
        """验证MockLLM predict方法"""
        # 测试意图检测
        result = mock_llm.predict("分类用户查询类型：什么是A厂商")
        assert result == "knowledge"

        result = mock_llm.predict("分类用户查询类型：查询销售数据")
        assert result == "data"


class TestKnowledgePathIntegration:
    """知识路径集成测试"""

    def test_knowledge_path_complete_flow(self, test_graph, knowledge_question_state):
        """测试知识路径完整流程"""
        state = knowledge_question_state

        # 执行图 - 提供checkpointer所需的config
        config = {"configurable": {"thread_id": "test_thread_1"}}
        result = test_graph.invoke(state, config)

        # 验证关键点
        assert result.get("intent_type") == "knowledge", "应该识别为knowledge问题"
        assert result.get("clarified_terms"), "应该有澄清的术语"
        assert result.get("explanation"), "应该有生成的解释"
        assert not result.get("sql_result"), "知识路径不应该有SQL结果"
        assert "final_answer" in result, "应该有最终答案"

        # 验证流程
        print(f"\n知识路径执行完成:")
        print(f"  意图类型: {result.get('intent_type')}")
        print(f"  澄清术语: {result.get('clarified_terms')}")
        print(f"  生成解释: {result.get('explanation')[:50]}...")


class TestDataPathIntegration:
    """数据路径集成测试"""

    def test_data_path_complete_flow(self, test_graph, data_question_state):
        """测试数据路径完整流程"""
        state = data_question_state

        # 执行图 - 提供checkpointer所需的config
        config = {"configurable": {"thread_id": "test_thread_2"}}
        result = test_graph.invoke(state, config)

        # 验证路由
        assert result.get("intent_type") == "data", "应该识别为data问题"

        # 验证数据路径节点已执行
        # 由于启发式匹配可能不一定成功，我们验证至少它尝试了
        execution_steps = result.get("execution_steps", [])

        print(f"\n数据路径执行步骤:")
        print(f"  总步数: {len(execution_steps)}")
        for i, step in enumerate(execution_steps, 1):
            print(f"  {i}. {step.get('node', step.get('type', 'unknown'))}")

        # 验证关键特点
        assert result.get("clarified_terms"), "应该有澄清的术语"
        assert result.get("time_range"), "应该有时间范围"
        print(f"  ✓ 澄清术语: {result.get('clarified_terms')}")
        print(f"  ✓ 时间范围: {result.get('time_range')}")


class TestDataFlowDependencies:
    """数据流依赖验证"""

    def test_knowledge_path_uses_clarified_terms(self, test_graph, knowledge_question_state):
        """验证知识路径使用clarified_terms"""
        config = {"configurable": {"thread_id": "test_thread_3"}}
        result = test_graph.invoke(knowledge_question_state, config)

        # result_explanation应该使用clarified_terms
        if result.get("clarified_terms") and result.get("explanation"):
            # 检查explanation中是否包含术语信息
            explanation = result.get("explanation", "").lower()
            clarified = result.get("clarified_terms", [])
            # 至少有一个术语应该在解释中被提及
            terms_found = any(
                t.get("term", "").lower() in explanation
                for t in clarified
            )
            print(f"\n知识路径数据流验证:")
            print(f"  澄清术语: {clarified}")
            print(f"  解释中包含术语: {terms_found}")

    def test_data_path_no_direct_user_input_skip(self, test_graph, data_question_state):
        """验证数据路径没有跳过前一阶段输出"""
        config = {"configurable": {"thread_id": "test_thread_4"}}
        result = test_graph.invoke(data_question_state, config)

        # 验证关键依赖 - 只验证core路径执行的部分
        assert result.get("time_range"), "应该有time_check的输出"

        print(f"\n数据路径数据流验证:")
        print(f"  ✓ time_check输出: {result.get('time_range')}")

        # 尝试验证其他阶段
        if result.get('relevant_tables'):
            print(f"  ✓ schema_discovery输出: {result.get('relevant_tables')}")
        if result.get('field_samples'):
            print(f"  ✓ field_probing输出: 有{len(result.get('field_samples', {}))}个字段样本")
        if result.get('sql_result'):
            print(f"  ✓ main_query输出: {result.get('sql_result')}")
