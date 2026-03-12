"""
评测标准库的单元测试
遵循TDD流程 - RED阶段：写失败的测试
"""

import pytest
from agents.evaluation.rubrics import (
    EXECUTION_RUBRIC,
    PERFORMANCE_METRICS,
    EVALUATION_THRESHOLD,
)


class TestExecutionRubric:
    """执行效果评测标准测试"""

    def test_execution_rubric_has_all_dimensions(self):
        """测试：执行效果rubric包含所有5个维度"""
        expected_dimensions = {
            "accuracy",
            "completeness",
            "clarity",
            "tool_appropriateness",
            "safety",
        }
        assert set(EXECUTION_RUBRIC.keys()) == expected_dimensions

    def test_each_dimension_has_weight(self):
        """测试：每个维度都有权重且权重和为1.0"""
        total_weight = 0
        for dimension, config in EXECUTION_RUBRIC.items():
            assert "weight" in config, f"{dimension}缺少weight字段"
            assert isinstance(config["weight"], (int, float))
            assert 0 < config["weight"] <= 1, f"{dimension}的weight无效"
            total_weight += config["weight"]

        # 权重和应该接近1.0（允许浮点误差）
        assert abs(total_weight - 1.0) < 0.01, f"权重和为{total_weight}，应该为1.0"

    def test_each_dimension_has_levels(self):
        """测试：每个维度都有评分等级"""
        expected_levels = {"excellent", "good", "fair", "poor"}
        for dimension, config in EXECUTION_RUBRIC.items():
            assert "levels" in config, f"{dimension}缺少levels字段"
            assert set(config["levels"].keys()) == expected_levels, f"{dimension}的levels不完整"

    def test_level_scores_are_valid_ranges(self):
        """测试：每个等级的分数范围有效（0-1之间）"""
        for dimension, config in EXECUTION_RUBRIC.items():
            for level, (min_score, max_score) in config["levels"].items():
                assert 0 <= min_score <= 1, f"{dimension}/{level}的min_score无效"
                assert 0 <= max_score <= 1, f"{dimension}/{level}的max_score无效"
                assert min_score <= max_score, f"{dimension}/{level}的范围无效"


class TestPerformanceMetrics:
    """性能评测指标测试"""

    def test_performance_metrics_has_required_fields(self):
        """测试：性能指标包含所有必要字段"""
        required_metrics = {
            "response_time",
            "token_efficiency",
            "tool_call_efficiency",
            "success_rate",
        }
        assert set(PERFORMANCE_METRICS.keys()) == required_metrics

    def test_each_metric_has_weight(self):
        """测试：每个指标都有权重"""
        total_weight = 0
        for metric, config in PERFORMANCE_METRICS.items():
            assert "weight" in config, f"{metric}缺少weight字段"
            total_weight += config["weight"]

        # 权重和应该为1.0
        assert abs(total_weight - 1.0) < 0.01

    def test_each_metric_has_targets(self):
        """测试：每个指标都有目标值和可接受值"""
        for metric, config in PERFORMANCE_METRICS.items():
            assert "target" in config, f"{metric}缺少target字段"
            assert "acceptable" in config, f"{metric}缺少acceptable字段"


class TestEvaluationThreshold:
    """评测阈值测试"""

    def test_threshold_values_valid(self):
        """测试：评测阈值有效（0-1之间且递减）"""
        assert "passed" in EVALUATION_THRESHOLD
        assert "needs_improvement" in EVALUATION_THRESHOLD
        assert "failed" in EVALUATION_THRESHOLD

        passed = EVALUATION_THRESHOLD["passed"]
        needs_improvement = EVALUATION_THRESHOLD["needs_improvement"]
        failed = EVALUATION_THRESHOLD["failed"]

        # 检查范围
        assert 0 <= failed <= needs_improvement <= passed <= 1
        # 检查通过标准通常是75%
        assert passed >= 0.7, "通过标准应该至少是0.7"
