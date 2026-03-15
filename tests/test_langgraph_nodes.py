import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from agents.langgraph_nodes import NodeManager
from agents.langgraph_state import create_initial_state


class TestNodeManager:
    """验证Agent节点函数"""

    @pytest.fixture
    def setup(self):
        """设置测试环境"""
        mock_llm = Mock()
        mock_tools = []

        return {
            "llm": mock_llm,
            "tools": mock_tools,
            "manager": NodeManager(mock_llm, mock_tools)
        }

    def test_process_input_node(self, setup):
        """验证输入处理节点"""
        state = create_initial_state("test query", "user1", "agent1")

        result = setup["manager"].process_input_node(state)

        assert "memory_context" in result
        assert result["iteration"] == 0

    def test_agent_loop_node(self, setup):
        """验证Agent循环节点"""
        state = create_initial_state("test query", "user1", "agent1")
        setup["manager"].llm.predict.return_value = "Thought: I need to search\nAction: search\nAction Input: test"

        result = setup["manager"].agent_loop_node(state)

        assert "agent_scratchpad" in result
        assert result["iteration"] == 1
        assert len(result["execution_steps"]) == 1

    def test_final_answer_node(self, setup):
        """验证最终答案节点"""
        state = create_initial_state("test query", "user1", "agent1")
        state["agent_scratchpad"] = "Thought: ...\nFinal Answer: This is the answer"
        state["start_time"] = datetime.now()

        result = setup["manager"].final_answer_node(state)

        assert "This is the answer" in result["final_answer"]
        assert result["end_time"] is not None
        assert result["total_duration"] >= 0

    def test_error_handler_node(self, setup):
        """验证错误处理节点"""
        state = create_initial_state("test query", "user1", "agent1")
        state["error_message"] = "Test error"

        result = setup["manager"].error_handler_node(state)

        assert "Error" in result["final_answer"]
        assert result["error_message"] == "Test error"
