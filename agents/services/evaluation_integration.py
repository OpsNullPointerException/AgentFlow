"""
Agent评测集成 - 简化版

直接使用以下方式进行评测，无需通过此模块：

【方式1】执行级评测（自动运行）
----------
Agent执行完成后，系统自动调用 RuleBasedEvaluator：

  from agents.services.agent_service import AgentService

  result = agent_service.execute_agent(agent_id, user_input, user_id)
  # execution.evaluation_score 自动保存

【方式2】详细评测（手动/批量）
----------
用 test_case 对执行进行详细评测：

  from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

  evaluator = RuleBasedEvaluator()
  result = evaluator.evaluate(execution, test_case)

  print(result['score'])
  print(result['details'])
  print(result['confidence'])

【方式3】数据集批量评测
----------
CLI 批量评测：

  python scripts/evaluate_agent.py \\
    --agent-id my-agent \\
    --dataset simple \\
    --output report.json

=== 架构说明 ===

评测系统已统一为单一设计：

  - RuleBasedEvaluator: 轻量级评测（4维）
    ├─ 关键词覆盖率 (30%)
    ├─ 长度合理性 (25%)
    ├─ 安全用词 (20%)
    └─ 工具使用 (25%)

    每维返回:
    {
        "score": 0.0-1.0,
        "justification": "原因",
        "confidence": 0.0-1.0,
        "evidence": {...}  # 维度相关
    }

  - AgentEvaluator: 详细评测（5维+性能）
    用于需要详细分析的场景

此模块保留是为了向后兼容，
推荐直接使用 RuleBasedEvaluator。
"""

# 已弃用的方式（使用上面的方式代替）：
# from agents.services.evaluation_integration import EvaluationIntegration
# ei = EvaluationIntegration()
# ei.evaluate_agent_execution(execution, test_case)
