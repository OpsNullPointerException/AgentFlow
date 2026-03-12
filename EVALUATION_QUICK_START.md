# AgentFlow 评测系统 - 快速参考

## 📌 系统目标
快速验证Agent的执行效果和性能，支持开发阶段的持续改进。

## 🎯 评测维度

### 执行效果 (权重 85%)
| 维度 | 权重 | 标准 |
|------|------|------|
| 准确性 | 30% | 答案是否正确 |
| 完成度 | 20% | 是否完成任务 |
| 可理解性 | 20% | 逻辑清晰度 |
| 工具适当性 | 15% | 工具选择合理性 |
| 安全性 | 15% | SQL/API安全性 |

### 性能指标 (权重 15%)
- 响应时间: 目标 ≤5秒
- Token效率: 目标 ≤1000 tokens
- 工具调用: 目标 ≤3次
- 成功率: 目标 ≥95%

## 📊 通过标准
**总分 ≥ 75% = 通过** ✅

## 🚀 快速使用

### 简单评测（开发中）
```bash
python scripts/evaluate_agent.py \
    --agent-id=my-agent \
    --dataset=simple \
    --output=report.json
```

### 中等难度
```bash
python scripts/evaluate_agent.py \
    --agent-id=my-agent \
    --dataset=medium
```

### 全量验证（发布前）
```bash
python scripts/evaluate_agent.py \
    --agent-id=my-agent \
    --dataset=all
```

### Django管理命令
```bash
python manage.py evaluate_agent my-agent --dataset=simple
```

## 📋 测试集构成

- **Simple**: 5个基础用例
- **Medium**: 5个中等难度
- **Complex**: 3个复杂任务
- **Edge Cases**: 5个已知难案例
- **Total**: 18个测试用例

## 📈 报告示例
```
✅ 评测完成
📊 总体评分: 82/100 ✓ 通过

维度评分:
  准确性:     85/100 ✓
  完成度:     80/100 ✓
  可理解性:   88/100 ✓
  工具适当性:  78/100 ⚠
  安全性:     95/100 ✓

性能指标:
  响应时间:   3.2秒 ✓
  Token效率:  850 tokens ✓
  工具调用:   2次 ✓
  成功率:     100% ✓

改进建议:
- 工具选择逻辑需优化
- 某些复杂query完成度低
```

## 🏗️ 文件结构
```
agents/evaluation/
├── evaluator.py       # 核心评测引擎
├── rubrics.py         # 评测标准
├── judge.py           # LLM-as-Judge
└── metrics.py         # 性能指标

agents/test_datasets/
├── fixtures.py        # 基础数据
├── scenarios.py       # 场景测试
└── edge_cases.py      # 难案例

scripts/
└── evaluate_agent.py  # CLI工具
```

## ⚡ 性能指标对标

| 指标 | 优秀 | 良好 | 需改进 |
|------|------|------|--------|
| 准确性 | ≥90% | 70-90% | <70% |
| 响应时间 | ≤3秒 | 3-5秒 | >5秒 |
| Token使用 | ≤800 | 800-1200 | >1200 |
| 成功率 | ≥98% | 95-98% | <95% |

## 💡 最佳实践

✅ **应该做**
- 每周运行一次完整评测
- 记录历史评测数据
- 对比Agent版本间的改进
- 根据评分改进system prompt

❌ **不应该做**
- 过度依赖单个评分指标
- 忽视用户实际反馈
- 不考虑评测数据的合理性
- 频繁改变评测标准

## 📞 常见问题

**Q: 评测要多长时间？**
A: 简单集 1-2分钟，中等集 3-5分钟，全量 5-10分钟

**Q: 评分为什么波动？**
A: LLM有随机性。建议多运行几次取平均，或降低temperature

**Q: 如何添加新的测试用例？**
A: 编辑 `agents/test_datasets/fixtures.py`，添加到对应的CASES列表

**Q: 性能很差怎么办？**
A: 检查工具调用次数、看执行步骤、调整system prompt

## 📚 详细文档
- 设计文档: `docs/plans/2025-03-12-evaluation-system-design.md`
- 架构评审: `docs/plans/2025-03-12-architecture-review.md`
- 实施路线: `docs/plans/2025-03-12-implementation-roadmap.md`

---
**最后更新**: 2025-03-12
**版本**: 1.0
