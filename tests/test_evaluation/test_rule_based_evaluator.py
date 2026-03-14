"""
RuleBasedEvaluator评测器测试 - 支持Rubric切换
"""

import pytest
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class MockExecution:
    """用于测试的模拟Execution对象"""
    agent_output: str
    tools_used: List[str]
    error_message: str
    execution_time: float


def test_evaluate_with_document_search_rubric():
    """测试文档搜索任务使用correct rubric"""
    from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

    # 创建mock execution
    execution = type('Execution', (), {
        'agent_output': '销售数据统计',
        'tools_used': ['document_search'],
        'error_message': '',
        'execution_time': 1.5,
        'execution_steps': []
    })()

    test_case = {
        'task_type': 'document_search',  # ← 指定任务类型
        'expected': {
            'keywords': ['销售', '数据', '统计'],
            'min_length': 30,
            'max_length': 5000,
            'should_NOT_contain': []
        }
    }

    evaluator = RuleBasedEvaluator()
    result = evaluator.evaluate(execution, test_case)

    # 验证使用了正确的rubric（权重应该是document_search的权重）
    assert result['score'] >= 0.0
    assert result['score'] <= 1.0
    assert 'details' in result
    assert 'keyword_coverage' in result['details']  # 应该有keyword_coverage维度
    assert result['detected_task_type'] == 'document_search'
    assert result['was_explicitly_set'] == True
    print(f"Document search evaluation: {result['score']}")


def test_evaluate_with_sql_query_rubric():
    """测试SQL查询任务使用correct rubric"""
    from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

    # SQL工具的原始输出（带表头和数据）
    sql_output = 'id\tproduct\tsales\n1\tA\t100\n2\tB\t200'

    execution = type('Execution', (), {
        'agent_output': '产品A销售额最高为100，产品B为200',
        'tools_used': ['sql_query'],
        'error_message': '',
        'execution_time': 0.8,
        'execution_steps': [
            {
                'step_type': 'tool_end',
                'tool_name': 'sql_query',
                'tool_output': sql_output,  # ← 单独的SQL输出，不是综合output
            }
        ]
    })()

    test_case = {
        'task_type': 'sql_query',  # ← 指定任务类型
        'expected': {
            'expected_min_rows': 1,
            'expected_max_rows': 100,
            'expected_columns': ['id', 'product', 'sales']
        }
    }

    evaluator = RuleBasedEvaluator()
    result = evaluator.evaluate(execution, test_case)

    # 关键验证：应该用sql工具的输出（2行数据）而非综合output
    assert 'sql_success' in result['details']  # SQL查询特定维度
    assert 'result_count' in result['details']
    assert result['details']['result_count']['actual_rows'] == 2  # ← 来自sql_output的行数
    assert result['detected_task_type'] == 'sql_query'
    assert result['was_explicitly_set'] == True
    print(f"SQL query evaluation: {result['score']}")


def test_default_rubric_when_task_type_missing():
    """测试缺少task_type时自动推断"""
    from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

    execution = type('Execution', (), {
        'agent_output': 'test output more text to reach minimum length',
        'tools_used': [],
        'error_message': '',
        'execution_time': 1.0,
        'execution_steps': []
    })()

    test_case = {
        # 没有指定task_type，应自动推断为document_search
        'expected': {
            'keywords': ['test'],
            'min_length': 30,
            'max_length': 5000
        }
    }

    evaluator = RuleBasedEvaluator()
    result = evaluator.evaluate(execution, test_case)

    assert 'keyword_coverage' in result['details']
    assert result['detected_task_type'] == 'document_search'  # 应该自动推断
    assert result['was_explicitly_set'] == False
    print(f"Auto-inferred document_search: {result['score']}")


def test_auto_infer_sql_from_tools_used():
    """测试自动推断：根据tools_used推断任务类型"""
    from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

    execution = type('Execution', (), {
        'agent_output': 'id\tproduct\tsales\n1\tA\t100',
        'tools_used': ['sql_query'],  # ← 明确指示是SQL任务
        'error_message': '',
        'execution_time': 0.8,
        'execution_steps': [
            {
                'step_type': 'tool_end',
                'tool_name': 'sql_query',
                'tool_output': 'id\tproduct\tsales\n1\tA\t100',
            }
        ]
    })()

    test_case = {
        # 没有显式task_type，但tools_used包含sql_query
        'expected': {
            'expected_min_rows': 1,
            'expected_max_rows': 100,
        }
    }

    evaluator = RuleBasedEvaluator()
    result = evaluator.evaluate(execution, test_case)

    # 应该自动推断为sql_query（基于tools_used）
    assert result['detected_task_type'] == 'sql_query'
    assert 'sql_success' in result['details']  # sql_query rubric的维度
    assert result['was_explicitly_set'] == False
    print(f"Auto-inferred sql_query: {result['score']}")

