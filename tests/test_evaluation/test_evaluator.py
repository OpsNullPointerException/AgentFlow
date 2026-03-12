"""
核心评测引擎测试
"""

import pytest
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class MockExecution:
    """用于测试的模拟AgentExecution对象"""

    id: str
    user_input: str
    agent_output: str
    execution_steps: List[Dict[str, Any]]
    tools_used: List[str]
    status: str
    execution_time: float
    token_usage: Dict[str, int]


class TestAgentEvaluator:
    """Agent评测引擎测试"""

    def test_evaluator_initialization(self):
        """测试：评测引擎初始化"""
        from agents.evaluation.evaluator import AgentEvaluator

        evaluator = AgentEvaluator()

        assert evaluator is not None
        assert hasattr(evaluator, "evaluate_execution")
        assert hasattr(evaluator, "evaluate_batch")

    def test_evaluate_execution_returns_report(self):
        """测试：evaluate_execution返回评测报告"""
        from agents.evaluation.evaluator import AgentEvaluator

        evaluator = AgentEvaluator()

        # 创建模拟执行记录
        mock_execution = MockExecution(
            id="exec-001",
            user_input="什么是机器学习？",
            agent_output="机器学习是一种人工智能技术",
            execution_steps=[
                {
                    "step_type": "action",
                    "step_name": "document_search",
                    "duration": 1.5,
                }
            ],
            tools_used=["document_search"],
            status="completed",
            execution_time=2.0,
            token_usage={"prompt_tokens": 100, "completion_tokens": 50},
        )

        # 评测（使用同步模式）
        report = evaluator._evaluate_execution_sync(mock_execution)

        # 验证：报告包含必要字段
        assert report is not None
        assert "overall_score" in report
        assert "execution_scores" in report
        assert "performance_scores" in report
        assert 0 <= report["overall_score"] <= 1

    def test_calculate_overall_score(self):
        """测试：综合评分计算"""
        from agents.evaluation.evaluator import AgentEvaluator

        evaluator = AgentEvaluator()

        # 执行效果分数
        execution_scores = {
            "accuracy": 0.85,
            "completeness": 0.80,
            "clarity": 0.88,
            "tool_appropriateness": 0.78,
            "safety": 0.95,
        }

        # 性能分数
        performance_scores = {
            "response_time": 0.90,
            "token_efficiency": 0.85,
            "tool_call_efficiency": 0.80,
            "success_rate": 0.95,
        }

        overall = evaluator._calculate_overall_score(
            execution_scores, performance_scores, weight_execution=0.85, weight_performance=0.15
        )

        # 验证：总分在0-1之间
        assert 0 <= overall <= 1
        # 验证：好的分数应该有较高的总分
        assert overall > 0.7

    def test_generate_recommendations(self):
        """测试：生成改进建议"""
        from agents.evaluation.evaluator import AgentEvaluator

        evaluator = AgentEvaluator()

        execution_scores = {
            "accuracy": 0.85,
            "completeness": 0.60,  # 较低
            "clarity": 0.88,
            "tool_appropriateness": 0.50,  # 较低
            "safety": 0.95,
        }

        performance_scores = {
            "response_time": 15.0,  # 较高
            "token_efficiency": 2500,  # 较高
            "tool_calls": 6,  # 较高
            "success": True,
        }

        recommendations = evaluator._generate_recommendations(
            execution_scores, performance_scores
        )

        # 验证：返回建议列表
        assert isinstance(recommendations, list)
        assert len(recommendations) > 0
        # 验证：建议针对低分维度
        recommendations_text = " ".join(recommendations)
        assert any(
            word in recommendations_text
            for word in ["完成度", "工具", "性能", "优化"]
        )

    def test_evaluation_threshold_check(self):
        """测试：评测通过阈值检查"""
        from agents.evaluation.evaluator import AgentEvaluator

        evaluator = AgentEvaluator()

        # 通过情况
        report_passed = evaluator._check_evaluation_threshold(0.80)
        assert report_passed["passed"] is True
        assert report_passed["status"] == "通过"

        # 需改进情况
        report_improvement = evaluator._check_evaluation_threshold(0.65)
        assert report_improvement["passed"] is False
        assert report_improvement["status"] == "需改进"

        # 失败情况
        report_failed = evaluator._check_evaluation_threshold(0.40)
        assert report_failed["passed"] is False
        assert report_failed["status"] == "失败"
