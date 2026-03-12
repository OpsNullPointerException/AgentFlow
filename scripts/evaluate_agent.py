#!/usr/bin/env python3
"""
AgentFlow 评测系统命令行工具

用法:
    python scripts/evaluate_agent.py --agent-id my-agent-001 --dataset simple
    python scripts/evaluate_agent.py --agent-id my-agent-001 --dataset all --output report.json
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.evaluation import AgentEvaluator
from agents.test_datasets import get_test_cases, get_statistics


def print_header(text: str):
    """打印标题"""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def print_evaluation_report(report: dict):
    """打印评测报告"""
    print("✅ 评测完成\n")

    # 总体评分
    overall_score = report.get("overall_score", 0)
    status = "✓ 通过" if report.get("passed") else "✗ " + report.get("status", "失败")
    print(f"📊 总体评分: {overall_score:.0%}  {status}\n")

    # 维度评分
    if "execution_scores" in report:
        print("维度评分:")
        execution_scores = report["execution_scores"]
        dimension_names = {
            "accuracy": "准确性",
            "completeness": "完成度",
            "clarity": "可理解性",
            "tool_appropriateness": "工具适当性",
            "safety": "安全性",
        }
        for dim, score in execution_scores.items():
            name = dimension_names.get(dim, dim)
            status_icon = "✓" if score >= 0.75 else "⚠" if score >= 0.5 else "✗"
            print(f"  {status_icon} {name:12s}: {score:6.0%}")
        print()

    # 性能指标
    if "performance_scores" in report:
        print("性能指标:")
        perf = report["performance_scores"]
        print(f"  响应时间:   {perf.get('response_time', 0):.1f}秒")
        print(f"  Token效率:  {perf.get('token_usage', 0)}")
        print(f"  工具调用:   {perf.get('tool_calls', 0)}次")
        print(f"  成功率:     {perf.get('success_rate', 0):.0%}")
        print()

    # 改进建议
    if "recommendations" in report and report["recommendations"]:
        print("改进建议:")
        for i, rec in enumerate(report["recommendations"], 1):
            print(f"  {i}. {rec}")
        print()


def format_report_table(reports: list) -> str:
    """生成汇总表格"""
    from statistics import mean

    if not reports:
        return "没有评测结果\n"

    # 收集数据
    scores = [r.get("overall_score", 0) for r in reports]
    statuses = [r.get("status", "未知") for r in reports]

    output = "\n📈 评测汇总:\n"
    output += f"  总用例数:  {len(reports)}\n"
    output += f"  平均评分:  {mean(scores):.0%}\n"
    output += f"  最高评分:  {max(scores):.0%}\n"
    output += f"  最低评分:  {min(scores):.0%}\n"

    # 按状态分类
    status_count = {}
    for status in statuses:
        status_count[status] = status_count.get(status, 0) + 1

    output += f"  状态分布:\n"
    for status, count in status_count.items():
        output += f"    - {status}: {count}例\n"

    return output


def main():
    parser = argparse.ArgumentParser(
        description="AgentFlow 评测系统 - 快速验证Agent性能",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 快速评测（简单用例）
  %(prog)s --agent-id my-agent --dataset simple

  # 中等难度评测
  %(prog)s --agent-id my-agent --dataset medium

  # 全量评测
  %(prog)s --agent-id my-agent --dataset all --output report.json
        """,
    )

    parser.add_argument(
        "--agent-id",
        required=True,
        help="Agent ID（必需）",
    )
    parser.add_argument(
        "--dataset",
        choices=["simple", "medium", "complex", "edge", "all"],
        default="simple",
        help="测试数据集复杂度（默认：simple）",
    )
    parser.add_argument(
        "--scenario",
        choices=["document_qa", "data_analysis", "research"],
        help="测试场景（可选，不指定则包含所有场景）",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="输出报告文件路径（JSON格式，可选）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细输出模式",
    )

    args = parser.parse_args()

    print_header(f"🚀 AgentFlow 评测系统")
    print(f"Agent ID: {args.agent_id}")
    print(f"数据集:   {args.dataset}")
    if args.scenario:
        print(f"场景:     {args.scenario}")
    print()

    # 获取测试用例
    test_cases = get_test_cases(complexity=args.dataset, scenario=args.scenario)
    print(f"📋 已加载 {len(test_cases)} 个测试用例")
    print(f"   - 从{args.dataset}级数据集")
    if args.scenario:
        print(f"   - 场景: {args.scenario}")
    print()

    # 创建评测器
    evaluator = AgentEvaluator()

    # 执行评测（模拟，实际应该执行真实Agent）
    print("⏳ 正在评测...")
    reports = []

    for i, test_case in enumerate(test_cases, 1):
        # 这里应该真实执行Agent，现在用模拟数据
        from dataclasses import dataclass

        @dataclass
        class MockExecution:
            id: str
            agent_id: str
            user_input: str
            agent_output: str
            execution_steps: list
            tools_used: list
            status: str
            execution_time: float
            token_usage: dict

        mock_exec = MockExecution(
            id=test_case.get("id", f"exec-{i}"),
            agent_id=args.agent_id,
            user_input=test_case.get("input", ""),
            agent_output=f"回答关于: {test_case.get('input', '')}的问题" * 5,
            execution_steps=[{"step_type": "action", "step_name": "search"}],
            tools_used=["document_search"],
            status="completed",
            execution_time=2.0 + i * 0.1,
            token_usage={"prompt_tokens": 100 + i * 10, "completion_tokens": 50},
        )

        report = evaluator.evaluate_execution(mock_exec)
        reports.append(report.to_dict())

        # 显示进度
        status_icon = "✓" if report.passed else "✗"
        print(f"  [{i:2d}/{len(test_cases)}] {status_icon} {test_case.get('name', 'Unknown'):20s} {report.overall_score:.0%}")

    print()

    # 显示汇总
    print(format_report_table(reports))

    # 显示代表性报告
    if reports:
        print("\n📊 代表性评测报告（第一个用例）:")
        print_evaluation_report(reports[0])

    # 保存报告
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report_data = {
            "timestamp": datetime.now().isoformat(),
            "agent_id": args.agent_id,
            "dataset": args.dataset,
            "scenario": args.scenario,
            "total_cases": len(reports),
            "reports": reports,
            "summary": {
                "avg_score": sum(r["overall_score"] for r in reports) / len(reports)
                if reports
                else 0,
                "passed": sum(1 for r in reports if r["passed"]),
                "failed": sum(1 for r in reports if not r["passed"]),
            },
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        print(f"\n✅ 报告已保存到: {output_path}")

    print()
    print("✨ 评测完成！\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  评测已中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 错误: {e}")
        if "--verbose" in sys.argv:
            import traceback
            traceback.print_exc()
        sys.exit(1)
