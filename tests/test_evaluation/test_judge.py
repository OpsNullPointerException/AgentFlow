"""
LLM-as-Judge评测器的单元测试
"""

import json
import pytest


class TestLLMJudge:
    """LLM-as-Judge评测器测试"""

    def test_build_evaluation_prompt(self):
        """测试：构建评测提示词"""
        from agents.evaluation.judge import LLMJudge
        from unittest.mock import MagicMock

        mock_llm_service = MagicMock()
        judge = LLMJudge(mock_llm_service)

        # 测试数据
        dimension = "accuracy"
        user_input = "什么是机器学习？"
        agent_output = "机器学习是一种人工智能技术，允许计算机从数据中学习。"
        execution_steps = [
            {"step_type": "action", "step_name": "document_search"},
            {"step_type": "finish", "step_name": "final_answer"},
        ]
        ground_truth = {"answer": "机器学习的定义"}
        rubric_config = {
            "weight": 0.30,
            "description": "答案准确性",
            "levels": {"excellent": (0.9, 1.0), "good": (0.7, 0.9)},
        }

        prompt = judge._build_evaluation_prompt(
            dimension=dimension,
            user_input=user_input,
            agent_output=agent_output,
            execution_steps=execution_steps,
            ground_truth=ground_truth,
            rubric_config=rubric_config,
        )

        # 验证：提示词包含关键信息
        assert "accuracy" in prompt
        assert "什么是机器学习" in prompt
        assert "机器学习是一种人工智能技术" in prompt
        assert len(prompt) > 100, "提示词太短"

    def test_parse_score_from_response(self):
        """测试：从LLM响应中解析评分"""
        from agents.evaluation.judge import LLMJudge
        from unittest.mock import MagicMock

        mock_llm_service = MagicMock()
        judge = LLMJudge(mock_llm_service)

        # 测试响应格式
        response = json.dumps({
            "score": 0.85,
            "reasoning": "答案准确且完整",
            "level": "good"
        })

        score = judge._parse_score(response)

        # 验证：能正确解析评分
        assert isinstance(score, float)
        assert 0 <= score <= 1
        assert score == 0.85

    def test_parse_score_handles_invalid_json(self):
        """测试：处理无效JSON响应"""
        from agents.evaluation.judge import LLMJudge
        from unittest.mock import MagicMock

        mock_llm_service = MagicMock()
        judge = LLMJudge(mock_llm_service)

        # 无效的JSON
        response = "Not valid JSON"

        # 应该返回一个有效的评分（降级处理）
        score = judge._parse_score(response)

        assert 0 <= score <= 1

    def test_parse_score_extracts_number_from_text(self):
        """测试：从文本中提取数字"""
        from agents.evaluation.judge import LLMJudge
        from unittest.mock import MagicMock

        mock_llm_service = MagicMock()
        judge = LLMJudge(mock_llm_service)

        # 文本格式的响应
        response = "I would rate this response 0.75 out of 1.0"

        score = judge._parse_score(response)

        assert isinstance(score, float)
        assert 0.70 <= score <= 0.80, f"应该接近0.75，实际为{score}"
