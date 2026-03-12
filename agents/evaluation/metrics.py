"""
性能指标计算模块

负责计算Agent执行的性能指标评分
"""

from agents.evaluation.rubrics import PERFORMANCE_METRICS


class MetricsCalculator:
    """性能指标计算器"""

    def __init__(self):
        self.metrics = PERFORMANCE_METRICS

    def calculate_response_time_score(self, response_time: float) -> float:
        """
        计算响应时间评分

        Args:
            response_time: 响应时间（秒）

        Returns:
            float: 评分（0-1）
        """
        metric_config = self.metrics["response_time"]
        target = metric_config["target"]
        acceptable = metric_config["acceptable"]

        if response_time <= target:
            # 在目标范围内，分数0.9-1.0
            score = 0.9 + 0.1 * (1 - response_time / target)
        elif response_time <= acceptable:
            # 在可接受范围内，分数0.7-0.9
            score = 0.7 + 0.2 * (1 - (response_time - target) / (acceptable - target))
        else:
            # 超出可接受范围，分数递减
            excess = response_time - acceptable
            score = max(0.0, 0.7 - 0.1 * (excess / acceptable))

        return min(1.0, max(0.0, score))

    def calculate_token_efficiency_score(self, token_usage: int) -> float:
        """
        计算Token效率评分

        Args:
            token_usage: Token使用数

        Returns:
            float: 评分（0-1）
        """
        metric_config = self.metrics["token_efficiency"]
        target = metric_config["target"]
        acceptable = metric_config["acceptable"]

        if token_usage <= target:
            # 在目标范围内
            score = 0.95 + 0.05 * (1 - token_usage / target)
        elif token_usage <= acceptable:
            # 在可接受范围内
            score = 0.85 + 0.1 * (1 - (token_usage - target) / (acceptable - target))
        else:
            # 超出可接受范围
            excess = token_usage - acceptable
            score = max(0.0, 0.85 - 0.15 * (excess / acceptable))

        return min(1.0, max(0.0, score))

    def calculate_tool_call_efficiency_score(self, tool_calls: int) -> float:
        """
        计算工具调用效率评分

        Args:
            tool_calls: 工具调用次数

        Returns:
            float: 评分（0-1）
        """
        metric_config = self.metrics["tool_call_efficiency"]
        target = metric_config["target"]
        acceptable = metric_config["acceptable"]

        if tool_calls <= target:
            # 在目标范围内
            score = 0.95 - 0.05 * (tool_calls / target)
        elif tool_calls <= acceptable:
            # 在可接受范围内
            score = 0.85 - 0.1 * ((tool_calls - target) / (acceptable - target))
        else:
            # 超出可接受范围
            excess = tool_calls - acceptable
            score = max(0.0, 0.75 - 0.15 * (excess / acceptable))

        return min(1.0, max(0.0, score))

    def calculate_success_rate_score(self, success_rate: float) -> float:
        """
        计算成功率评分

        Args:
            success_rate: 成功率（0-1）

        Returns:
            float: 评分（0-1）
        """
        metric_config = self.metrics["success_rate"]
        target = metric_config["target"]  # 0.95
        acceptable = metric_config["acceptable"]  # 0.85

        if success_rate >= target:
            # 在目标范围内及以上：0.9-1.0
            score = 0.9 + 0.1 * min(1.0, (success_rate - target) / (1.0 - target))
        elif success_rate >= acceptable:
            # 在可接受范围内：0.7-0.9
            score = 0.7 + 0.2 * ((success_rate - acceptable) / (target - acceptable))
        else:
            # 低于可接受范围：0-0.7
            score = 0.7 * success_rate / acceptable

        return min(1.0, max(0.0, score))

    def calculate_overall_performance_score(self, performance_metrics: dict) -> float:
        """
        计算综合性能评分

        Args:
            performance_metrics: 性能指标字典，包含：
                - response_time: 响应时间（秒）
                - token_usage: Token使用数
                - tool_calls: 工具调用次数
                - success: 是否成功（bool）

        Returns:
            float: 综合性能评分（0-1）
        """
        # 计算各项评分
        response_time_score = self.calculate_response_time_score(
            performance_metrics.get("response_time", 0)
        )
        token_score = self.calculate_token_efficiency_score(
            performance_metrics.get("token_usage", 0)
        )
        tool_call_score = self.calculate_tool_call_efficiency_score(
            performance_metrics.get("tool_calls", 0)
        )

        # 成功率计算
        success_rate = 1.0 if performance_metrics.get("success", False) else 0.5
        success_score = self.calculate_success_rate_score(success_rate)

        # 加权求和
        weights = self.metrics
        overall_score = (
            response_time_score * weights["response_time"]["weight"]
            + token_score * weights["token_efficiency"]["weight"]
            + tool_call_score * weights["tool_call_efficiency"]["weight"]
            + success_score * weights["success_rate"]["weight"]
        )

        return overall_score
