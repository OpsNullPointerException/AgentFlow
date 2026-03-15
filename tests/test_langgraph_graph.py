import pytest
from unittest.mock import Mock, MagicMock
from agents.langgraph_graph import AgentGraphBuilder, create_agent_graph
from agents.langgraph_state import create_initial_state


class TestAgentGraphBuilder:
    """验证Agent图构建"""

    @pytest.fixture
    def setup(self):
        """设置测试环境"""
        mock_llm = Mock()
        mock_tools = []

        return {
            "llm": mock_llm,
            "tools": mock_tools,
            "builder": AgentGraphBuilder(mock_llm, mock_tools)
        }

    def test_build_graph(self, setup):
        """验证图构建成功"""
        graph = setup["builder"].build()

        assert graph is not None
        # 验证graph有invoke方法
        assert hasattr(graph, 'invoke')

    def test_should_continue_loop_max_iterations(self, setup):
        """验证达到最大迭代数时停止"""
        state = create_initial_state("query", "user", "agent")
        state["iteration"] = 10
        state["max_iterations"] = 10

        result = setup["builder"]._should_continue_loop(state)

        assert result == "finish"

    def test_should_continue_loop_final_answer(self, setup):
        """验证检测到Final Answer时停止"""
        state = create_initial_state("query", "user", "agent")
        state["agent_scratchpad"] = "Thought: ...\nFinal Answer: Done"

        result = setup["builder"]._should_continue_loop(state)

        assert result == "finish"

    def test_should_continue_loop_continue(self, setup):
        """验证普通情况下继续循环"""
        state = create_initial_state("query", "user", "agent")
        state["iteration"] = 1
        state["agent_scratchpad"] = "Thought: I need more info"

        result = setup["builder"]._should_continue_loop(state)

        assert result == "continue"

    def test_create_agent_graph_function(self, setup):
        """验证便利函数"""
        graph = create_agent_graph(setup["llm"], setup["tools"])

        assert graph is not None
        assert hasattr(graph, 'invoke')
