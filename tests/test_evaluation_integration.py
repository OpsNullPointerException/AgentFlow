"""
集成测试：验证完整的评测系统在生产环境中的工作情况

测试范围：
1. 文档搜索任务的完整评测流程
2. SQL查询任务的完整评测流程
3. 数据分析任务的完整评测流程
4. 边界情况处理
5. Rubric选择一致性
6. Auto task type inference准确性
7. metadata字段正确性
"""

import pytest
from dataclasses import dataclass
from typing import List, Dict, Any


# ============== Mock Execution Objects ==============

class MockExecution:
    """用于测试的模拟Execution对象"""

    def __init__(
        self,
        agent_output: str,
        tools_used: List[str] = None,
        error_message: str = "",
        execution_time: float = 1.0,
        execution_steps: List[Dict[str, Any]] = None
    ):
        self.agent_output = agent_output
        self.tools_used = tools_used or []
        self.error_message = error_message
        self.execution_time = execution_time
        self.execution_steps = execution_steps or []


# ============== Test Suite 1: Document Search Integration ==============

class TestDocumentSearchIntegration:
    """文档搜索任务的完整评测流程"""

    def test_complete_document_search_evaluation(self):
        """完整的文档搜索评测流程"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        # 创建mock execution
        execution = MockExecution(
            agent_output="机器学习是一种人工智能技术。机器学习使计算机能够从数据中学习。",
            tools_used=["document_search"],
            error_message="",
            execution_time=1.5,
            execution_steps=[
                {
                    'step_type': 'tool_end',
                    'tool_name': 'document_search',
                    'tool_output': "机器学习是一种人工智能技术。机器学习使计算机能够从数据中学习。"
                }
            ]
        )

        # 创建测试用例
        test_case = {
            'task_type': 'document_search',
            'expected': {
                'keywords': ['机器学习', '人工智能', '学习'],
                'min_length': 30,
                'max_length': 5000,
                'should_NOT_contain': [],
                'expected_tools': ['document_search']
            }
        }

        # 执行评测
        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 验证结果结构
        assert 'score' in result
        assert 'details' in result
        assert 'reasoning' in result
        assert 'passed' in result
        assert 'confidence' in result
        assert 'detected_task_type' in result
        assert 'was_explicitly_set' in result

        # 验证评测分数和通过状态
        assert 0.0 <= result['score'] <= 1.0
        assert result['score'] >= 0.6  # 应该能通过主要维度
        assert result['detected_task_type'] == 'document_search'
        assert result['was_explicitly_set'] == True

        # 验证所有维度的评测结果
        assert 'keyword_coverage' in result['details']
        assert 'length_ok' in result['details']
        assert 'no_bad_words' in result['details']
        assert 'tools_ok' in result['details']

        # 验证维度结构（score, justification, confidence）
        for dimension_key in result['details']:
            dimension = result['details'][dimension_key]
            assert 'score' in dimension
            assert 'justification' in dimension
            assert 'confidence' in dimension

    def test_keyword_coverage_accuracy(self):
        """验证keyword_coverage维度计算正确"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        # 场景1：全部关键词都找到
        execution = MockExecution(
            agent_output="API文档和教程",
            tools_used=["document_search"],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'document_search', 'tool_output': "API文档和教程"}
            ]
        )

        test_case = {
            'task_type': 'document_search',
            'expected': {
                'keywords': ['API', '文档', '教程'],
                'min_length': 10,
                'max_length': 1000
            }
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 应该找到所有关键词
        assert result['details']['keyword_coverage']['score'] == 1.0
        assert result['details']['keyword_coverage']['confidence'] >= 0.95

        # 场景2：部分关键词找到
        execution = MockExecution(
            agent_output="API使用指南",
            tools_used=["document_search"],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'document_search', 'tool_output': "API使用指南"}
            ]
        )

        test_case = {
            'task_type': 'document_search',
            'expected': {
                'keywords': ['API', '文档', '教程'],
                'min_length': 10,
                'max_length': 1000
            }
        }

        result = evaluator.evaluate(execution, test_case)

        # 应该找到1/3的关键词（API）
        assert result['details']['keyword_coverage']['score'] == pytest.approx(1/3, abs=0.01)

    def test_length_validation(self):
        """验证length_ok维度"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        evaluator = RuleBasedEvaluator()

        # 场景1：长度合理
        execution = MockExecution(
            agent_output="这是一个适当长度的文本。" * 5,
            tools_used=["document_search"],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'document_search', 'tool_output': "这是一个适当长度的文本。" * 5}
            ]
        )

        test_case = {
            'task_type': 'document_search',
            'expected': {
                'keywords': ['文本'],
                'min_length': 50,
                'max_length': 200
            }
        }

        result = evaluator.evaluate(execution, test_case)
        assert result['details']['length_ok']['score'] == 1.0

        # 场景2：文本过短
        execution = MockExecution(
            agent_output="短文本",
            tools_used=["document_search"],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'document_search', 'tool_output': "短文本"}
            ]
        )

        test_case = {
            'task_type': 'document_search',
            'expected': {
                'keywords': ['文本'],
                'min_length': 50,
                'max_length': 200
            }
        }

        result = evaluator.evaluate(execution, test_case)
        assert result['details']['length_ok']['score'] < 1.0  # 应该被扣分

        # 场景3：文本过长
        execution = MockExecution(
            agent_output="长文本。" * 100,
            tools_used=["document_search"],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'document_search', 'tool_output': "长文本。" * 100}
            ]
        )

        test_case = {
            'task_type': 'document_search',
            'expected': {
                'keywords': ['文本'],
                'min_length': 50,
                'max_length': 200
            }
        }

        result = evaluator.evaluate(execution, test_case)
        assert result['details']['length_ok']['score'] < 1.0  # 应该被扣分


# ============== Test Suite 2: SQL Query Integration ==============

class TestSQLQueryIntegration:
    """SQL查询任务的完整评测流程"""

    def test_complete_sql_query_evaluation(self):
        """完整的SQL查询评测流程"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        # SQL工具的原始输出
        sql_output = "product\tsales\nProduct A\t5000\nProduct B\t3000"

        execution = MockExecution(
            agent_output="根据查询，产品A销售额为5000，产品B为3000",
            tools_used=['sql_query'],
            error_message="",
            execution_time=0.8,
            execution_steps=[
                {
                    'step_type': 'tool_end',
                    'tool_name': 'sql_query',
                    'tool_output': sql_output
                }
            ]
        )

        test_case = {
            'task_type': 'sql_query',
            'expected': {
                'expected_min_rows': 1,
                'expected_max_rows': 100,
                'expected_output': "Product A\t5000\nProduct B\t3000",
                'expected_time': 2.0
            }
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 验证结果结构
        assert 'score' in result
        assert 'details' in result
        assert 'reasoning' in result
        assert 'passed' in result
        assert 'confidence' in result

        # 验证SQL评测维度
        assert 'sql_success' in result['details']
        assert 'result_count' in result['details']
        assert 'result_accuracy' in result['details']
        assert 'performance' in result['details']

        # 验证task_type和metadata
        assert result['detected_task_type'] == 'sql_query'
        assert result['was_explicitly_set'] == True

        # 验证SQL成功（无error_message）
        assert result['details']['sql_success']['score'] == 1.0

    def test_sql_success_check(self):
        """验证SQL成功执行检查"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        evaluator = RuleBasedEvaluator()

        # 场景1：SQL执行成功
        execution = MockExecution(
            agent_output="查询成功",
            tools_used=['sql_query'],
            error_message="",
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': "result: 100"}
            ]
        )

        test_case = {
            'task_type': 'sql_query',
            'expected': {}
        }

        result = evaluator.evaluate(execution, test_case)
        assert result['details']['sql_success']['score'] == 1.0

        # 场景2：SQL执行失败
        execution = MockExecution(
            agent_output="查询失败",
            tools_used=['sql_query'],
            error_message="Syntax error: invalid SQL",
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': ""}
            ]
        )

        test_case = {
            'task_type': 'sql_query',
            'expected': {}
        }

        result = evaluator.evaluate(execution, test_case)
        assert result['details']['sql_success']['score'] == 0.0

    def test_result_count_check(self):
        """验证结果行数检查"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        evaluator = RuleBasedEvaluator()

        # 场景1：返回合理的行数
        sql_output = "id\tname\n1\tAlice\n2\tBob\n3\tCharlie"

        execution = MockExecution(
            agent_output="查询结果",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': sql_output}
            ]
        )

        test_case = {
            'task_type': 'sql_query',
            'expected': {
                'expected_min_rows': 1,
                'expected_max_rows': 100
            }
        }

        result = evaluator.evaluate(execution, test_case)
        assert result['details']['result_count']['score'] == 1.0
        assert result['details']['result_count']['actual_rows'] == 3

    def test_result_accuracy_with_reference(self):
        """验证参考值准确性对比"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        evaluator = RuleBasedEvaluator()

        # 场景1：结果准确
        sql_output = "product\tsales\nA\t100\nB\t200"

        execution = MockExecution(
            agent_output="结果",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': sql_output}
            ]
        )

        test_case = {
            'task_type': 'sql_query',
            'expected': {
                'expected_output': "A\t100\nB\t200"
            }
        }

        result = evaluator.evaluate(execution, test_case)
        # 应该有较高的准确率
        assert result['details']['result_accuracy']['score'] >= 0.7

    def test_sql_zero_rows_valid(self):
        """边界情况：返回0行（假设min_rows=0）"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        evaluator = RuleBasedEvaluator()

        # 只有表头，无数据行（0行结果）
        sql_output = "product\tsales"

        execution = MockExecution(
            agent_output="查询完成，无结果",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': sql_output}
            ]
        )

        test_case = {
            'task_type': 'sql_query',
            'expected': {
                'expected_min_rows': 0,  # ← 允许返回0行
                'expected_max_rows': 100
            }
        }

        result = evaluator.evaluate(execution, test_case)
        assert result['details']['result_count']['score'] == 1.0
        assert result['details']['result_count']['actual_rows'] == 0


# ============== Test Suite 3: Analysis Integration ==============

class TestAnalysisIntegration:
    """数据分析任务的完整评测流程"""

    def test_complete_analysis_evaluation(self):
        """完整的分析任务评测流程"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        # SQL工具输出作为分析的数据来源
        sql_output = "product\tsales\n产品A\t5000\n产品B\t3000"

        execution = MockExecution(
            agent_output="产品A销售占比占比62%，产品B销售占比38%。总销售额为8000。",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': sql_output}
            ]
        )

        test_case = {
            'task_type': 'analysis',
            'expected': {
                'expected_metrics': ['占比', '销售'],
                'expected_format': 'summary',
                'expected_values': ['5000', '3000'],
                'allow_approximation': True
            }
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 验证结果结构
        assert 'score' in result
        assert 'details' in result
        assert 'reasoning' in result

        # 验证分析评测维度
        assert 'metric_presence' in result['details']
        assert 'numerical_accuracy' in result['details']
        assert 'result_format' in result['details']

        # 验证task_type和metadata
        assert result['detected_task_type'] == 'analysis'
        assert result['was_explicitly_set'] == True

    def test_metric_presence_check(self):
        """验证指标存在性检查"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        evaluator = RuleBasedEvaluator()

        # 场景1：包含所有期望的指标
        # 注意：analysis类型提取的是sql_query工具的输出，不是agent_output
        execution = MockExecution(
            agent_output="销售数据分析显示占比增长趋势",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': "销售数据占比增长"}
            ]
        )

        test_case = {
            'task_type': 'analysis',
            'expected': {
                'expected_metrics': ['销售', '占比', '增长'],
            }
        }

        result = evaluator.evaluate(execution, test_case)
        assert result['details']['metric_presence']['score'] == 1.0

        # 场景2：缺少部分指标
        execution = MockExecution(
            agent_output="销售数据分析",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': "销售数据"}
            ]
        )

        test_case = {
            'task_type': 'analysis',
            'expected': {
                'expected_metrics': ['销售', '占比', '增长', '预测'],
            }
        }

        result = evaluator.evaluate(execution, test_case)
        # 应该只找到1/4的指标
        assert result['details']['metric_presence']['score'] < 1.0

    def test_numerical_accuracy_with_reference(self):
        """验证数值准确性对比"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        evaluator = RuleBasedEvaluator()

        # 场景1：数值准确
        execution = MockExecution(
            agent_output="产品A销售额5000，产品B销售额3000",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': "A\t5000\nB\t3000"}
            ]
        )

        test_case = {
            'task_type': 'analysis',
            'expected': {
                'expected_values': ['5000', '3000'],
                'allow_approximation': False
            }
        }

        result = evaluator.evaluate(execution, test_case)
        assert result['details']['numerical_accuracy']['score'] >= 0.8

    def test_result_format_validation(self):
        """验证结果格式检查"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        evaluator = RuleBasedEvaluator()

        # 场景1：表格格式
        # 注意：analysis类型提取的是sql_query工具的输出
        execution = MockExecution(
            agent_output="产品\t销售\n产品A\t5000\n产品B\t3000",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': "product\tsales\nA\t5000"}
            ]
        )

        test_case = {
            'task_type': 'analysis',
            'expected': {
                'expected_format': 'table'
            }
        }

        result = evaluator.evaluate(execution, test_case)
        assert result['details']['result_format']['score'] == 1.0

        # 场景2：总结格式（tool_output包含总结关键词）
        execution = MockExecution(
            agent_output="总销售额为8000，共有2个产品",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': "总销售额为8000，共有2个产品"}
            ]
        )

        test_case = {
            'task_type': 'analysis',
            'expected': {
                'expected_format': 'summary'
            }
        }

        result = evaluator.evaluate(execution, test_case)
        assert result['details']['result_format']['score'] == 1.0


# ============== Test Suite 4: Auto Task Inference ==============

class TestAutoTaskInference:
    """验证auto task type inference"""

    def test_infer_from_explicit_task_type(self):
        """优先级1：显式指定的task_type"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        execution = MockExecution(
            agent_output="any output",
            tools_used=['document_search'],
            execution_steps=[]
        )

        # 显式指定为sql_query
        test_case = {
            'task_type': 'sql_query',
            'expected': {}
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 应该使用显式指定的task_type
        assert result['detected_task_type'] == 'sql_query'
        assert result['was_explicitly_set'] == True

    def test_infer_from_tools_used(self):
        """优先级2：根据tools_used推断"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        # 使用sql_query工具
        execution = MockExecution(
            agent_output="id\tname\n1\ttest",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': "id\tname\n1\ttest"}
            ]
        )

        # 不显式指定task_type
        test_case = {
            'expected': {}
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 应该从tools_used推断为sql_query
        assert result['detected_task_type'] == 'sql_query'
        assert result['was_explicitly_set'] == False

    def test_infer_from_output_pattern(self):
        """优先级3：根据output内容推断"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        # 输出包含表格结构和数字，但tools_used为空
        execution = MockExecution(
            agent_output="product\tsales\nA\t100\nB\t200",
            tools_used=[],
            execution_steps=[]
        )

        # 不显式指定task_type，不使用工具
        test_case = {
            'expected': {}
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 应该从output推断为sql_query（表格结构）
        assert result['detected_task_type'] == 'sql_query'
        assert result['was_explicitly_set'] == False

    def test_infer_analysis_from_output(self):
        """从output推断为analysis（包含统计关键词）"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        # 输出包含表格结构、数字和统计关键词
        execution = MockExecution(
            agent_output="product\tsales\nA\t100\nB\t200\n共计\t300（占比统计）",
            tools_used=[],
            execution_steps=[]
        )

        test_case = {
            'expected': {}
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 应该推断为analysis
        assert result['detected_task_type'] == 'analysis'

    def test_infer_default_when_ambiguous(self):
        """当无法推断时，默认为document_search"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        # 简单的文本输出
        execution = MockExecution(
            agent_output="这是一段普通的文本输出",
            tools_used=[],
            execution_steps=[]
        )

        test_case = {
            'expected': {}
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 应该默认为document_search
        assert result['detected_task_type'] == 'document_search'
        assert result['was_explicitly_set'] == False


# ============== Test Suite 5: Rubric Consistency ==============

class TestRubricConsistency:
    """验证Rubric一致性"""

    def test_correct_rubric_applied_for_document_search(self):
        """验证document_search任务应用正确的Rubric"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator
        from agents.evaluation.rubrics import RUBRICS

        execution = MockExecution(
            agent_output="关键词搜索结果文本长度足够",
            tools_used=['document_search'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'document_search', 'tool_output': "关键词搜索结果文本长度足够"}
            ]
        )

        test_case = {
            'task_type': 'document_search',
            'expected': {
                'keywords': ['关键词', '搜索'],
                'min_length': 10,
                'max_length': 1000
            }
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 验证使用了document_search的Rubric维度
        rubric = RUBRICS['document_search']
        criterion_names = {c.name for c in rubric.criteria}

        for dimension_name in result['details'].keys():
            assert dimension_name in criterion_names

    def test_correct_rubric_applied_for_sql_query(self):
        """验证sql_query任务应用正确的Rubric"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator
        from agents.evaluation.rubrics import RUBRICS

        execution = MockExecution(
            agent_output="查询结果",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': "id\tname\n1\ttest"}
            ]
        )

        test_case = {
            'task_type': 'sql_query',
            'expected': {}
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 验证使用了sql_query的Rubric维度
        rubric = RUBRICS['sql_query']
        criterion_names = {c.name for c in rubric.criteria}

        for dimension_name in result['details'].keys():
            assert dimension_name in criterion_names

    def test_correct_rubric_applied_for_analysis(self):
        """验证analysis任务应用正确的Rubric"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator
        from agents.evaluation.rubrics import RUBRICS

        execution = MockExecution(
            agent_output="产品销售统计分析",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': "product\tsales"}
            ]
        )

        test_case = {
            'task_type': 'analysis',
            'expected': {}
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 验证使用了analysis的Rubric维度
        rubric = RUBRICS['analysis']
        criterion_names = {c.name for c in rubric.criteria}

        for dimension_name in result['details'].keys():
            assert dimension_name in criterion_names

    def test_metadata_fields_correct(self):
        """验证metadata字段正确性"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        # 场景1：显式指定task_type
        execution = MockExecution(
            agent_output="output",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': "result"}
            ]
        )

        test_case = {
            'task_type': 'sql_query',
            'expected': {}
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        assert result['detected_task_type'] == 'sql_query'
        assert result['was_explicitly_set'] == True

        # 场景2：自动推断task_type
        execution = MockExecution(
            agent_output="output",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': "result"}
            ]
        )

        test_case = {
            'expected': {}
        }

        result = evaluator.evaluate(execution, test_case)

        assert result['detected_task_type'] == 'sql_query'
        assert result['was_explicitly_set'] == False


# ============== Test Suite 6: Edge Cases ==============

class TestEdgeCases:
    """边界情况处理"""

    def test_empty_output_handling(self):
        """处理空输出"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        execution = MockExecution(
            agent_output="",
            tools_used=[],
            execution_steps=[]
        )

        test_case = {
            'task_type': 'document_search',
            'expected': {
                'keywords': ['test'],
                'min_length': 30,
                'max_length': 5000
            }
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 空输出应该被低分
        assert result['score'] < 0.5
        assert result['details']['length_ok']['score'] < 1.0

    def test_null_execution_handling(self):
        """处理None execution"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        test_case = {
            'expected': {}
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(None, test_case)

        # 应该返回零评分结果
        assert result['score'] == 0.0
        assert result['passed'] == False
        assert result['confidence'] == 1.0

    def test_no_expected_requirements(self):
        """处理没有期望要求的情况"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        execution = MockExecution(
            agent_output="任意输出",
            tools_used=[],
            execution_steps=[]
        )

        test_case = {
            'task_type': 'document_search',
            'expected': {}
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 应该能正确处理
        assert 'score' in result
        assert 'details' in result

    def test_special_characters_in_keywords(self):
        """处理关键词中的特殊字符"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        execution = MockExecution(
            agent_output="API@2023相关内容API/REST教程",
            tools_used=['document_search'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'document_search', 'tool_output': "API@2023相关内容API/REST教程"}
            ]
        )

        test_case = {
            'task_type': 'document_search',
            'expected': {
                'keywords': ['API', 'REST'],
                'min_length': 10,
                'max_length': 1000
            }
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 应该能找到特殊字符中的关键词
        assert result['details']['keyword_coverage']['score'] >= 0.5


# ============== Test Suite 7: Integration Tests ==============

class TestIntegrationScenarios:
    """集成测试场景"""

    def test_multiple_evaluations_consistency(self):
        """多次评测的一致性"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        execution = MockExecution(
            agent_output="API文档和教程资源",
            tools_used=['document_search'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'document_search', 'tool_output': "API文档和教程资源"}
            ]
        )

        test_case = {
            'task_type': 'document_search',
            'expected': {
                'keywords': ['API', '文档'],
                'min_length': 10,
                'max_length': 1000
            }
        }

        evaluator = RuleBasedEvaluator()

        # 多次评测应该结果一致
        result1 = evaluator.evaluate(execution, test_case)
        result2 = evaluator.evaluate(execution, test_case)

        assert result1['score'] == result2['score']
        assert result1['passed'] == result2['passed']
        assert result1['confidence'] == result2['confidence']

    def test_document_search_with_tools_extraction(self):
        """文档搜索任务与工具输出提取"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        doc_search_output = "这是从文档搜索工具返回的文档内容，包含关键信息"

        execution = MockExecution(
            agent_output="综合的agent输出，包含多个工具的结果总结",
            tools_used=['document_search', 'other_tool'],
            execution_steps=[
                {
                    'step_type': 'tool_end',
                    'tool_name': 'document_search',
                    'tool_output': doc_search_output
                },
                {
                    'step_type': 'tool_end',
                    'tool_name': 'other_tool',
                    'tool_output': "其他工具的输出"
                }
            ]
        )

        test_case = {
            'task_type': 'document_search',
            'expected': {
                'keywords': ['文档', '内容'],
                'min_length': 30,
                'max_length': 5000
            }
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 应该从document_search工具提取输出进行评测
        assert result['details']['keyword_coverage']['score'] >= 0.5

    def test_sql_with_multiple_execution_steps(self):
        """SQL查询任务与多个execution_steps"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        sql_output = "id\tproduct\tsales\n1\tProduct A\t5000\n2\tProduct B\t3000"

        execution = MockExecution(
            agent_output="查询完成",
            tools_used=['sql_query', 'document_search'],
            execution_steps=[
                {
                    'step_type': 'tool_end',
                    'tool_name': 'document_search',
                    'tool_output': "不相关的文档"
                },
                {
                    'step_type': 'tool_end',
                    'tool_name': 'sql_query',
                    'tool_output': sql_output
                }
            ]
        )

        test_case = {
            'task_type': 'sql_query',
            'expected': {
                'expected_min_rows': 1,
                'expected_max_rows': 100
            }
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 应该正确提取sql_query工具的输出，返回2行
        assert result['details']['result_count']['actual_rows'] == 2

    def test_analysis_with_reference_values(self):
        """分析任务与参考值的准确性检查"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        sql_output = "category\tcount\nA\t100\nB\t200\nC\t300"

        execution = MockExecution(
            agent_output="分类A有100个，分类B有200个，分类C有300个。总计600个。",
            tools_used=['sql_query'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'sql_query', 'tool_output': sql_output}
            ]
        )

        test_case = {
            'task_type': 'analysis',
            'expected': {
                'expected_metrics': ['分类', '总计'],
                'expected_values': ['100', '200', '300'],
                'expected_format': 'summary',
                'allow_approximation': False
            }
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 应该检测到所有的数值
        assert result['details']['numerical_accuracy']['score'] >= 0.8

    def test_score_calculation_weighted_correctly(self):
        """验证加权评分计算正确"""
        from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

        execution = MockExecution(
            agent_output="测试文本输出",
            tools_used=['document_search'],
            execution_steps=[
                {'step_type': 'tool_end', 'tool_name': 'document_search', 'tool_output': "测试文本输出"}
            ]
        )

        test_case = {
            'task_type': 'document_search',
            'expected': {
                'keywords': ['测试'],
                'min_length': 10,
                'max_length': 1000
            }
        }

        evaluator = RuleBasedEvaluator()
        result = evaluator.evaluate(execution, test_case)

        # 验证加权分数在合理范围内
        assert 0.0 <= result['score'] <= 1.0

        # 详细分数应该也都在合理范围内
        for dimension_key in result['details']:
            dimension = result['details'][dimension_key]
            assert 0.0 <= dimension['score'] <= 1.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
