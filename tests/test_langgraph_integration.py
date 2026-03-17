import pytest
from unittest.mock import Mock, patch
from agents.services.agent_service import AgentService


class TestLangGraphIntegration:
    """LangGraph与现有系统的集成测试"""

    @pytest.fixture
    def setup(self):
        """设置测试环境"""
        mock_llm = Mock()
        mock_llm.predict.return_value = "Thought: I need to search\nFinal Answer: Success"
        mock_tools = []

        return {
            "llm": mock_llm,
            "tools": mock_tools,
            "service": AgentService(mock_llm, mock_tools)
        }

    def test_integration_with_evaluation(self, setup):
        """验证与评测系统的集成"""
        result = setup["service"].execute_agent(
            agent_id="agent1",
            user_input="test query",
            user_id="user1",
            test_case={"expected": "Success"}
        )

        assert result["success"] is True
        assert "agent_output" in result

    def test_integration_with_memory(self, setup):
        """验证与记忆系统的集成"""
        result = setup["service"].execute_agent(
            agent_id="agent1",
            user_input="test query",
            user_id="user1",
            conversation_id="conv1"
        )

        assert result["success"] is True
        assert result["user_input"] == "test query"

    def test_multi_iteration_execution(self, setup):
        """验证多迭代执行"""
        result = setup["service"].execute_agent(
            agent_id="agent1",
            user_input="complex query requiring multiple steps",
            user_id="user1",
            max_iterations=5
        )

        assert result["success"] is True

    def test_error_with_detailed_info(self, setup):
        """验证详细的错误信息"""
        setup["service"].agent_graph.invoke = Mock(side_effect=ValueError("Invalid input"))

        result = setup["service"].execute_agent(
            agent_id="agent1",
            user_input="test query",
            user_id="user1"
        )

        assert result["success"] is False
        assert "Invalid input" in result["error_message"]
        assert result["status"] == "failed"

    def test_all_langgraph_tests_together(self, setup):
        """综合验证所有LangGraph组件"""
        # 执行第一次查询
        result1 = setup["service"].execute_agent(
            agent_id="agent1",
            user_input="First query",
            user_id="user1",
            conversation_id="conv1"
        )
        assert result1["success"] is True

        # 执行相关查询
        result2 = setup["service"].execute_agent(
            agent_id="agent1",
            user_input="Follow-up query",
            user_id="user1",
            conversation_id="conv1"
        )
        assert result2["success"] is True
