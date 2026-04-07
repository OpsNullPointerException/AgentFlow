#!/usr/bin/env python3
"""测试改进的表选择器"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartdocs_project.settings')

import django
django.setup()

from agents.langgraph.nodes import get_table_selector

def test_table_selector():
    """测试向量相似度表选择"""

    selector = get_table_selector()

    # 测试用例
    test_cases = [
        {
            "user_input": "上周新能源车的平均能耗是多少",
            "clarified_terms": [
                {"term": "新能源车", "meaning": "fuel_type IN ('electric', 'hybrid')"},
                {"term": "能耗", "meaning": "单位里程能耗，kWh/100km"},
            ],
            "expected": ["vehicle_workload"],  # 应该选中工况表
        },
        {
            "user_input": "座椅日活率怎么样",
            "clarified_terms": [
                {"term": "座椅日活率", "meaning": "有座椅传感器数据的车辆数/总车辆数"},
            ],
            "expected": ["sensor_data"],  # 应该选中传感器表
        },
        {
            "user_input": "故障率最高的三款车型",
            "clarified_terms": [
                {"term": "故障率", "meaning": "故障次数/工作次数"},
            ],
            "expected": ["vehicle_fault"],  # 应该选中故障表
        },
        {
            "user_input": "能耗和座椅日活率对比",
            "clarified_terms": [
                {"term": "能耗", "meaning": "单位里程能耗"},
                {"term": "座椅日活率", "meaning": "座椅传感器激活率"},
            ],
            "expected": ["vehicle_workload", "sensor_data"],  # 应该选中两个表
        },
    ]

    print("\n" + "="*80)
    print("🧪 测试表选择器（向量相似度方法）")
    print("="*80 + "\n")

    for i, test_case in enumerate(test_cases, 1):
        user_input = test_case["user_input"]
        clarified_terms = test_case["clarified_terms"]
        expected = test_case["expected"]

        print(f"测试用例 {i}:")
        print(f"  📝 用户输入: {user_input}")
        print(f"  📚 澄清术语: {[t['term'] for t in clarified_terms]}")

        # 调用表选择器
        selected = selector.select_tables(user_input, clarified_terms)

        print(f"  ✅ 选中的表: {selected}")
        print(f"  📊 期望的表: {expected}")

        # 验证结果
        if set(selected) & set(expected):  # 如果有交集
            print(f"  ✓ 通过 ✓")
        else:
            print(f"  ✗ 失败 ✗")

        print()

    print("="*80)
    print("📊 缓存测试：同样的查询应该立即返回（缓存命中）")
    print("="*80 + "\n")

    # 测试缓存
    import time

    test_input = "能耗是多少"
    test_terms = [{"term": "能耗", "meaning": "单位里程能耗"}]

    # 第一次查询（没有缓存）
    start = time.time()
    result1 = selector.select_tables(test_input, test_terms)
    time1 = (time.time() - start) * 1000

    print(f"第一次查询:")
    print(f"  ⏱️  耗时: {time1:.2f}ms")
    print(f"  📊 结果: {result1}")

    # 第二次查询（有缓存）
    start = time.time()
    result2 = selector.select_tables(test_input, test_terms)
    time2 = (time.time() - start) * 1000

    print(f"\n第二次查询（缓存）:")
    print(f"  ⏱️  耗时: {time2:.2f}ms")
    print(f"  📊 结果: {result2}")

    speedup = time1 / time2 if time2 > 0 else float('inf')
    print(f"\n  🚀 加速倍数: {speedup:.0f}x")

    print("\n" + "="*80)
    print("✅ 所有测试完成！")
    print("="*80 + "\n")

if __name__ == "__main__":
    test_table_selector()
