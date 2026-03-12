"""
场景化测试集

提供针对不同应用场景的测试用例组合
"""

# 文档问答场景测试
DOCUMENT_QA_SCENARIOS = {
    "basic_qa": [
        {
            "name": "基础概念问题",
            "queries": [
                "什么是REST API？",
                "解释一下异步编程",
                "微服务架构有什么优点？",
            ],
            "expected_characteristics": [
                "contain_definition",
                "clear_structure",
                "relevant_examples",
            ],
        },
        {
            "name": "技术细节问题",
            "queries": [
                "Django中间件的执行顺序是什么？",
                "Python GIL对多线程有什么影响？",
                "数据库索引如何提升查询性能？",
            ],
            "expected_characteristics": [
                "technical_accuracy",
                "detailed_explanation",
                "include_implementation_details",
            ],
        },
    ],
    "comparison_qa": [
        {
            "name": "技术对比",
            "queries": [
                "对比MySQL和MongoDB的优缺点",
                "比较Python和Go语言的特点",
                "REST和GraphQL有什么区别",
            ],
            "expected_characteristics": [
                "balanced_comparison",
                "multiple_dimensions",
                "use_cases_examples",
            ],
        },
    ],
}

# 数据分析场景测试
DATA_ANALYSIS_SCENARIOS = {
    "simple_analytics": [
        {
            "name": "单表查询",
            "queries": [
                "查询今天的销售总额",
                "统计活跃用户数量",
                "列出所有未完成的订单",
            ],
            "expected_characteristics": [
                "single_table_query",
                "correct_aggregation",
                "proper_filtering",
            ],
        },
    ],
    "complex_analytics": [
        {
            "name": "多表联合分析",
            "queries": [
                "分析客户的购买频率和平均消费额的关系",
                "对比各地区的销售增长率和产品偏好",
                "统计员工绩效与部门预算的关联",
            ],
            "expected_characteristics": [
                "complex_joins",
                "multiple_aggregations",
                "advanced_filtering",
            ],
        },
    ],
    "forecasting": [
        {
            "name": "预测分析",
            "queries": [
                "基于历史趋势预测下个季度的销售",
                "评估客户流失风险",
                "预测库存需求",
            ],
            "expected_characteristics": [
                "historical_data_analysis",
                "trend_identification",
                "prediction_reasoning",
            ],
        },
    ],
}

# 研究合成场景测试
RESEARCH_SCENARIOS = {
    "literature_synthesis": [
        {
            "name": "文献综合",
            "queries": [
                "总结最新的深度学习研究方向",
                "综合各种云计算的架构设计",
                "对比不同的数据挖掘算法",
            ],
            "expected_characteristics": [
                "multiple_sources",
                "synthesis_not_copy",
                "critical_analysis",
            ],
        },
    ],
    "trend_analysis": [
        {
            "name": "趋势分析",
            "queries": [
                "分析AI技术的发展趋势",
                "评估开源项目的受欢迎程度变化",
                "预测编程语言的发展方向",
            ],
            "expected_characteristics": [
                "temporal_analysis",
                "pattern_recognition",
                "future_outlook",
            ],
        },
    ],
}

# 综合所有场景
ALL_SCENARIOS = {
    "document_qa": DOCUMENT_QA_SCENARIOS,
    "data_analysis": DATA_ANALYSIS_SCENARIOS,
    "research": RESEARCH_SCENARIOS,
}
