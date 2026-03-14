# agents/evaluation/rubrics.py

from dataclasses import dataclass
from typing import Dict, List, Any

@dataclass
class CriterionConfig:
    """单个评测维度配置"""
    name: str                    # 维度名称，如 "keyword_coverage"
    weight: float               # 权重，0-1
    description: str            # 描述
    applicable_task_types: List[str]  # 适用的任务类型

@dataclass
class RubricConfig:
    """评测标准配置"""
    task_type: str              # 任务类型，如 "document_search", "sql_query"
    criteria: List[CriterionConfig]  # 该任务类型的所有维度
    pass_threshold: float       # 通过阈值（0-1）
    description: str            # 该rubric的描述

# 定义所有Rubric配置
RUBRICS: Dict[str, RubricConfig] = {
    "document_search": RubricConfig(
        task_type="document_search",
        criteria=[
            CriterionConfig(
                name="keyword_coverage",
                weight=0.40,
                description="输出中包含的关键词比例",
                applicable_task_types=["document_search", "faq", "analysis"]
            ),
            CriterionConfig(
                name="length_ok",
                weight=0.30,
                description="输出长度是否合理",
                applicable_task_types=["document_search", "faq", "analysis"]
            ),
            CriterionConfig(
                name="no_bad_words",
                weight=0.20,
                description="不包含禁词",
                applicable_task_types=["document_search", "faq", "analysis"]
            ),
            CriterionConfig(
                name="tools_ok",
                weight=0.10,
                description="工具使用是否恰当",
                applicable_task_types=["document_search"]
            ),
        ],
        pass_threshold=0.75,
        description="文档搜索任务评测标准"
    ),

    "sql_query": RubricConfig(
        task_type="sql_query",
        criteria=[
            CriterionConfig(
                name="sql_success",
                weight=0.35,
                description="SQL是否成功执行",
                applicable_task_types=["sql_query"]
            ),
            CriterionConfig(
                name="result_count",
                weight=0.25,
                description="返回结果数量是否合理",
                applicable_task_types=["sql_query"]
            ),
            CriterionConfig(
                name="result_accuracy",
                weight=0.25,
                description="返回结果是否准确（如果有reference）",
                applicable_task_types=["sql_query"]
            ),
            CriterionConfig(
                name="performance",
                weight=0.15,
                description="查询执行效率",
                applicable_task_types=["sql_query"]
            ),
        ],
        pass_threshold=0.75,
        description="SQL查询任务评测标准"
    ),

    "analysis": RubricConfig(
        task_type="analysis",
        criteria=[
            CriterionConfig(
                name="metric_presence",
                weight=0.35,
                description="是否包含期望的指标",
                applicable_task_types=["analysis", "report"]
            ),
            CriterionConfig(
                name="numerical_accuracy",
                weight=0.35,
                description="数值准确性（如果有reference）",
                applicable_task_types=["analysis"]
            ),
            CriterionConfig(
                name="result_format",
                weight=0.20,
                description="结果格式是否清晰",
                applicable_task_types=["analysis", "report"]
            ),
            CriterionConfig(
                name="no_bad_words",
                weight=0.10,
                description="不包含禁词或不当表述",
                applicable_task_types=["analysis"]
            ),
        ],
        pass_threshold=0.75,
        description="数据分析任务评测标准"
    ),
}

# 默认Rubric（当task_type未指定时使用）
DEFAULT_RUBRIC = RUBRICS["document_search"]

def get_rubric(task_type: str) -> RubricConfig:
    """获取指定任务类型的Rubric，如果不存在则返回默认"""
    return RUBRICS.get(task_type, DEFAULT_RUBRIC)


# ============== 向后兼容性：保留旧的常量定义 ==============
# 这些在Task 2中将被重构

# ============== 执行效果评测标准 ==============
# 权重总和：100% = 1.0

EXECUTION_RUBRIC = {
    "accuracy": {
        "weight": 0.30,
        "description": "答案准确性（是否正确、符合预期）",
        "levels": {
            "excellent": (0.9, 1.0),      # 完全准确
            "good": (0.7, 0.9),           # 基本准确，细节差异
            "fair": (0.5, 0.7),           # 部分准确，有错误
            "poor": (0.0, 0.5),           # 主要错误或完全错误
        }
    },
    "completeness": {
        "weight": 0.20,
        "description": "任务完成度（是否完成了用户意图）",
        "levels": {
            "excellent": (0.9, 1.0),      # 完全完成所有要求
            "good": (0.7, 0.9),           # 完成大部分要求
            "fair": (0.5, 0.7),           # 完成50%以上要求
            "poor": (0.0, 0.5),           # 完成度低
        }
    },
    "clarity": {
        "weight": 0.20,
        "description": "可理解性（逻辑清晰度、结构化程度）",
        "levels": {
            "excellent": (0.9, 1.0),      # 极其清晰，结构完美
            "good": (0.7, 0.9),           # 清晰，流程清楚
            "fair": (0.5, 0.7),           # 基本清晰，有歧义
            "poor": (0.0, 0.5),           # 含糊不清，难以理解
        }
    },
    "tool_appropriateness": {
        "weight": 0.15,
        "description": "工具使用适当性（工具选择是否恰当、调用序列合理）",
        "levels": {
            "excellent": (0.9, 1.0),      # 工具选择完美，序列最优
            "good": (0.7, 0.9),           # 工具选择合理，序列可接受
            "fair": (0.5, 0.7),           # 工具选择有偏差，但可用
            "poor": (0.0, 0.5),           # 工具选择不当或调用错误
        }
    },
    "safety": {
        "weight": 0.15,
        "description": "安全性（SQL/API调用是否安全，无注入风险）",
        "levels": {
            "excellent": (0.9, 1.0),      # 完全安全，0风险
            "good": (0.7, 0.9),           # 基本安全，低风险
            "fair": (0.5, 0.7),           # 有安全隐患，但可控
            "poor": (0.0, 0.5),           # 高风险，存在注入/越权
        }
    }
}

# ============== 性能评测指标 ==============

PERFORMANCE_METRICS = {
    "response_time": {
        "weight": 0.30,
        "unit": "seconds",
        "description": "Agent响应时间",
        "target": 5.0,         # 目标：5秒内响应
        "acceptable": 10.0,    # 可接受：10秒内
    },
    "token_efficiency": {
        "weight": 0.35,
        "unit": "tokens",
        "description": "Token使用效率",
        "target": 1000,        # 目标：1000 tokens以内
        "acceptable": 2000,    # 可接受：2000 tokens以内
    },
    "tool_call_efficiency": {
        "weight": 0.20,
        "unit": "count",
        "description": "工具调用次数是否合理",
        "target": 3,           # 目标：平均3次以内
        "acceptable": 5,       # 可接受：5次以内
    },
    "success_rate": {
        "weight": 0.15,
        "unit": "percentage",
        "description": "成功率",
        "target": 0.95,        # 目标：95%成功率
        "acceptable": 0.85,    # 可接受：85%成功率
    }
}

# ============== 评测通过阈值 ==============

EVALUATION_THRESHOLD = {
    "passed": 0.75,              # 通过标准：总分≥75%
    "needs_improvement": 0.50,   # 需改进：总分50-75%
    "failed": 0.0,               # 失败：总分<50%
}

# ============== 权重和验证 ==============

def _validate_weights():
    """验证所有权重和为1.0"""
    execution_weight_sum = sum(dim["weight"] for dim in EXECUTION_RUBRIC.values())
    performance_weight_sum = sum(metric["weight"] for metric in PERFORMANCE_METRICS.values())

    assert abs(execution_weight_sum - 1.0) < 0.01, f"执行效果权重和为{execution_weight_sum}，应该为1.0"
    assert abs(performance_weight_sum - 1.0) < 0.01, f"性能指标权重和为{performance_weight_sum}，应该为1.0"

_validate_weights()
