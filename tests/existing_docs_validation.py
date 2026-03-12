#!/usr/bin/env python
"""
基于现有文档的验证测试
不创建新文档，不使用缓存，测试真实查询性能
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
from django.contrib.auth.models import User


class ExistingDocsValidator:
    """基于现有文档的验证器"""
    
    def __init__(self):
        self.user = User.objects.get(id=1)
        self.results = []
        self.start_time = time.time()
        
    def validate_existing_documents(self):
        """使用现有文档进行验证测试"""
        logger.info("=== 现有文档验证测试（无缓存） ===")
        
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
        
        # 多样化的测试查询
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
            "网络安全防护措施",
            
            # 英文技术查询
            "What is artificial intelligence?",
            "How does machine learning work?",
            "Deep learning applications",
            "Computer vision techniques",
            "Natural language processing",
            "Big data analytics",
            "Cloud computing benefits",
            "Blockchain technology",
            "Internet of Things",
            "Cybersecurity measures",
            
            # 具体技术问题
            "Python编程语言特点",
            "JavaScript框架比较",
            "数据库设计原则",
            "软件工程方法论",
            "算法复杂度分析",
            "系统架构设计",
            "微服务架构",
            "容器化技术",
            "DevOps实践",
            "敏捷开发方法",
            
            # 业务相关查询
            "项目管理最佳实践",
            "产品设计流程",
            "用户体验设计",
            "商业模式创新",
            "数字化转型",
            "电子商务平台",
            "在线教育技术",
            "金融科技发展",
            "智能制造趋势",
            "可持续发展技术"
        ]
        
        for i, query in enumerate(test_queries):
            logger.info(f"\n--- 查询 {i+1}/{len(test_queries)} ---")
            logger.info(f"查询内容: {query}")
            
            # 执行搜索（禁用缓存）
            start_time = time.time()
            search_results = self._search_documents_no_cache(query)
            query_time = time.time() - start_time
            
            if search_results:
                relevance = search_results[0]['relevance_score']
                
                result = {
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
                
                results.append(result)
                
                logger.info(f"✓ 相关性: {relevance:.4f}")
                logger.info(f"✓ 查询时间: {query_time:.3f}秒")
                logger.info(f"✓ 检索到文档数: {len(search_results)}")
                logger.info(f"✓ 最佳匹配: {search_results[0]['document_title']}")
                logger.info(f"✓ 内容预览: {search_results[0]['content_preview'][:100]}...")
                
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
                
            # 短暂延迟，避免过快的API调用
            time.sleep(0.1)
                
        logger.info(f"\n现有文档验证完成，测试了 {len(results)} 个查询")
        return results
        
    def _search_documents_no_cache(self, query: str):
        """搜索文档（禁用缓存）"""
        try:
            # 使用非缓存版本的搜索
            vector_db = VectorDBService.get_instance()
            
            # 直接调用search方法，不使用缓存的静态方法
            results = vector_db.search(query, top_k=10)
            
            formatted_results = []
            for result in results:
                formatted_results.append({
                    'document_id': result.get('id'),
                    'relevance_score': 1 - result.get('score', 1),  # 转换为相关性分数
                    'content_preview': result.get('content', '')[:200],
                    'document_title': result.get('title', 'Unknown'),
                    'chunk_index': result.get('chunk_index', 0),
                    'embedding_model': result.get('embedding_model_version', 'unknown')
                })
                    
            return formatted_results
        except Exception as e:
            logger.error(f"搜索失败: {str(e)}")
            return []
            
    def analyze_performance(self, results):
        """分析性能数据"""
        if not results:
            logger.warning("没有结果可以分析")
            return
            
        logger.info("\n=== 性能分析 ===")
        
        # 计算统计指标
        relevance_scores = [r['relevance_score'] for r in results]
        query_times = [r['query_time_seconds'] for r in results]
        
        # 相关性统计
        avg_relevance = sum(relevance_scores) / len(relevance_scores)
        max_relevance = max(relevance_scores)
        min_relevance = min(relevance_scores)
        
        # 查询时间统计
        avg_query_time = sum(query_times) / len(query_times)
        max_query_time = max(query_times)
        min_query_time = min(query_times)
        
        # 相关性分布
        excellent = len([s for s in relevance_scores if s >= 0.9])
        good = len([s for s in relevance_scores if 0.7 <= s < 0.9])
        fair = len([s for s in relevance_scores if 0.5 <= s < 0.7])
        poor = len([s for s in relevance_scores if s < 0.5])
        
        # 查询时间分布
        very_fast = len([t for t in query_times if t < 0.1])
        fast = len([t for t in query_times if 0.1 <= t < 0.5])
        medium = len([t for t in query_times if 0.5 <= t < 1.0])
        slow = len([t for t in query_times if t >= 1.0])
        
        logger.info(f"📊 总查询数: {len(results)}")
        logger.info(f"📊 平均相关性: {avg_relevance:.4f}")
        logger.info(f"📊 最高相关性: {max_relevance:.4f}")
        logger.info(f"📊 最低相关性: {min_relevance:.4f}")
        logger.info(f"📊 平均查询时间: {avg_query_time:.3f}秒")
        logger.info(f"📊 最长查询时间: {max_query_time:.3f}秒")
        logger.info(f"📊 最短查询时间: {min_query_time:.3f}秒")
        
        logger.info(f"\n📈 相关性分布:")
        logger.info(f"  优秀 (≥0.9): {excellent} ({excellent/len(results)*100:.1f}%)")
        logger.info(f"  良好 (0.7-0.9): {good} ({good/len(results)*100:.1f}%)")
        logger.info(f"  一般 (0.5-0.7): {fair} ({fair/len(results)*100:.1f}%)")
        logger.info(f"  较差 (<0.5): {poor} ({poor/len(results)*100:.1f}%)")
        
        logger.info(f"\n⚡ 查询时间分布:")
        logger.info(f"  很快 (<0.1s): {very_fast} ({very_fast/len(results)*100:.1f}%)")
        logger.info(f"  快速 (0.1-0.5s): {fast} ({fast/len(results)*100:.1f}%)")
        logger.info(f"  中等 (0.5-1s): {medium} ({medium/len(results)*100:.1f}%)")
        logger.info(f"  较慢 (≥1s): {slow} ({slow/len(results)*100:.1f}%)")
        
        # 找出表现最好和最差的查询
        best_result = max(results, key=lambda x: x['relevance_score'])
        worst_result = min(results, key=lambda x: x['relevance_score'])
        
        logger.info(f"\n🏆 最佳查询:")
        logger.info(f"  问题: {best_result['question']}")
        logger.info(f"  相关性: {best_result['relevance_score']:.4f}")
        logger.info(f"  匹配文档: {best_result['top_result']['title']}")
        
        logger.info(f"\n😞 最差查询:")
        logger.info(f"  问题: {worst_result['question']}")
        logger.info(f"  相关性: {worst_result['relevance_score']:.4f}")
        logger.info(f"  匹配文档: {worst_result['top_result']['title']}")
        
    def generate_report(self, results):
        """生成详细报告"""
        end_time = time.time()
        total_time = end_time - self.start_time
        
        # 获取数据量统计
        from documents.models.models import DocumentChunk
        total_documents = Document.objects.filter(owner_id=self.user.id).count()
        total_chunks = DocumentChunk.objects.filter(document_id__in=[d.id for d in Document.objects.filter(owner_id=self.user.id)]).count()
        
        report = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'test_type': 'existing_documents_no_cache',
            'test_duration_seconds': total_time,
            'system_info': {
                'total_documents': total_documents,
                'total_chunks': total_chunks,
                'avg_chunks_per_doc': total_chunks / total_documents if total_documents > 0 else 0
            },
            'test_results': {
                'total_queries': len(results),
                'successful_queries': len([r for r in results if r['retrieved_docs'] > 0]),
                'failed_queries': len([r for r in results if r['retrieved_docs'] == 0])
            },
            'performance_metrics': {},
            'detailed_results': results
        }
        
        if results:
            relevance_scores = [r['relevance_score'] for r in results]
            query_times = [r['query_time_seconds'] for r in results]
            
            report['performance_metrics'] = {
                'relevance_stats': {
                    'avg': sum(relevance_scores) / len(relevance_scores),
                    'max': max(relevance_scores),
                    'min': min(relevance_scores),
                    'distribution': {
                        'excellent_0.9+': len([s for s in relevance_scores if s >= 0.9]),
                        'good_0.7-0.9': len([s for s in relevance_scores if 0.7 <= s < 0.9]),
                        'fair_0.5-0.7': len([s for s in relevance_scores if 0.5 <= s < 0.7]),
                        'poor_below_0.5': len([s for s in relevance_scores if s < 0.5])
                    }
                },
                'timing_stats': {
                    'avg_query_time': sum(query_times) / len(query_times),
                    'max_query_time': max(query_times),
                    'min_query_time': min(query_times),
                    'distribution': {
                        'very_fast_0-0.1s': len([t for t in query_times if t < 0.1]),
                        'fast_0.1-0.5s': len([t for t in query_times if 0.1 <= t < 0.5]),
                        'medium_0.5-1s': len([t for t in query_times if 0.5 <= t < 1.0]),
                        'slow_1s+': len([t for t in query_times if t >= 1.0])
                    }
                }
            }
        
        # 保存报告
        datasets_dir = Path(project_root) / "validation_datasets"
        report_file = datasets_dir / f"existing_docs_report_{int(time.time())}.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            
        logger.info(f"\n📋 详细报告已保存: {report_file}")
        return report


def main():
    """主函数"""
    logger.info("开始基于现有文档的验证测试（无缓存）")
    
    validator = ExistingDocsValidator()
    
    try:
        # 执行验证测试
        results = validator.validate_existing_documents()
        
        # 分析性能
        validator.analyze_performance(results)
        
        # 生成报告
        validator.generate_report(results)
        
    except Exception as e:
        logger.exception(f"测试过程中出现错误: {str(e)}")
        return False
        
    logger.info("现有文档验证测试完成")
    return True


if __name__ == "__main__":
    main()