"""
简单测试用例集合
包含document_search、sql_query和analysis三种任务类型
"""

# 测试用例列表
TEST_CASES = [
    # ==================== Document Search Cases ====================
    {
        "id": "doc_search_1",
        "task_type": "document_search",
        "user_input": "什么是机器学习？",
        "expected": {
            "expected_min_length": 50,
            "expected_max_length": 5000,
            "expected_keywords": ["机器学习", "学习"],
            "expected_time": 5.0
        }
    },
    {
        "id": "doc_search_2",
        "task_type": "document_search",
        "user_input": "如何使用API？",
        "expected": {
            "expected_min_length": 30,
            "expected_max_length": 3000,
            "expected_keywords": ["API", "使用"],
            "expected_time": 4.0
        }
    },
    {
        "id": "doc_search_3",
        "task_type": "document_search",
        "user_input": "数据库优化技巧",
        "expected": {
            "expected_min_length": 50,
            "expected_max_length": 4000,
            "expected_keywords": ["数据库", "优化"],
            "expected_time": 4.5
        }
    },

    # ==================== SQL Query Cases ====================
    {
        "id": "sql_query_1",
        "task_type": "sql_query",
        "user_input": "查询昨天销售额最高的产品",
        "expected": {
            "expected_min_rows": 1,
            "expected_max_rows": 10,
            "expected_columns": ["product", "sales"],
            "expected_output": "产品A\t5000",  # 可选reference
            "expected_time": 2.0
        }
    },
    {
        "id": "sql_query_2",
        "task_type": "sql_query",
        "user_input": "统计各部门的员工数",
        "expected": {
            "expected_min_rows": 1,
            "expected_max_rows": 50,
            "expected_columns": ["department", "count"],
            "expected_time": 1.5
        }
    },
    {
        "id": "sql_query_3",
        "task_type": "sql_query",
        "user_input": "查询本月订单总额",
        "expected": {
            "expected_min_rows": 1,
            "expected_max_rows": 5,
            "expected_columns": ["month", "total_amount"],
            "expected_time": 1.8
        }
    },
    {
        "id": "sql_query_4",
        "task_type": "sql_query",
        "user_input": "列出前10个高价值客户",
        "expected": {
            "expected_min_rows": 1,
            "expected_max_rows": 10,
            "expected_columns": ["customer_id", "customer_name", "total_spending"],
            "expected_time": 2.5
        }
    },

    # ==================== Analysis Cases ====================
    {
        "id": "analysis_1",
        "task_type": "analysis",
        "user_input": "统计各产品的销售数据",
        "expected": {
            "expected_metrics": ["产品", "销售"],
            "expected_values": ["5000", "3000"],  # 可选reference
            "expected_format": "table",
            "allow_approximation": True
        }
    },
    {
        "id": "analysis_2",
        "task_type": "analysis",
        "user_input": "计算销售占比",
        "expected": {
            "expected_metrics": ["占比", "%"],
            "expected_format": "summary",
            "allow_approximation": True
        }
    },
    {
        "id": "analysis_3",
        "task_type": "analysis",
        "user_input": "分析客户购买趋势",
        "expected": {
            "expected_metrics": ["时间", "购买量", "趋势"],
            "expected_format": "chart",
            "allow_approximation": True
        }
    },
    {
        "id": "analysis_4",
        "task_type": "analysis",
        "user_input": "比较不同地区的销售表现",
        "expected": {
            "expected_metrics": ["地区", "销售额", "增长率"],
            "expected_format": "table",
            "allow_approximation": True
        }
    },
]


def get_test_cases_by_type(task_type: str):
    """
    按任务类型获取测试用例

    Args:
        task_type: 任务类型（document_search, sql_query, analysis）

    Returns:
        该类型的所有测试用例列表
    """
    return [case for case in TEST_CASES if case.get("task_type") == task_type]


def get_test_case_by_id(case_id: str):
    """
    按ID获取测试用例

    Args:
        case_id: 测试用例ID

    Returns:
        对应的测试用例字典，如果不存在则返回None
    """
    for case in TEST_CASES:
        if case.get("id") == case_id:
            return case
    return None


if __name__ == "__main__":
    # 打印所有测试用例信息
    print(f"Total test cases: {len(TEST_CASES)}")
    print("\nTest cases by type:")

    task_types = set(case.get("task_type") for case in TEST_CASES)
    for task_type in sorted(task_types):
        cases = get_test_cases_by_type(task_type)
        print(f"  {task_type}: {len(cases)} cases")
        for case in cases:
            print(f"    - {case['id']}: {case['user_input'][:50]}")
