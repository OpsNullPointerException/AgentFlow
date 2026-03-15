import pytest
from unittest.mock import Mock, patch
from agents.langgraph_service import LangGraphAgentService


class TestLangGraphAgentService:
    """验证LangGraphAgentService"""

    @pytest.fixture
    def setup(self):
        """设置测试环境"""
        mock_llm = Mock()
        mock_llm.predict.return_value = "Thought: Let me think\nFinal Answer: Done"
        mock_tools = []

        return {
            "llm": mock_llm,
            "tools": mock_tools,
            "service": LangGraphAgentService(mock_llm, mock_tools)
        }

    def test_service_initialization(self, setup):
        """验证服务初始化"""
        assert setup["service"].llm is not None
        assert setup["service"].tools == []
        assert setup["service"].agent_graph is not None

    def test_execute_agent_success(self, setup):
        """验证成功执行Agent"""
        result = setup["service"].execute_agent(
            agent_id="agent1",
            user_input="test query",
            user_id="user1"
        )

        assert result["success"] is True
        assert result["agent_id"] == "agent1"
        assert result["user_id"] == "user1"
        assert result["status"] == "completed"

    def test_execute_agent_with_conversation_id(self, setup):
        """验证带conversation_id的执行"""
        result = setup["service"].execute_agent(
            agent_id="agent1",
            user_input="test query",
            user_id="user1",
            conversation_id="conv1"
        )

        assert result["success"] is True
        assert "agent_output" in result

    def test_execute_agent_error_handling(self, setup):
        """验证错误处理"""
        # Mock graph.invoke抛出异常
        setup["service"].agent_graph.invoke = Mock(side_effect=Exception("Test error"))

        result = setup["service"].execute_agent(
            agent_id="agent1",
            user_input="test query",
            user_id="user1"
        )

        assert result["success"] is False
        assert result["status"] == "failed"
        assert "Test error" in result["error_message"]
