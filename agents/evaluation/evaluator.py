"""
核心评测引擎

负责协调所有评测模块，生成完整的评测报告
"""

import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from loguru import logger

from agents.evaluation.rubrics import (
    EXECUTION_RUBRIC,
    PERFORMANCE_METRICS,
    EVALUATION_THRESHOLD,
)
from agents.evaluation.metrics import MetricsCalculator
from agents.evaluation.judge import LLMJudgeSync


@dataclass
class EvaluationReport:
    """评测报告数据类"""

    execution_id: str
    agent_id: Optional[str] = None

    # 执行效果评分
    execution_scores: Dict[str, float] = None

    # 性能指标
    performance_scores: Dict[str, Any] = None

    # 安全性评分
    safety_scores: Dict[str, Any] = None

    # 综合评分
    overall_score: float = 0.0
    passed: bool = False
    status: str = "未知"

    # 改进建议
    recommendations: List[str] = None

    # 时间戳
    timestamp: datetime = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class AgentEvaluator:
    """Agent综合评测引擎"""

    def __init__(self, llm_service=None):
        """
        初始化评测引擎

        Args:
            llm_service: LLM服务实例（可选）
        """
        self.metrics_calculator = MetricsCalculator()
        self.llm_service = llm_service
        if llm_service:
            self.judge = LLMJudgeSync(llm_service)
        else:
            self.judge = None

    def evaluate_execution(
        self,
        execution,
        ground_truth: Optional[Dict[str, Any]] = None,
        use_llm: bool = False,
    ) -> EvaluationReport:
        """
        评测单个Agent执行结果

        Args:
            execution: Agent执行记录对象
            ground_truth: 预期结果（可选）
            use_llm: 是否使用LLM进行评测

        Returns:
            EvaluationReport: 评测报告
        """
        try:
            # 1. 执行效果评测
            execution_scores = self._evaluate_execution_quality(
                execution, ground_truth, use_llm=use_llm
            )

            # 2. 性能评测
            performance_scores = self._evaluate_performance(execution)

            # 3. 安全性评测
            safety_scores = self._evaluate_safety(execution)

            # 4. 综合评分
            overall_score = self._calculate_overall_score(
                execution_scores, performance_scores, weight_execution=0.85, weight_performance=0.15
            )

            # 5. 通过阈值检查
            threshold_result = self._check_evaluation_threshold(overall_score)

            # 6. 生成改进建议
            recommendations = self._generate_recommendations(execution_scores, performance_scores)

            # 7. 生成报告
            report = EvaluationReport(
                execution_id=str(execution.id if hasattr(execution, "id") else "unknown"),
                agent_id=str(execution.agent_id if hasattr(execution, "agent_id") else "unknown"),
                execution_scores=execution_scores,
                performance_scores=performance_scores,
                safety_scores=safety_scores,
                overall_score=overall_score,
                passed=threshold_result["passed"],
                status=threshold_result["status"],
                recommendations=recommendations,
                timestamp=datetime.now(),
            )

            logger.info(f"评测完成：{overall_score:.2%}，状态：{threshold_result['status']}")

            return report

        except Exception as e:
            logger.error(f"评测失败: {e}")
            return EvaluationReport(
                execution_id=str(execution.id if hasattr(execution, "id") else "unknown"),
                overall_score=0.5,
                passed=False,
                status="评测失败",
                recommendations=[f"评测过程出现错误: {str(e)}"],
                timestamp=datetime.now(),
            )

    def _evaluate_execution_sync(self, execution) -> Dict[str, Any]:
        """评测execution对象的简化版本（用于测试）"""
        execution_scores = self._evaluate_execution_quality(execution, None, use_llm=False)
        performance_scores = self._evaluate_performance(execution)
        overall = self._calculate_overall_score(execution_scores, performance_scores)

        return {
            "overall_score": overall,
            "execution_scores": execution_scores,
            "performance_scores": performance_scores,
        }

    def _evaluate_execution_quality(
        self,
        execution,
        ground_truth: Optional[Dict[str, Any]] = None,
        use_llm: bool = False,
    ) -> Dict[str, float]:
        """评测执行质量"""
        scores = {}

        # 如果有judge且use_llm=True，使用LLM评测
        if use_llm and self.judge:
            for dimension in EXECUTION_RUBRIC.keys():
                try:
                    score = self.judge.judge_dimension(
                        dimension=dimension,
                        agent_output=execution.agent_output if hasattr(execution, "agent_output") else "",
                        user_input=execution.user_input if hasattr(execution, "user_input") else "",
                        execution_steps=execution.execution_steps if hasattr(execution, "execution_steps") else [],
                        ground_truth=ground_truth,
                        rubric_config=EXECUTION_RUBRIC.get(dimension),
                    )
                    scores[dimension] = score
                except Exception as e:
                    logger.warning(f"LLM评测{dimension}失败，使用默认值: {e}")
                    scores[dimension] = 0.75
        else:
            # 使用规则-based评测（简化版）
            output_len = len(execution.agent_output if hasattr(execution, "agent_output") else "")
            scores["accuracy"] = min(1.0, 0.5 + output_len / 1000 * 0.5)  # 简化规则
            scores["completeness"] = 0.8 if output_len > 50 else 0.5
            scores["clarity"] = 0.85
            scores["tool_appropriateness"] = 0.8 if execution.tools_used else 0.5 if hasattr(execution, "tools_used") else 0.5
            scores["safety"] = 0.95

        return scores

    def _evaluate_performance(self, execution) -> Dict[str, Any]:
        """评测性能指标"""
        # 提取性能数据
        response_time = execution.execution_time if hasattr(execution, "execution_time") else 0
        token_usage = execution.token_usage if hasattr(execution, "token_usage") else {}
        total_tokens = token_usage.get("total_tokens", token_usage.get("prompt_tokens", 0) + token_usage.get("completion_tokens", 0))
        tool_calls = len(execution.tools_used) if hasattr(execution, "tools_used") else 0
        success = execution.status == "completed" if hasattr(execution, "status") else False

        # 计算性能指标
        performance_metrics = {
            "response_time": response_time,
            "token_usage": total_tokens,
            "tool_calls": tool_calls,
            "success": success,
        }

        # 获取各项评分
        overall_performance = self.metrics_calculator.calculate_overall_performance_score(
            performance_metrics
        )

        return {
            "response_time": response_time,
            "token_usage": total_tokens,
            "tool_calls": tool_calls,
            "success_rate": 1.0 if success else 0.0,
            "overall_score": overall_performance,
        }

    def _evaluate_safety(self, execution) -> Dict[str, Any]:
        """评测安全性"""
        safety_issues = []

        # 检查执行步骤中的SQL调用
        if hasattr(execution, "execution_steps"):
            for step in execution.execution_steps:
                if step.get("step_type") == "action" and step.get("step_name") == "sql_query":
                    # 这里可以添加更详细的SQL安全检查
                    pass

        return {
            "is_safe": len(safety_issues) == 0,
            "safety_level": "high" if len(safety_issues) == 0 else "medium" if len(safety_issues) <= 2 else "low",
            "issues": safety_issues,
        }

    def _calculate_overall_score(
        self,
        execution_scores: Dict[str, float],
        performance_scores: Dict[str, Any],
        weight_execution: float = 0.85,
        weight_performance: float = 0.15,
    ) -> float:
        """计算综合评分"""

        # 执行效果的加权平均
        execution_weight_sum = sum(EXECUTION_RUBRIC[dim]["weight"] for dim in execution_scores.keys())
        execution_avg = sum(
            execution_scores[dim] * EXECUTION_RUBRIC[dim]["weight"] / execution_weight_sum
            for dim in execution_scores.keys()
        )

        # 性能的加权平均（取overall_score）
        performance_avg = performance_scores.get("overall_score", 0.5)

        # 综合评分
        overall = execution_avg * weight_execution + performance_avg * weight_performance

        return min(1.0, max(0.0, overall))

    def _check_evaluation_threshold(self, overall_score: float) -> Dict[str, Any]:
        """检查评测通过阈值"""

        passed_threshold = EVALUATION_THRESHOLD["passed"]
        needs_improvement_threshold = EVALUATION_THRESHOLD["needs_improvement"]

        if overall_score >= passed_threshold:
            status = "通过"
            passed = True
        elif overall_score >= needs_improvement_threshold:
            status = "需改进"
            passed = False
        else:
            status = "失败"
            passed = False

        return {
            "passed": passed,
            "status": status,
            "score": overall_score,
            "threshold": passed_threshold,
        }

    def _generate_recommendations(
        self, execution_scores: Dict[str, float], performance_scores: Dict[str, Any]
    ) -> List[str]:
        """生成改进建议"""
        recommendations = []

        # 检查执行效果中的低分维度
        for dimension, score in execution_scores.items():
            if score < 0.70:
                dimension_name = {
                    "accuracy": "准确性",
                    "completeness": "完成度",
                    "clarity": "可理解性",
                    "tool_appropriateness": "工具适当性",
                    "safety": "安全性",
                }.get(dimension, dimension)

                recommendations.append(f"提升{dimension_name}，当前{score:.0%}")

        # 检查性能指标
        if performance_scores.get("response_time", 0) > 5:
            recommendations.append(f"缩短响应时间（当前{performance_scores['response_time']:.1f}秒）")

        if performance_scores.get("token_usage", 0) > 1000:
            recommendations.append(f"优化Token使用（当前{performance_scores['token_usage']}tokens）")

        if performance_scores.get("tool_calls", 0) > 3:
            recommendations.append(f"减少工具调用次数（当前{performance_scores['tool_calls']}次）")

        if not performance_scores.get("success", False):
            recommendations.append("提高执行成功率")

        return recommendations if recommendations else ["继续保持现有质量，各项指标已达标"]

    def evaluate_batch(self, test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量评测（简化版）

        Args:
            test_cases: 测试用例列表

        Returns:
            Dict: 汇总报告
        """
        logger.info(f"开始批量评测，共{len(test_cases)}个用例")

        results = []
        for i, test_case in enumerate(test_cases):
            logger.info(f"评测用例{i+1}/{len(test_cases)}: {test_case.get('name', '未名名')}")
            # 这里会调用evaluate_execution
            results.append({"test_case": test_case})

        return {
            "total_cases": len(test_cases),
            "results": results,
        }
