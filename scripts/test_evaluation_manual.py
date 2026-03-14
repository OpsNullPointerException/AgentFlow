"""
手工验证RuleBasedEvaluator的评分合理性

测试策略：选择5个test cases，覆盖不同场景
1. Simple_001 - 完美回答（高分期望）
2. Simple_002 - 计算题不清晰（中分期望）
3. Medium_001 - 多工具正确（高分期望）
4. Edge_001 - 空结果处理（中低分期望）
5. Edge_002 - SQL注入防护（低分期望）
"""

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator
from agents.test_datasets.fixtures import SIMPLE_CASES, MEDIUM_CASES, EDGE_CASES


@dataclass
class MockExecution:
    """用于测试的模拟AgentExecution对象"""

    agent_output: str
    tools_used: List[str]
    status: str = "completed"


class EvaluationTestRunner:
    """评测测试运行器"""

    def __init__(self):
        self.evaluator = RuleBasedEvaluator()
        self.results = []

    def run_test(self, case_id: str, test_case: Dict[str, Any], execution: MockExecution, scenario: str, description: str) -> Dict[str, Any]:
        """运行单个测试"""
        print(f"\n{'='*70}")
        print(f"Case: {case_id} ({scenario})")
        print(f"Description: {description}")
        print(f"{'='*70}")

        # 运行评测
        result = self.evaluator.evaluate(execution, test_case)

        # 提取详细信息
        details = result["details"]

        # 输出结果
        print(f"\n输出内容: {execution.agent_output[:100]}...")
        print(f"使用工具: {execution.tools_used}")
        print(f"\n评测维度分析:")
        print(f"  关键词覆盖: {details['keyword_coverage']:.1%}")
        print(f"  长度检查: {'✓' if details['length_ok'] else '✗'} (预期范围: {test_case.get('expected', {}).get('min_length', 30)}-{test_case.get('expected', {}).get('max_length', 5000)}字)")
        print(f"  用词安全: {'✓' if details['no_bad_words'] else '✗'}")
        print(f"  工具使用: {details['tools_ok']:.1%}")
        print(f"\n最终结果:")
        print(f"  总分: {result['score']:.2f} / 1.00")
        print(f"  通过: {'✓ 通过' if result['passed'] else '✗ 失败'} (通过阈值: {self.evaluator.PASS_THRESHOLD})")
        print(f"  理由: {result['reasoning']}")

        # 记录结果
        test_result = {
            "case_id": case_id,
            "scenario": scenario,
            "score": result["score"],
            "passed": result["passed"],
            "details": details,
            "reasoning": result["reasoning"],
        }
        self.results.append(test_result)

        return result

    def run_all_tests(self):
        """运行所有测试"""
        # 测试1: Simple_001 - 完美回答
        print("\n" + "█" * 70)
        print("测试1: Simple_001 - 完美回答")
        print("█" * 70)

        test_case_1 = SIMPLE_CASES[0]  # 机器学习定义
        execution_1 = MockExecution(
            agent_output="""
机器学习是指：
1. 机器学习是一种让计算机学习和改进的方法
2. 通过算法和数据训练模型
3. 常见学习类型包括监督学习和无监督学习

这是一个全面的定义，包含了核心概念。机器学习在现代科技中发挥着重要作用。
            """.strip(),
            tools_used=["document_search"],
            status="completed",
        )
        self.run_test(
            "simple_001",
            test_case_1,
            execution_1,
            "完美回答",
            "基础定义查询，应该得高分"
        )

        # 测试2: Simple_002 - 计算题不清晰
        print("\n" + "█" * 70)
        print("测试2: Simple_002 - 计算题不清晰")
        print("█" * 70)

        test_case_2 = SIMPLE_CASES[1]  # 2+3×4=?
        execution_2 = MockExecution(
            agent_output="14",
            tools_used=["calculator"],
            status="completed",
        )
        self.run_test(
            "simple_002",
            test_case_2,
            execution_2,
            "不清晰",
            "计算题，虽然答案对但过程解释不足"
        )

        # 测试3: Medium_001 - 多工具正确
        print("\n" + "█" * 70)
        print("测试3: Medium_001 - 多工具正确")
        print("█" * 70)

        test_case_3 = MEDIUM_CASES[0]  # 销售数据分析
        execution_3 = MockExecution(
            agent_output="""
根据数据库查询（sql_query）和文档搜索（document_search）的结果，我可以提供以下分析：

产品A在上月销量最高，达到5000单，相比去年同期增长30%。
这主要得益于新推出的营销活动和改进的产品质量。

详细数据：
- 产品A: 5000单（环比↑30%）
- 产品B: 3500单（环比↑15%）
- 产品C: 2000单（环比↓5%）
            """.strip(),
            tools_used=["sql_query", "document_search"],
            status="completed",
        )
        self.run_test(
            "medium_001",
            test_case_3,
            execution_3,
            "多工具正确",
            "多工具调用，检查工具识别"
        )

        # 测试4: Edge_001 - 空结果处理
        print("\n" + "█" * 70)
        print("测试4: Edge_001 - 空结果处理")
        print("█" * 70)

        test_case_4 = EDGE_CASES[0]  # 查2025年1月数据（为空）
        execution_4 = MockExecution(
            agent_output="""
未找到2025年1月的销售数据。

原因是：2025年1月还未到达（当前日期为2024年12月），因此系统中没有该时期的数据记录。
建议：
1. 检查查询时间范围是否正确
2. 如需历史数据，可查询2024年1月-12月的数据
            """.strip(),
            tools_used=["sql_query"],
            status="completed",
        )
        self.run_test(
            "edge_001",
            test_case_4,
            execution_4,
            "空结果处理",
            "空结果，应该解释为什么空"
        )

        # 测试5: Edge_002 - SQL注入防护
        print("\n" + "█" * 70)
        print("测试5: Edge_002 - SQL注入防护")
        print("█" * 70)

        test_case_5 = EDGE_CASES[1]  # SQL注入
        execution_5 = MockExecution(
            agent_output="检测到恶意SQL语句，已拒绝执行。该输入包含SQL注入攻击特征。",
            tools_used=[],
            status="completed",
        )
        self.run_test(
            "edge_002",
            test_case_5,
            execution_5,
            "SQL注入防护",
            "安全防护，应该被拒绝"
        )

    def print_summary(self):
        """打印测试总结"""
        print("\n" + "=" * 70)
        print("测试结果总结")
        print("=" * 70)

        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r["passed"])
        total_score = sum(r["score"] for r in self.results) / total_tests if total_tests > 0 else 0

        print(f"\n统计信息:")
        print(f"  总测试数: {total_tests}")
        print(f"  通过数: {passed_tests}")
        print(f"  失败数: {total_tests - passed_tests}")
        print(f"  通过率: {passed_tests / total_tests * 100:.1f}%")
        print(f"  平均分: {total_score:.2f}")

        print(f"\n详细结果:")
        print(f"{'Case ID':<15} {'评分':<10} {'状态':<10} {'理由':<40}")
        print("-" * 75)

        for result in self.results:
            status = "✓ 通过" if result["passed"] else "✗ 失败"
            print(f"{result['case_id']:<15} {result['score']:.2f}{'':<6} {status:<10} {result['reasoning'][:38]:<40}")

        # 分析评分合理性
        print("\n" + "=" * 70)
        print("评分合理性分析")
        print("=" * 70)

        expectations = {
            "simple_001": (0.85, 1.0, "完美回答 - 应该得高分"),
            "simple_002": (0.40, 0.70, "不清晰 - 应该得中低分"),
            "medium_001": (0.75, 1.0, "多工具正确 - 应该得高分"),
            "edge_001": (0.55, 0.80, "空结果处理 - 应该得中等分"),
            "edge_002": (0.30, 0.60, "SQL注入防护 - 应该得低分（因为没用工具）"),
        }

        print("\n对标预期评分范围:")
        print(f"{'Case ID':<15} {'实际分':<10} {'预期范围':<20} {'符合':<10}")
        print("-" * 55)

        weight_adjustments = []

        for result in self.results:
            case_id = result["case_id"]
            actual_score = result["score"]

            if case_id in expectations:
                min_expected, max_expected, description = expectations[case_id]
                is_within_range = min_expected <= actual_score <= max_expected

                status_symbol = "✓" if is_within_range else "⚠️"
                print(f"{case_id:<15} {actual_score:.2f}{'':<6} [{min_expected:.2f}-{max_expected:.2f}]{'':<5} {status_symbol:<10}")

                if not is_within_range:
                    weight_adjustments.append((case_id, actual_score, min_expected, max_expected))

        # 权重调整建议
        print("\n" + "=" * 70)
        print("权重调整建议")
        print("=" * 70)

        if not weight_adjustments:
            print("\n✓ 所有评分符合预期，权重设置合理，无需调整。")
        else:
            print(f"\n⚠️ 发现{len(weight_adjustments)}个评分偏差：\n")
            for case_id, actual, min_exp, max_exp in weight_adjustments:
                deviation = "偏低" if actual < min_exp else "偏高"
                print(f"  • {case_id}: 实际{actual:.2f}，预期[{min_exp:.2f}-{max_exp:.2f}] ({deviation})")

            print("\n建议调整项：")
            print("  1. 检查各维度权重是否合理")
            print("  2. 关键词权重 (当前30%): 如果keyword_coverage导致评分偏低，可降至25%")
            print("  3. 长度权重 (当前25%): 如果长度检查过严格，可考虑调整min_length")
            print("  4. 安全权重 (当前20%): 如果安全检查太宽松，可提至25%")

        # 输出权重配置
        print("\n" + "=" * 70)
        print("当前权重配置")
        print("=" * 70)
        print(f"  关键词覆盖: {self.evaluator.WEIGHTS['keyword_coverage']:.0%}")
        print(f"  长度合理性: {self.evaluator.WEIGHTS['length_ok']:.0%}")
        print(f"  安全用词: {self.evaluator.WEIGHTS['no_bad_words']:.0%}")
        print(f"  工具使用: {self.evaluator.WEIGHTS['tools_ok']:.0%}")
        print(f"  通过阈值: {self.evaluator.PASS_THRESHOLD:.2f}")


def main():
    """主函数"""
    runner = EvaluationTestRunner()
    runner.run_all_tests()
    runner.print_summary()


if __name__ == "__main__":
    main()
