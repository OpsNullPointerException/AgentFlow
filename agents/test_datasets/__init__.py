"""
评测系统的测试数据集模块

提供不同难度和场景的测试用例
"""

from .fixtures import (
    SIMPLE_CASES,
    MEDIUM_CASES,
    COMPLEX_CASES,
    EDGE_CASES as FIXTURE_EDGE_CASES,
    SCENARIO_CASES,
    ALL_CASES_BY_COMPLEXITY,
    STATISTICS,
)
from .scenarios import ALL_SCENARIOS, DOCUMENT_QA_SCENARIOS, DATA_ANALYSIS_SCENARIOS, RESEARCH_SCENARIOS
from .edge_cases import (
    ALL_EDGE_CASES,
    EDGE_CASES_BY_CATEGORY,
    SECURITY_EDGE_CASES,
    AMBIGUITY_EDGE_CASES,
    DATA_EDGE_CASES,
    PERFORMANCE_EDGE_CASES,
    CONTEXT_EDGE_CASES,
    LANGUAGE_EDGE_CASES,
)

__all__ = [
    # 基础测试用例
    "SIMPLE_CASES",
    "MEDIUM_CASES",
    "COMPLEX_CASES",
    "FIXTURE_EDGE_CASES",
    "SCENARIO_CASES",
    "ALL_CASES_BY_COMPLEXITY",
    "STATISTICS",
    # 场景化测试
    "ALL_SCENARIOS",
    "DOCUMENT_QA_SCENARIOS",
    "DATA_ANALYSIS_SCENARIOS",
    "RESEARCH_SCENARIOS",
    # 难案例
    "ALL_EDGE_CASES",
    "EDGE_CASES_BY_CATEGORY",
    "SECURITY_EDGE_CASES",
    "AMBIGUITY_EDGE_CASES",
    "DATA_EDGE_CASES",
    "PERFORMANCE_EDGE_CASES",
    "CONTEXT_EDGE_CASES",
    "LANGUAGE_EDGE_CASES",
    # 工具函数
    "get_test_cases",
    "get_statistics",
    "get_edge_cases",
]


def get_test_cases(complexity: str = "all", scenario: str = None):
    """
    获取测试用例

    Args:
        complexity: 复杂度级别 ('simple', 'medium', 'complex', 'edge', 'all')
        scenario: 场景 ('document_qa', 'data_analysis', 'research')

    Returns:
        list: 测试用例列表
    """
    cases = []

    if complexity == "all":
        cases = SIMPLE_CASES + MEDIUM_CASES + COMPLEX_CASES + FIXTURE_EDGE_CASES
    elif complexity in ALL_CASES_BY_COMPLEXITY:
        cases = ALL_CASES_BY_COMPLEXITY[complexity]

    if scenario:
        cases = [c for c in cases if c.get("scenario") == scenario]

    return cases


def get_statistics():
    """获取测试集统计"""
    return STATISTICS


def get_edge_cases(category: str = None):
    """
    获取难案例

    Args:
        category: 难案例分类 ('security', 'ambiguity', 'data', 'performance', 'context', 'language')

    Returns:
        list: 难案例列表
    """
    if category and category in EDGE_CASES_BY_CATEGORY:
        return EDGE_CASES_BY_CATEGORY[category]
    return ALL_EDGE_CASES
