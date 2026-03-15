import pytest
from datetime import datetime
from agents.langgraph_state import AgentState, create_initial_state, ExecutionStep


class TestAgentState:
    """验证Agent State结构"""

    def test_create_initial_state(self):
        """验证初始状态创建"""
        state = create_initial_state(
            user_input="test query",
            user_id="user123",
            agent_id="agent456"
        )

        assert state["user_input"] == "test query"
        assert state["user_id"] == "user123"
        assert state["agent_id"] == "agent456"
        assert state["iteration"] == 0
        assert state["max_iterations"] == 10
        assert state["eval_passed"] is False
        assert state["tools_used"] == []
        assert state["start_time"] is not None

    def test_state_field_types(self):
        """验证状态字段类型"""
        state = create_initial_state("query", "user", "agent")

        assert isinstance(state["user_input"], str)
        assert isinstance(state["iteration"], int)
        assert isinstance(state["tools_used"], list)
        assert isinstance(state["eval_score"], float)
        assert isinstance(state["chat_history"], list)

    def test_execution_step_creation(self):
        """验证执行步骤数据结构"""
        step = ExecutionStep(
            step_type="tool_call",
            tool_name="sql_query",
            tool_input="SELECT * FROM users",
            tool_output="2 rows returned",
            timestamp=datetime.now(),
            duration=1.5
        )

        assert step["step_type"] == "tool_call"
        assert step["tool_name"] == "sql_query"
        assert step["duration"] == 1.5
