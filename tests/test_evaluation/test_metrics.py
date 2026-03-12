"""
性能指标计算模块的单元测试
"""

import pytest


class TestMetricsCalculator:
    """性能指标计算器测试"""

    def test_calculate_response_time_score(self):
        """测试：响应时间评分计算"""
        from agents.evaluation.metrics import MetricsCalculator

        calc = MetricsCalculator()

        # 目标：5秒，超出则分数降低
        score_3s = calc.calculate_response_time_score(3.0)
        score_5s = calc.calculate_response_time_score(5.0)
        score_10s = calc.calculate_response_time_score(10.0)
        score_15s = calc.calculate_response_time_score(15.0)

        # 验证：时间越长，分数越低
        assert score_3s > score_5s > score_10s > score_15s
        # 验证：在可接受范围内分数较高
        assert score_5s > 0.7

    def test_calculate_token_efficiency_score(self):
        """测试：Token效率评分计算"""
        from agents.evaluation.metrics import MetricsCalculator

        calc = MetricsCalculator()

        # 目标：1000 tokens
        score_800 = calc.calculate_token_efficiency_score(800)
        score_1000 = calc.calculate_token_efficiency_score(1000)
        score_2000 = calc.calculate_token_efficiency_score(2000)
        score_3000 = calc.calculate_token_efficiency_score(3000)

        # 验证：token越少，分数越高
        assert score_800 > score_1000 > score_2000 > score_3000
        assert score_1000 >= 0.85

    def test_calculate_tool_call_efficiency_score(self):
        """测试：工具调用效率评分"""
        from agents.evaluation.metrics import MetricsCalculator

        calc = MetricsCalculator()

        score_2 = calc.calculate_tool_call_efficiency_score(2)
        score_3 = calc.calculate_tool_call_efficiency_score(3)
        score_5 = calc.calculate_tool_call_efficiency_score(5)
        score_8 = calc.calculate_tool_call_efficiency_score(8)

        assert score_2 > score_3 > score_5 > score_8

    def test_calculate_success_rate_score(self):
        """测试：成功率评分"""
        from agents.evaluation.metrics import MetricsCalculator

        calc = MetricsCalculator()

        score_98 = calc.calculate_success_rate_score(0.98)
        score_95 = calc.calculate_success_rate_score(0.95)
        score_85 = calc.calculate_success_rate_score(0.85)
        score_70 = calc.calculate_success_rate_score(0.70)

        assert score_98 > score_95 > score_85 > score_70
        assert score_95 >= 0.85

    def test_calculate_overall_performance_score(self):
        """测试：综合性能评分计算"""
        from agents.evaluation.metrics import MetricsCalculator

        calc = MetricsCalculator()

        performance_metrics = {
            "response_time": 3.0,
            "token_usage": 900,
            "tool_calls": 2,
            "success": True,
        }

        overall_score = calc.calculate_overall_performance_score(performance_metrics)

        # 验证：分数在0-1之间
        assert 0 <= overall_score <= 1
        # 验证：好的指标应该有较高的分数
        assert overall_score > 0.7
