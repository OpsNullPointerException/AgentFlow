#!/usr/bin/env python
"""
优化后的缓存测试 - 验证轻量级缓存策略的效果
专注于嵌入向量和检索结果缓存，避免复杂的LLM推理缓存
"""

import os
import sys
import time
import json
from datetime import datetime

# 设置Django环境
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartdocs_project.settings')

import django
django.setup()

from django.core.cache import cache
from loguru import logger
from documents.services.embedding_service import EmbeddingService
from qa.services.qa_service import QAService


def test_embedding_cache():
    """测试嵌入向量缓存效果"""
    logger.info("=== 测试嵌入向量缓存 ===")
    
    embedding_service = EmbeddingService()
    test_queries = [
        "人工智能的定义是什么？",
        "机器学习有哪些应用？",
        "深度学习的优势是什么？"
    ]
    
    # 第一轮：填充缓存
    logger.info("第一轮：填充嵌入向量缓存...")
    first_round_times = []
    
    for query in test_queries:
        start_time = time.time()
        embedding = embedding_service.get_embedding(query)
        end_time = time.time()
        
        query_time = end_time - start_time
        first_round_times.append(query_time)
        logger.info(f"查询: {query[:30]}... 时间: {query_time:.3f}秒")
    
    # 等待缓存稳定
    time.sleep(1)
    
    # 第二轮：测试缓存命中
    logger.info("第二轮：测试嵌入向量缓存命中...")
    second_round_times = []
    
    for query in test_queries:
        start_time = time.time()
        embedding = embedding_service.get_embedding(query)
        end_time = time.time()
        
        query_time = end_time - start_time
        second_round_times.append(query_time)
        logger.info(f"查询: {query[:30]}... 时间: {query_time:.3f}秒")
    
    # 分析结果
    avg_first = sum(first_round_times) / len(first_round_times)
    avg_second = sum(second_round_times) / len(second_round_times)
    improvement = (avg_first - avg_second) / avg_first * 100
    
    logger.info(f"第一轮平均时间: {avg_first:.3f}秒")
    logger.info(f"第二轮平均时间: {avg_second:.3f}秒") 
    logger.info(f"时间改进: {improvement:.1f}%")
    
    return {
        "first_round_avg": avg_first,
        "second_round_avg": avg_second,
        "improvement_percent": improvement,
        "cache_hit_successful": improvement > 50  # 嵌入缓存应该有显著改进
    }


def test_qa_retrieval_cache():
    """测试QA检索缓存效果"""
    logger.info("=== 测试QA检索缓存 ===")
    
    qa_service = QAService()
    test_queries = [
        "人工智能的定义是什么？",
        "机器学习有哪些应用？",
        "深度学习的优势是什么？"
    ]
    
    # 第一轮：填充缓存
    logger.info("第一轮：填充检索缓存...")
    first_round_times = []
    
    for query in test_queries:
        start_time = time.time()
        response = qa_service.process_query(
            conversation_id=999,  # 测试对话ID
            query=query,
            user_id=1
        )
        end_time = time.time()
        
        query_time = end_time - start_time
        first_round_times.append(query_time)
        logger.info(f"查询: {query[:30]}... 时间: {query_time:.3f}秒")
    
    # 等待缓存稳定
    time.sleep(2)
    
    # 第二轮：测试缓存命中
    logger.info("第二轮：测试检索缓存命中...")
    second_round_times = []
    
    for query in test_queries:
        start_time = time.time()
        response = qa_service.process_query(
            conversation_id=999,  # 相同的测试对话ID
            query=query,
            user_id=1
        )
        end_time = time.time()
        
        query_time = end_time - start_time
        second_round_times.append(query_time)
        logger.info(f"查询: {query[:30]}... 时间: {query_time:.3f}秒")
    
    # 分析结果
    avg_first = sum(first_round_times) / len(first_round_times)
    avg_second = sum(second_round_times) / len(second_round_times)
    improvement = (avg_first - avg_second) / avg_first * 100
    
    logger.info(f"第一轮平均时间: {avg_first:.3f}秒")
    logger.info(f"第二轮平均时间: {avg_second:.3f}秒")
    logger.info(f"时间改进: {improvement:.1f}%")
    
    return {
        "first_round_avg": avg_first,
        "second_round_avg": avg_second,
        "improvement_percent": improvement,
        "cache_hit_successful": improvement > 10  # 检索缓存应该有一定改进
    }


def test_cache_stats():
    """测试缓存统计功能"""
    logger.info("=== 测试缓存统计 ===")
    
    # 测试嵌入服务缓存统计
    embedding_service = EmbeddingService()
    embedding_stats = embedding_service.get_cache_stats()
    logger.info(f"嵌入服务缓存统计: {embedding_stats}")
    
    # 测试QA服务缓存统计
    qa_service = QAService()
    qa_stats = qa_service.get_cache_stats()
    logger.info(f"QA服务缓存统计: {qa_stats}")
    
    return {
        "embedding_stats": embedding_stats,
        "qa_stats": qa_stats
    }


def main():
    """主测试函数"""
    logger.info("开始优化后的缓存测试")
    start_time = time.time()
    
    # 清空缓存，确保干净的测试环境
    cache.clear()
    logger.info("已清空缓存")
    
    results = {}
    
    try:
        # 1. 测试嵌入向量缓存
        results["embedding_cache"] = test_embedding_cache()
        
        # 2. 测试QA检索缓存
        results["qa_retrieval_cache"] = test_qa_retrieval_cache()
        
        # 3. 测试缓存统计
        results["cache_stats"] = test_cache_stats()
        
        # 4. 整体评估
        end_time = time.time()
        total_time = end_time - start_time
        
        results["test_summary"] = {
            "total_test_time": total_time,
            "embedding_cache_works": results["embedding_cache"]["cache_hit_successful"],
            "qa_cache_works": results["qa_retrieval_cache"]["cache_hit_successful"],
            "overall_success": (
                results["embedding_cache"]["cache_hit_successful"] and 
                results["qa_retrieval_cache"]["cache_hit_successful"]
            )
        }
        
        # 保存测试结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"validation_datasets/optimized_cache_test_{timestamp}.json"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        logger.info(f"测试报告已保存: {report_path}")
        
        # 输出总结
        logger.info("=== 优化后缓存测试总结 ===")
        logger.info(f"总测试时间: {total_time:.1f}秒")
        logger.info(f"嵌入缓存效果: {'✅ 成功' if results['embedding_cache']['cache_hit_successful'] else '❌ 失败'}")
        logger.info(f"检索缓存效果: {'✅ 成功' if results['qa_retrieval_cache']['cache_hit_successful'] else '❌ 失败'}")
        logger.info(f"整体评估: {'✅ 优化成功' if results['test_summary']['overall_success'] else '❌ 需要进一步优化'}")
        
        # 性能对比
        embedding_improvement = results["embedding_cache"]["improvement_percent"]
        qa_improvement = results["qa_retrieval_cache"]["improvement_percent"]
        
        logger.info("=== 性能改进对比 ===")
        logger.info(f"嵌入向量缓存改进: {embedding_improvement:.1f}%")
        logger.info(f"QA检索缓存改进: {qa_improvement:.1f}%")
        
        if embedding_improvement > 50:
            logger.info("🚀 嵌入缓存效果优秀！")
        elif embedding_improvement > 20:
            logger.info("✅ 嵌入缓存效果良好")
        else:
            logger.info("⚠️ 嵌入缓存效果一般")
            
        if qa_improvement > 30:
            logger.info("🚀 检索缓存效果优秀！")
        elif qa_improvement > 10:
            logger.info("✅ 检索缓存效果良好")
        else:
            logger.info("⚠️ 检索缓存效果一般")
        
    except Exception as e:
        logger.exception(f"测试过程中出现错误: {e}")
        return False
    
    return results["test_summary"]["overall_success"]


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)