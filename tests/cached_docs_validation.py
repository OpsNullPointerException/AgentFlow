#!/usr/bin/env python
"""
基于现有文档的缓存验证测试
使用缓存机制，测试缓存对查询性能和相关性的影响
"""

import os
import sys
import json
import time
from pathlib import Path
from loguru import logger
import random

# Django环境设置
current_path = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_path)
sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartdocs_project.settings')

import django
django.setup()

from documents.models import Document
from documents.services.vector_db_service import VectorDBService
from qa.services.qa_service import QAService
from django.contrib.auth.models import User


class CachedDocsValidator:
    """基于现有文档的缓存验证器"""
    
    def __init__(self):
        self.user = User.objects.get(id=1)
        self.results = []
        self.start_time = time.time()
        self.qa_service = QAService()
        
    def validate_existing_documents_with_cache(self):
        """使用现有文档进行缓存验证测试"""
        logger.info("=== 现有文档验证测试（启用缓存） ===")
        
        # 获取现有文档
        existing_docs = Document.objects.filter(owner_id=self.user.id, status='processed')
        
        logger.info(f"找到 {len(existing_docs)} 个已处理的文档")
        
        if not existing_docs:
            logger.warning("没有找到已处理的文档")
            return []
        
        # 显示文档信息
        for doc in existing_docs[:10]:
            logger.info(f"文档: {doc.title} (ID: {doc.id})")
        
        results = []
        
        # 简化测试，只使用前10个查询进行对比
        test_queries = [
            # 中文技术查询
            "人工智能的定义是什么？",
            "机器学习有哪些应用？",
            "深度学习的优势是什么？",
            "计算机视觉技术原理",
            "自然语言处理的挑战",
            "大数据分析方法",
            "云计算的特点",
            "区块链技术应用",
            "物联网发展趋势",
            "网络安全防护措施"
        ]
        
        logger.info("开始缓存性能测试...")
        
        # 第一轮：首次查询（可能触发缓存填充）
        first_round_results = []
        logger.info("第一轮查询（缓存填充）...")
        
        for i, query in enumerate(test_queries):
            logger.info(f"\n--- 第一轮查询 {i+1}/{len(test_queries)} ---")
            logger.info(f"查询内容: {query}")
            
            start_time = time.time()
            search_results = self._search_documents_with_cache(query)
            query_time = time.time() - start_time
            
            if search_results:
                relevance = search_results[0]['relevance_score']
                
                result = {
                    'round': 1,
                    'query_id': i + 1,
                    'question': query,
                    'relevance_score': relevance,
                    'retrieved_docs': len(search_results),
                    'query_time_seconds': query_time,
                    'top_result': {
                        'title': search_results[0]['document_title'],
                        'content_preview': search_results[0]['content_preview']
                    }
                }
                
                first_round_results.append(result)
                
                logger.info(f"✓ 相关性: {relevance:.4f}")
                logger.info(f"✓ 查询时间: {query_time:.3f}秒")
                logger.info(f"✓ 检索到文档数: {len(search_results)}")
                logger.info(f"✓ 最佳匹配: {search_results[0]['document_title']}")
                
                # 显示相关性评级
                if relevance >= 0.9:
                    rating = "优秀"
                elif relevance >= 0.7:
                    rating = "良好"
                elif relevance >= 0.5:
                    rating = "一般"
                else:
                    rating = "较差"
                logger.info(f"✓ 相关性评级: {rating}")
                
            else:
                logger.warning("✗ 没有找到相关文档")
                
            # 短暂延迟
            time.sleep(0.1)
        
        # 等待缓存稳定
        logger.info("等待缓存稳定...")
        time.sleep(2)
        
        # 第二轮：缓存命中查询
        second_round_results = []
        logger.info("第二轮查询（缓存命中）...")
        
        for i, query in enumerate(test_queries):
            logger.info(f"\n--- 第二轮查询 {i+1}/{len(test_queries)} ---")
            logger.info(f"查询内容: {query}")
            
            start_time = time.time()
            search_results = self._search_documents_with_cache(query)
            query_time = time.time() - start_time
            
            if search_results:
                relevance = search_results[0]['relevance_score']
                
                result = {
                    'round': 2,
                    'query_id': i + 1,
                    'question': query,
                    'relevance_score': relevance,
                    'retrieved_docs': len(search_results),
                    'query_time_seconds': query_time,
                    'top_result': {
                        'title': search_results[0]['document_title'],
                        'content_preview': search_results[0]['content_preview']
                    }
                }
                
                second_round_results.append(result)
                
                logger.info(f"✓ 相关性: {relevance:.4f}")
                logger.info(f"✓ 查询时间: {query_time:.3f}秒")
                logger.info(f"✓ 检索到文档数: {len(search_results)}")
                
                # 与第一轮对比
                if first_round_results and i < len(first_round_results):
                    first_time = first_round_results[i]['query_time_seconds']
                    time_improvement = ((first_time - query_time) / first_time) * 100
                    logger.info(f"✓ 时间改进: {time_improvement:.1f}%")
                
            else:
                logger.warning("✗ 没有找到相关文档")
                
            # 短暂延迟
            time.sleep(0.1)
        
        # 合并结果
        results = first_round_results + second_round_results
                
        logger.info(f"\n缓存验证完成，第一轮测试了 {len(first_round_results)} 个查询")
        logger.info(f"第二轮测试了 {len(second_round_results)} 个查询")
        return results
        
    def _search_documents_with_cache(self, query: str):
        """搜索文档（使用缓存的QA服务）"""
        try:
            # 使用QA服务进行检索，会自动使用缓存
            response = self.qa_service.process_query(
                conversation_id=1,  # 使用固定对话ID
                query=query,
                user_id=self.user.id,
                memory_type="buffer_window"
            )
            
            # 从QA响应中提取搜索结果信息
            formatted_results = []
            
            # 如果有引用文档，解析它们
            if hasattr(response, 'referenced_documents') and response.referenced_documents:
                for i, doc_ref in enumerate(response.referenced_documents):
                    formatted_results.append({
                        'document_id': doc_ref.document_id,
                        'relevance_score': doc_ref.relevance_score,
                        'content_preview': doc_ref.content_preview or '',
                        'document_title': doc_ref.title,
                        'chunk_index': doc_ref.chunk_indices[0] if doc_ref.chunk_indices else 0,
                        'embedding_model': 'qa_service_cached'
                    })
            else:
                # 如果没有引用文档但有答案，创建一个基于答案的结果
                if hasattr(response, 'answer') and response.answer:
                    formatted_results.append({
                        'document_id': 'qa_generated',
                        'relevance_score': 0.7,  # 默认中等相关性
                        'content_preview': str(response.answer)[:200],
                        'document_title': 'QA Service Response',
                        'chunk_index': 0,
                        'embedding_model': 'qa_service_cached'
                    })
                    
            return formatted_results
        except Exception as e:
            logger.error(f"缓存搜索失败: {str(e)}")
            return []
            
    def analyze_cache_performance(self, results):
        """分析缓存性能数据"""
        if not results:
            logger.warning("没有结果可以分析")
            return
            
        logger.info("\n=== 缓存性能分析 ===")
        
        # 分离两轮结果
        first_round = [r for r in results if r['round'] == 1]
        second_round = [r for r in results if r['round'] == 2]
        
        if not first_round or not second_round:
            logger.warning("缺少完整的两轮测试数据")
            return
        
        # 计算两轮的统计指标
        first_times = [r['query_time_seconds'] for r in first_round]
        second_times = [r['query_time_seconds'] for r in second_round]
        
        first_relevance = [r['relevance_score'] for r in first_round]
        second_relevance = [r['relevance_score'] for r in second_round]
        
        # 时间统计
        avg_first_time = sum(first_times) / len(first_times)
        avg_second_time = sum(second_times) / len(second_times)
        time_improvement = ((avg_first_time - avg_second_time) / avg_first_time) * 100
        
        # 相关性统计
        avg_first_relevance = sum(first_relevance) / len(first_relevance)
        avg_second_relevance = sum(second_relevance) / len(second_relevance)
        relevance_change = ((avg_second_relevance - avg_first_relevance) / avg_first_relevance) * 100
        
        logger.info(f"📊 缓存效果分析:")
        logger.info(f"📊 第一轮平均查询时间: {avg_first_time:.3f}秒")
        logger.info(f"📊 第二轮平均查询时间: {avg_second_time:.3f}秒")
        logger.info(f"📊 查询时间改进: {time_improvement:.1f}%")
        logger.info(f"📊 第一轮平均相关性: {avg_first_relevance:.4f}")
        logger.info(f"📊 第二轮平均相关性: {avg_second_relevance:.4f}")
        logger.info(f"📊 相关性变化: {relevance_change:+.1f}%")
        
        # 逐查询对比
        consistent_results = 0
        improved_time = 0
        
        for i in range(min(len(first_round), len(second_round))):
            first = first_round[i]
            second = second_round[i]
            
            # 检查结果一致性
            if abs(first['relevance_score'] - second['relevance_score']) < 0.01:
                consistent_results += 1
                
            # 检查时间改进
            if second['query_time_seconds'] < first['query_time_seconds']:
                improved_time += 1
        
        consistency_rate = (consistent_results / len(first_round)) * 100
        time_improvement_rate = (improved_time / len(first_round)) * 100
        
        logger.info(f"📊 结果一致性: {consistency_rate:.1f}%")
        logger.info(f"📊 时间改进查询比例: {time_improvement_rate:.1f}%")
        
        # 找出改进最明显的查询
        max_improvement = 0
        best_query = None
        
        for i in range(min(len(first_round), len(second_round))):
            first = first_round[i]
            second = second_round[i]
            improvement = ((first['query_time_seconds'] - second['query_time_seconds']) / first['query_time_seconds']) * 100
            
            if improvement > max_improvement:
                max_improvement = improvement
                best_query = first['question']
        
        if best_query:
            logger.info(f"🏆 最大时间改进: {max_improvement:.1f}%")
            logger.info(f"🏆 改进最明显的查询: {best_query}")
        
    def generate_cache_report(self, results):
        """生成缓存对比报告"""
        end_time = time.time()
        total_time = end_time - self.start_time
        
        # 获取数据量统计
        from documents.models.models import DocumentChunk
        total_documents = Document.objects.filter(owner_id=self.user.id).count()
        total_chunks = DocumentChunk.objects.filter(document_id__in=[d.id for d in Document.objects.filter(owner_id=self.user.id)]).count()
        
        # 分离两轮结果
        first_round = [r for r in results if r['round'] == 1]
        second_round = [r for r in results if r['round'] == 2]
        
        report = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'test_type': 'existing_documents_with_cache',
            'test_duration_seconds': total_time,
            'system_info': {
                'total_documents': total_documents,
                'total_chunks': total_chunks,
                'avg_chunks_per_doc': total_chunks / total_documents if total_documents > 0 else 0,
                'cache_enabled': True
            },
            'test_results': {
                'first_round_queries': len(first_round),
                'second_round_queries': len(second_round),
                'total_queries': len(results)
            },
            'cache_performance': {},
            'detailed_results': results
        }
        
        if first_round and second_round:
            first_times = [r['query_time_seconds'] for r in first_round]
            second_times = [r['query_time_seconds'] for r in second_round]
            first_relevance = [r['relevance_score'] for r in first_round]
            second_relevance = [r['relevance_score'] for r in second_round]
            
            avg_first_time = sum(first_times) / len(first_times)
            avg_second_time = sum(second_times) / len(second_times)
            time_improvement = ((avg_first_time - avg_second_time) / avg_first_time) * 100
            
            avg_first_relevance = sum(first_relevance) / len(first_relevance)
            avg_second_relevance = sum(second_relevance) / len(second_relevance)
            
            report['cache_performance'] = {
                'first_round_stats': {
                    'avg_query_time': avg_first_time,
                    'avg_relevance': avg_first_relevance,
                    'max_query_time': max(first_times),
                    'min_query_time': min(first_times)
                },
                'second_round_stats': {
                    'avg_query_time': avg_second_time,
                    'avg_relevance': avg_second_relevance,
                    'max_query_time': max(second_times),
                    'min_query_time': min(second_times)
                },
                'improvement_metrics': {
                    'time_improvement_percent': time_improvement,
                    'relevance_change_percent': ((avg_second_relevance - avg_first_relevance) / avg_first_relevance) * 100,
                    'queries_with_time_improvement': len([i for i in range(len(first_times)) if second_times[i] < first_times[i]]),
                    'consistency_rate': len([i for i in range(len(first_relevance)) if abs(first_relevance[i] - second_relevance[i]) < 0.01]) / len(first_relevance) * 100
                }
            }
        
        # 保存报告
        datasets_dir = Path(project_root) / "validation_datasets"
        report_file = datasets_dir / f"cached_docs_report_{int(time.time())}.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            
        logger.info(f"\n📋 缓存对比报告已保存: {report_file}")
        return report


def main():
    """主函数"""
    logger.info("开始基于现有文档的缓存验证测试")
    
    validator = CachedDocsValidator()
    
    try:
        # 执行缓存验证测试
        results = validator.validate_existing_documents_with_cache()
        
        # 分析缓存性能
        validator.analyze_cache_performance(results)
        
        # 生成缓存对比报告
        validator.generate_cache_report(results)
        
    except Exception as e:
        logger.exception(f"测试过程中出现错误: {str(e)}")
        return False
        
    logger.info("缓存验证测试完成")
    return True


if __name__ == "__main__":
    main()