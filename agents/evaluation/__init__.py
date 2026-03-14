"""
Agent评测系统模块

提供完整的Agent执行效果和性能评测框架
"""

from .rubrics import (
    # 新的数据类和函数
    CriterionConfig,
    RubricConfig,
    RUBRICS,
    DEFAULT_RUBRIC,
    get_rubric,
    # 向后兼容：保留旧的常量
    EXECUTION_RUBRIC,
    PERFORMANCE_METRICS,
    EVALUATION_THRESHOLD,
)
from .metrics import MetricsCalculator
from .judge import LLMJudge, LLMJudgeSync
from .evaluator import AgentEvaluator, EvaluationReport
from .rule_based_evaluator import RuleBasedEvaluator

__all__ = [
    # 新的数据类和函数
    "CriterionConfig",
    "RubricConfig",
    "RUBRICS",
    "DEFAULT_RUBRIC",
    "get_rubric",
    # 向后兼容：保留旧的常量
    "EXECUTION_RUBRIC",
    "PERFORMANCE_METRICS",
    "EVALUATION_THRESHOLD",
    # 核心类
    "MetricsCalculator",
    "LLMJudge",
    "LLMJudgeSync",
    "AgentEvaluator",
    "RuleBasedEvaluator",
    # 数据类
    "EvaluationReport",
]

__version__ = "1.0.0"