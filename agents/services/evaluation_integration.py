"""
Agent服务与评测系统的集成

提供在Agent执行过程中进行自动评测的接口
"""

from typing import Optional, Dict, Any
from loguru import logger

from agents.evaluation import AgentEvaluator


class EvaluationIntegration:
    """Agent评测集成类"""

    def __init__(self):
        self.evaluator = AgentEvaluator()

    def evaluate_agent_execution(
        self,
        execution,
        ground_truth: Optional[Dict[str, Any]] = None,
        use_llm: bool = False,
    ) -> Dict[str, Any]:
        """
        评测Agent执行结果

        这个方法可以集成到agents/services/agent_service.py中

        Args:
            execution: AgentExecution对象
            ground_truth: 预期结果
            use_llm: 是否使用LLM进行详细评测

        Returns:
            Dict: 包含evaluation_report和evaluation_passed的字典
        """
        try:
            logger.info(f"开始评测Agent执行: {execution.id}")

            # 执行评测
            report = self.evaluator.evaluate_execution(
                execution, ground_truth=ground_truth, use_llm=use_llm
            )

            # 记录评测结果
            logger.info(
                f"评测完成 - 总分: {report.overall_score:.0%}, 状态: {report.status}"
            )

            # 返回结果
            return {
                "evaluation_report": report.to_dict(),
                "evaluation_passed": report.passed,
                "overall_score": report.overall_score,
            }

        except Exception as e:
            logger.error(f"评测失败: {e}")
            return {
                "evaluation_report": None,
                "evaluation_passed": False,
                "error": str(e),
            }

    def should_execute_evaluation(self, execution) -> bool:
        """
        判断是否应该对此次执行进行评测

        可根据配置、环境、执行状态等条件判断

        Args:
            execution: AgentExecution对象

        Returns:
            bool: 是否应该执行评测
        """
        # 只对完成或失败的执行进行评测
        if hasattr(execution, "status") and execution.status in ["completed", "failed"]:
            return True

        return False

    def get_evaluation_summary(self, evaluations: list) -> Dict[str, Any]:
        """
        生成多个评测结果的汇总

        Args:
            evaluations: 评测结果列表

        Returns:
            Dict: 汇总信息
        """
        if not evaluations:
            return {}

        scores = [e.get("overall_score", 0) for e in evaluations]
        passed = sum(1 for e in evaluations if e.get("evaluation_passed", False))

        return {
            "total_evaluations": len(evaluations),
            "passed": passed,
            "failed": len(evaluations) - passed,
            "average_score": sum(scores) / len(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "pass_rate": passed / len(evaluations) if evaluations else 0,
        }
