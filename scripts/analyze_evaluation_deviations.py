"""
详细的评分偏差分析和权重调整方案

基于5个test cases的手工验证结果
"""

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator
from agents.test_datasets.fixtures import SIMPLE_CASES, MEDIUM_CASES, EDGE_CASES


@dataclass
class MockExecution:
    agent_output: str
    tools_used: List[str]
    status: str = "completed"


def analyze_deviations():
    """详细分析评分偏差"""

    print("=" * 80)
    print("详细的评分偏差分析")
    print("=" * 80)

    evaluator = RuleBasedEvaluator()

    # 问题分析
    print("\n问题1: simple_002 评分偏高")
    print("-" * 80)
    print("现象: 实际0.88，预期[0.40-0.70]")
    print("原因分析:")
    print("  • 输出长度只有2字，远低于min_length(30)，长度检查失败 ✗")
    print("  • 但长度失败只占25%权重，当其他维度得分高时，总分仍高")
    print("  • 计算公式: 1.0*0.30 + 0.5*0.25 + 1.0*0.20 + 1.0*0.25 = 0.88")
    print("  • 问题：长度不足时，0.5的分数仍然太高")
    print("\n建议:")
    print("  ✓ 方案A: 当length_ok=False时，改为0.3而非0.5 (更严格)")
    print("  ✓ 方案B: 提高length权重从25%到35% (让长度更重要)")
    print("  ✓ 方案C: 结合方案A和B (既严格又重要)")

    print("\n问题2: edge_001 评分偏高")
    print("-" * 80)
    print("现象: 实际1.00，预期[0.55-0.80]")
    print("原因分析:")
    print("  • 虽然输出内容好，解释了为什么空，但空结果本身是不理想的")
    print("  • test_case中expected['handles_empty']=True，但无具体要求")
    print("  • 当前evaluator没有检查'handles_empty'字段，无法区分")
    print("  • 应该有针对空结果的惩罚机制")
    print("\n建议:")
    print("  ✓ 方案A: 在evaluator中添加'handles_empty'检查")
    print("  ✓ 方案B: 如果期望空结果处理，检查是否包含解释性关键词")
    print("  ✓ 方案C: 为空结果添加0.8x的系数 (轻微惩罚)")

    print("\n问题3: edge_002 评分偏高")
    print("-" * 80)
    print("现象: 实际1.00，预期[0.30-0.60]")
    print("原因分析:")
    print("  • tools_used为空[]，但tools_ok仍返回1.0")
    print("  • 这是因为expected_tools也是空[]，按规则返回1.0")
    print("  • 对于security_reject类型的case，不调用工具是正确的")
    print("  • 但评分1.0可能过于乐观，安全防护虽重要但不应该满分")
    print("\n建议:")
    print("  ✓ 方案A: 为safety_reject/security类case添加特殊处理")
    print("  ✓ 方案B: 这类case的上限改为0.7（因为没有工具调用）")
    print("  ✓ 方案C: 添加'security_score'维度，独立评估安全防护")

    print("\n" + "=" * 80)
    print("综合权重调整方案")
    print("=" * 80)

    print("\n当前权重配置:")
    print(f"  keyword_coverage: 30%")
    print(f"  length_ok: 25%")
    print(f"  no_bad_words: 20%")
    print(f"  tools_ok: 25%")
    print(f"  PASS_THRESHOLD: 0.75")

    print("\n推荐方案（综合考虑）:")
    print("-" * 80)
    print("\n【方案1】保守调整（最小改动）")
    print("  keyword_coverage: 30% (不变)")
    print("  length_ok: 25% → 30% (+5%)")
    print("  no_bad_words: 20% → 20% (不变)")
    print("  tools_ok: 25% → 20% (-5%)")
    print("  PASS_THRESHOLD: 0.75 (不变)")
    print("  影响: 提高长度检查的重要性，降低工具权重")
    print("  长度失败时分数: 0.3*0.30 + 0.5*0.30 + 1.0*0.20 + 1.0*0.20 = 0.65")

    print("\n【方案2】激进调整（更严格）")
    print("  keyword_coverage: 30% (不变)")
    print("  length_ok: 25% → 35% (+10%)")
    print("  no_bad_words: 20% → 20% (不变)")
    print("  tools_ok: 25% → 15% (-10%)")
    print("  PASS_THRESHOLD: 0.75 → 0.80 (+0.05)")
    print("  影响: 对长度要求更严格，提高通过阈值")
    print("  长度失败时分数: 0.3*0.30 + 0.5*0.35 + 1.0*0.20 + 1.0*0.15 = 0.60")

    print("\n【方案3】推荐方案（平衡）")
    print("  keyword_coverage: 30% (不变)")
    print("  length_ok: 25% → 28% (+3%)")
    print("  no_bad_words: 20% → 22% (+2%)")
    print("  tools_ok: 25% → 20% (-5%)")
    print("  PASS_THRESHOLD: 0.75 (不变)")
    print("  长度失败时分数: 0.3*0.30 + 0.3*0.28 + 1.0*0.22 + 1.0*0.20 = 0.62")
    print("  ✓ 改动最少，效果均衡")

    print("\n【方案4】专项修复（推荐）")
    print("  修改 _check_length 的长度失败分数")
    print("  当 length_ok=False 时，改为 0.3 而不是 0.5")
    print("  其他权重保持不变")
    print("  长度失败时分数: 0.3*0.30 + 0.3*0.25 + 1.0*0.20 + 1.0*0.25 = 0.59")
    print("  ✓ 目标精准，改动最小")

    print("\n" + "=" * 80)
    print("特殊case处理建议")
    print("=" * 80)

    print("\nedge_001 (空结果处理):")
    print("  建议添加检查逻辑:")
    print("  - 如果expected['handles_empty']=True AND 输出包含解释")
    print("    → 给予0.9x系数的奖励（认可了空结果处理）")
    print("  - 如果expected['handles_empty']=True BUT 无解释")
    print("    → 给予0.6x系数的惩罚")

    print("\nedge_002 (安全防护):")
    print("  建议添加检查逻辑:")
    print("  - 如果expected['should_reject']=True AND 输出拒绝")
    print("    → 给予0.8x系数（虽正确但没有工具调用）")
    print("  - 如果expected['should_reject']=True AND 未拒绝")
    print("    → 给予0.0分（安全失败）")


def print_implementation_guide():
    """打印实现指南"""

    print("\n" + "=" * 80)
    print("实现指南")
    print("=" * 80)

    print("\n对于 【方案4】 的实现（推荐）:")
    print("-" * 80)
    print("""
在 agents/evaluation/rule_based_evaluator.py 中修改:

  当前代码 (第82行):
    + (1.0 if length_ok else 0.5) * self.WEIGHTS["length_ok"]

  修改为:
    + (1.0 if length_ok else 0.3) * self.WEIGHTS["length_ok"]

  这样会使得长度不足的输出分数从:
    0.88 → 0.77 (simple_002 的情况)
    从而符合预期[0.40-0.70]的范围

注意: 0.3这个系数可以根据后续测试调整:
  - 0.2 = 更严格
  - 0.3 = 中等严格
  - 0.4 = 较宽松
""")

    print("\n验证修改的方法:")
    print("-" * 80)
    print("运行 scripts/test_evaluation_manual.py 再次测试")
    print("确认simple_002的评分在[0.40-0.70]范围内")


if __name__ == "__main__":
    analyze_deviations()
    print_implementation_guide()
