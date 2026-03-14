"""
Agent评测集成 - 简化版

直接使用以下方式进行评测，无需通过此模块：

【方式1】执行级评测（自动运行）
----------
Agent执行完成后，系统自动调用 RuleBasedEvaluator：

  from agents.services.agent_service import AgentService

  result = agent_service.execute_agent(agent_id, user_input, user_id)
  # execution.evaluation_score 自动保存
  # execution.evaluation_details 保存详细评测信息
  # execution.evaluation_report 保存评测理由（Chain-of-Thought）

【方式2】详细评测（手动/批量）- 支持多任务类型
----------
用 test_case 对执行进行详细评测。系统自动推断任务类型，但也支持显式指定：

  from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

  evaluator = RuleBasedEvaluator()

  # 文档搜索任务（显式指定）
  test_case_doc = {
      "task_type": "document_search",  # 可选：显式指定
      "expected": {
          "keywords": ["销售", "数据"],
          "min_length": 30,
          "max_length": 5000,
      }
  }
  result = evaluator.evaluate(execution, test_case_doc)
  print(result['score'])        # 评分
  print(result['details'])      # 各维度详情
  print(result['reasoning'])    # Chain-of-Thought理由
  print(result['confidence'])   # 置信度
  print(result['detected_task_type'])  # 推断的任务类型

  # SQL查询任务（显式指定）
  test_case_sql = {
      "task_type": "sql_query",  # 显式指定为SQL任务
      "expected": {
          "expected_min_rows": 1,
          "expected_max_rows": 100,
          "expected_columns": ["product", "sales"],
          "expected_output": "产品A\t1000",  # 可选：用于准确性检查
          "expected_time": 3.0
      }
  }
  result = evaluator.evaluate(execution, test_case_sql)
  # 会自动从execution_steps中提取sql_query工具的原始输出进行评测
  # 而不是用最终的agent_output

  # 数据分析任务（显式指定）
  test_case_analysis = {
      "task_type": "analysis",  # 显式指定为分析任务
      "expected": {
          "expected_metrics": ["销售", "占比"],
          "expected_values": ["5000", "50"],  # 可选：用于数值准确性检查
          "expected_format": "table",
          "allow_approximation": True  # 允许±10%误差
      }
  }
  result = evaluator.evaluate(execution, test_case_analysis)

  # 自动推断任务类型（不显式指定）
  test_case_auto = {
      # 没有task_type，系统会根据tools_used或output推断
      "expected": {
          "expected_min_rows": 1,
          "expected_max_rows": 100,
      }
  }
  result = evaluator.evaluate(execution, test_case_auto)
  print(result['detected_task_type'])  # 会显示推断的类型：'sql_query' / 'analysis' / 'document_search'
  print(result['was_explicitly_set'])  # False，表示是自动推断的

【方式3】数据集批量评测
----------
CLI 批量评测（支持多任务类型）：

  python scripts/evaluate_agent.py \\
    --agent-id my-agent \\
    --dataset simple \\
    --output report.json

  # 输出report.json包含详细评测数据

=== 支持的任务类型 ===

1. document_search （默认）
   特点：纯文本搜索和问答任务
   评测维度：
   ├─ keyword_coverage (40%)   关键词覆盖率
   ├─ length_ok (30%)          长度合理性
   ├─ no_bad_words (20%)       禁词检查
   └─ tools_ok (10%)           工具使用恰当性
   通过阈值：0.75

2. sql_query
   特点：数据库查询任务
   核心特性：从execution_steps提取sql_query工具的原始输出进行评测
   评测维度：
   ├─ sql_success (35%)        SQL执行是否成功
   ├─ result_count (25%)       返回行数是否合理
   ├─ result_accuracy (25%)    结果准确性（支持reference对比）
   └─ performance (15%)        执行效率
   通过阈值：0.75

3. analysis
   特点：数据分析和统计任务
   评测维度：
   ├─ metric_presence (35%)    是否包含期望指标
   ├─ numerical_accuracy (35%) 数值准确性（支持reference对比）
   ├─ result_format (20%)      结果格式清晰度
   └─ no_bad_words (10%)       禁词检查
   通过阈值：0.75

=== 架构说明 ===

评测系统采用三层设计：

1. 任务识别层
   - 支持显式指定 task_type
   - 支持自动推断（优先级：显式指定 > tools_used推断 > output推断 > 默认）
   - 返回元信息供用户验证

2. 输出提取层
   - 不同任务类型从不同来源提取output
   - SQL查询：优先从execution_steps中提取sql_query工具的原始输出
   - 分析：优先从sql_query输出，降级到综合output
   - 搜索：优先从document_search工具输出，降级到综合output

3. 评测层
   - RuleBasedEvaluator: Rubric适配评测
     ├─ 根据task_type选择对应Rubric
     ├─ 支持reference-based准确性检查
     ├─ 支持边界情况处理
     └─ 每维返回: score + justification + confidence + evidence
   - 优点：规则完全透明，快速稳定，无LLM调用成本

=== 返回结果格式 ===

evaluate()返回的字典包含：

{
    "score": 0.82,                          # 综合评分（0-1）
    "passed": true,                         # 是否通过阈值
    "confidence": 0.90,                     # 置信度（0-1）
    "detected_task_type": "sql_query",      # 推断的任务类型
    "was_explicitly_set": false,            # 是否显式指定了task_type
    "reasoning": "SQL执行成功✓；返回2行...", # Chain-of-Thought理由
    "details": {
        "sql_success": {
            "score": 1.0,
            "justification": "SQL执行成功✓",
            "confidence": 0.99,
            # 其他维度相关字段
        },
        "result_count": {
            "score": 1.0,
            "justification": "返回2行，在范围[1, 100]内✓",
            "confidence": 0.95,
            "actual_rows": 2
        },
        # ... 其他维度
    }
}

此模块保留是为了向后兼容。
推荐直接使用 RuleBasedEvaluator。
"""

# 已弃用的方式（使用上面的方式代替）：
# from agents.services.evaluation_integration import EvaluationIntegration
# ei = EvaluationIntegration()
# ei.evaluate_agent_execution(execution, test_case)
