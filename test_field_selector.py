#!/usr/bin/env python3
"""测试改进的字段选择器"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartdocs_project.settings')

import django
django.setup()

from agents.langgraph.nodes import get_field_selector, FIELD_METADATA

def test_field_selector():
    """测试向量相似度字段选择"""

    selector = get_field_selector()

    # 测试用例
    test_cases = [
        {
            "table": "vehicle_workload",
            "user_input": "上周新能源车的平均能耗是多少",
            "clarified_terms": [
                {"term": "新能源车", "meaning": "fuel_type IN ('electric', 'hybrid')"},
                {"term": "能耗", "meaning": "单位里程能耗，kWh/100km"},
            ],
            "expected_fields": ["date", "power_consumption"],  # 应该选中日期和能耗
        },
        {
            "table": "sensor_data",
            "user_input": "座椅日活率怎么样",
            "clarified_terms": [
                {"term": "座椅日活率", "meaning": "有座椅传感器数据的车辆数/总车辆数"},
            ],
            "expected_fields": ["seat_sensor_active"],  # 应该选中座椅传感器
        },
        {
            "table": "vehicle_fault",
            "user_input": "故障率最高的三款车型",
            "clarified_terms": [
                {"term": "故障率", "meaning": "故障次数/工作次数"},
            ],
            "expected_fields": ["fault_count"],  # 应该选中故障计数字段（直接相关）
        },
        {
            "table": "vehicle_info",
            "user_input": "电动车和混动车的品牌分布",
            "clarified_terms": [
                {"term": "电动车", "meaning": "fuel_type = 'electric'"},
                {"term": "混动车", "meaning": "fuel_type = 'hybrid'"},
            ],
            "expected_fields": ["fuel_type", "vehicle_name"],  # 应该选中能源类型和车型名称
        },
        {
            "table": "vehicle_workload",
            "user_input": "车辆行驶的最高速度和平均速度对比",
            "clarified_terms": [
                {"term": "最高速度", "meaning": "max_speed"},
                {"term": "平均速度", "meaning": "avg_speed"},
            ],
            "expected_fields": ["max_speed", "avg_speed"],  # 应该选中两个速度字段
        },
    ]

    print("\n" + "="*80)
    print("🧪 测试字段选择器（向量相似度方法）")
    print("="*80 + "\n")

    passed = 0
    total = len(test_cases)

    for i, test_case in enumerate(test_cases, 1):
        table = test_case["table"]
        user_input = test_case["user_input"]
        clarified_terms = test_case["clarified_terms"]
        expected_fields = test_case["expected_fields"]

        print(f"测试用例 {i}:")
        print(f"  📊 表: {table}")
        print(f"  📝 用户输入: {user_input}")
        print(f"  📚 澄清术语: {[t['term'] for t in clarified_terms]}")

        # 调用字段选择器
        selected = selector.select_fields(table, user_input, clarified_terms, top_k=3)

        print(f"  ✅ 选中的字段: {selected}")
        print(f"  📊 期望的字段: {expected_fields}")

        # 验证结果 - 检查是否有交集
        matches = set(selected) & set(expected_fields)
        if matches:
            print(f"  ✓ 通过 ✓ (匹配: {matches})")
            passed += 1
        else:
            print(f"  ✗ 失败 ✗")

        print()

    print("="*80)
    print(f"📊 测试结果: {passed}/{total} 通过")
    print("="*80 + "\n")

    # 性能测试：缓存
    print("="*80)
    print("📊 缓存性能测试：同样的查询应该立即返回（缓存命中）")
    print("="*80 + "\n")

    import time

    test_table = "vehicle_workload"
    test_input = "平均能耗是多少"
    test_terms = [{"term": "能耗", "meaning": "单位里程能耗"}]

    # 第一次查询（没有缓存）
    start = time.time()
    result1 = selector.select_fields(test_table, test_input, test_terms)
    time1 = (time.time() - start) * 1000

    print(f"第一次查询:")
    print(f"  ⏱️  耗时: {time1:.2f}ms")
    print(f"  📊 结果: {result1}")

    # 第二次查询（有缓存）
    start = time.time()
    result2 = selector.select_fields(test_table, test_input, test_terms)
    time2 = (time.time() - start) * 1000

    print(f"\n第二次查询（缓存）:")
    print(f"  ⏱️  耗时: {time2:.2f}ms")
    print(f"  📊 结果: {result2}")

    speedup = time1 / time2 if time2 > 0 else float('inf')
    print(f"\n  🚀 加速倍数: {speedup:.0f}x")

    # 字段采样对比
    print("\n" + "="*80)
    print("📊 字段采样效率对比")
    print("="*80 + "\n")

    total_fields_by_table = {}
    for table, fields in FIELD_METADATA.items():
        total_fields_by_table[table] = len(fields)

    print("改进前（采样所有字段）：")
    for table, count in total_fields_by_table.items():
        print(f"  {table}: {count} 个字段")
    total_before = sum(total_fields_by_table.values())
    print(f"  📊 总计: {total_before} 个字段采样")

    print("\n改进后（智能选择 top-3）：")
    for table in FIELD_METADATA.keys():
        selected = selector.select_fields(table, "查询", [], top_k=3)
        print(f"  {table}: {len(selected)} 个字段 -> {selected}")
    total_after = 3 * len(FIELD_METADATA)
    print(f"  📊 总计: {total_after} 个字段采样")

    reduction_ratio = 1 - (total_after / total_before)
    print(f"\n  📉 采样减少: {reduction_ratio*100:.1f}%")

    print("\n" + "="*80)
    print("✅ 所有测试完成！")
    print("="*80 + "\n")

if __name__ == "__main__":
    test_field_selector()
