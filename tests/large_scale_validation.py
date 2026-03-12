#!/usr/bin/env python
"""
大规模数据集验证测试
使用更多数据量全面验证SmartDocs系统性能和可用性
"""

import os
import sys
import json
import time
from pathlib import Path
from loguru import logger
import requests
from typing import List, Dict, Any
import random

# Django环境设置
current_path = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_path)
sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartdocs_project.settings')

import django
django.setup()

from documents.models import Document
from documents.services.document_processor import DocumentProcessor
from documents.services.vector_db_service import VectorDBService
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
import tempfile


class LargeScaleValidator:
    """大规模数据验证器"""
    
    def __init__(self):
        self.user = User.objects.get(id=1)
        self.results = {
            'wikipedia_test': [],
            'news_test': [],
            'technical_docs': [],
            'qa_pairs': [],
            'performance_metrics': {}
        }
        self.start_time = time.time()
        
    def download_large_datasets(self):
        """下载更大的数据集"""
        logger.info("下载大规模数据集...")
        
        datasets_dir = Path(project_root) / "validation_datasets" / "large_scale"
        datasets_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. 下载更多的SQuAD数据
        squad_train_url = "https://rajpurkar.github.io/SQuAD-explorer/dataset/train-v2.0.json"
        squad_train_path = datasets_dir / "squad_train_v2.json"
        
        if not squad_train_path.exists():
            logger.info("下载SQuAD训练集...")
            self._download_file(squad_train_url, squad_train_path)
            
        # 2. 创建大量测试文档
        self._create_test_documents(datasets_dir)
        
        return datasets_dir
        
    def _download_file(self, url: str, path: Path):
        """下载文件"""
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            with open(path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            logger.info(f"下载完成: {path}")
        except Exception as e:
            logger.error(f"下载失败 {url}: {str(e)}")
            
    def _create_test_documents(self, datasets_dir: Path):
        """创建大量测试文档"""
        logger.info("创建测试文档...")
        
        # 创建100个不同主题的文档
        topics = [
            "人工智能", "机器学习", "深度学习", "神经网络", "计算机视觉",
            "自然语言处理", "数据科学", "大数据", "云计算", "区块链",
            "物联网", "5G技术", "量子计算", "边缘计算", "网络安全",
            "软件工程", "数据库", "操作系统", "编程语言", "算法",
            "互联网", "移动应用", "Web开发", "游戏开发", "AR/VR",
            "金融科技", "电子商务", "在线教育", "智能制造", "自动驾驶",
            "医疗健康", "生物技术", "环境科学", "新能源", "航空航天",
            "机器人", "智能家居", "智慧城市", "数字货币", "供应链",
            "商业分析", "项目管理", "产品设计", "用户体验", "营销策略",
            "经济学", "心理学", "社会学", "历史", "文学",
            "物理学", "化学", "数学", "生物学", "地理学"
        ]
        
        test_docs_dir = datasets_dir / "test_documents"
        test_docs_dir.mkdir(exist_ok=True)
        
        for i, topic in enumerate(topics[:50]):  # 创建50个文档
            content = self._generate_document_content(topic, i)
            # 清理文件名中的特殊字符
            safe_topic = topic.replace('/', '_').replace('\\', '_')
            doc_path = test_docs_dir / f"{safe_topic}_{i:03d}.txt"
            
            with open(doc_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
        logger.info(f"创建了50个测试文档")
        
    def _generate_document_content(self, topic: str, doc_id: int) -> str:
        """生成文档内容"""
        templates = [
            f"""# {topic}概述

{topic}是当今科技领域的重要分支，具有广泛的应用前景。本文档将详细介绍{topic}的基本概念、技术原理、应用场景和发展趋势。

## 基本概念
{topic}的定义和核心概念包括多个方面。首先，{topic}涉及的技术栈非常广泛，包括理论基础、实践应用和工程实现。

## 技术原理
{topic}的技术原理基于多年的研究和实践积累。其核心算法和方法论已经在各个领域得到验证和应用。

## 应用场景
{topic}在实际应用中表现出色，主要应用场景包括：
- 企业级应用
- 消费级产品
- 科研项目
- 教育培训

## 发展趋势
未来{topic}的发展将朝着更加智能化、自动化的方向前进。预计在未来几年内，{topic}将取得重大突破。

## 挑战与机遇
{topic}面临的主要挑战包括技术壁垒、标准化问题和人才缺口。同时，这也为相关从业者提供了巨大的发展机遇。

## 结论
{topic}作为前沿技术，将在未来发挥越来越重要的作用。我们需要持续关注其发展动态，把握技术趋势。

文档编号: DOC-{doc_id:05d}
创建时间: 2025-08-16
版本: 1.0
""",
            f"""# {topic}技术指南

## 前言
本指南旨在帮助读者全面了解{topic}技术，从基础概念到实际应用，提供系统性的学习路径。

## 第一章 基础知识
{topic}的基础知识包括以下几个方面：

### 1.1 历史发展
{topic}的发展经历了多个重要阶段，每个阶段都有其特定的技术特点和应用场景。

### 1.2 核心概念
理解{topic}需要掌握一系列核心概念，这些概念构成了整个技术体系的基础。

### 1.3 技术架构
{topic}的技术架构设计考虑了性能、可扩展性和可维护性等多个维度。

## 第二章 实现方法
{topic}的实现方法多种多样，需要根据具体应用场景选择合适的技术方案。

### 2.1 算法选择
不同的算法适用于不同的问题类型，选择合适的算法是成功实现{topic}的关键。

### 2.2 工具与框架
现有的工具和框架可以大大简化{topic}的开发过程，提高开发效率。

### 2.3 性能优化
性能优化是{topic}实现中的重要环节，涉及算法优化、系统调优等多个方面。

## 第三章 最佳实践
基于多年的实践经验，我们总结了{topic}领域的最佳实践。

### 3.1 设计原则
良好的设计原则是项目成功的基础，需要在项目初期就确定并严格遵守。

### 3.2 开发流程
规范的开发流程可以确保项目质量，降低开发风险。

### 3.3 测试策略
全面的测试策略是保证{topic}系统可靠性的重要手段。

## 总结
{topic}技术发展迅速，需要持续学习和实践。本指南提供了系统性的学习框架，希望对读者有所帮助。

技术难度: ⭐⭐⭐
适用人群: 中级开发者
文档ID: GUIDE-{doc_id:05d}
"""
        ]
        
        return random.choice(templates)
        
    def validate_with_large_squad_limited(self, datasets_dir: Path):
        """使用完整SQuAD数据集验证"""
        logger.info("=== 大规模SQuAD数据集验证 ===")
        
        squad_file = datasets_dir / "squad_train_v2.json"
        if not squad_file.exists():
            logger.warning("SQuAD训练集文件不存在，跳过大规模测试")
            return []
            
        with open(squad_file, 'r', encoding='utf-8') as f:
            squad_data = json.load(f)
            
        results = []
        processed_articles = 0
        max_articles = 100  # 大规模测试，不限制数量
        
        for article in squad_data['data'][:max_articles]:
            if processed_articles >= max_articles:
                break
                
            logger.info(f"处理文章 {processed_articles + 1}: {article['title']}")
            
            # 处理文章的所有段落
            for paragraph in article['paragraphs']:
                # 创建文档
                doc = self._create_document(
                    title=f"{article['title']}_段落_{len(results)+1}",
                    content=paragraph['context']
                )
                
                if not self.process_document(doc.id):
                    continue
                    
                # 测试该段落的所有问题（限制数量）
                for qa in paragraph['qas'][:3]:  # 每段落最多测试3个问题
                    if qa['is_impossible']:
                        continue
                        
                    query = qa['question']
                    expected_answers = [ans['text'] for ans in qa['answers']]
                    
                    # 执行检索测试
                    start_time = time.time()
                    search_results = self._search_documents(query)
                    query_time = time.time() - start_time
                    
                    if search_results:
                        relevance = search_results[0]['relevance_score']
                        results.append({
                            'dataset': 'Large SQuAD',
                            'question': query[:50] + '...',
                            'expected_answers': expected_answers,
                            'relevance_score': relevance,
                            'retrieved_docs': len(search_results),
                            'article_title': article['title'],
                            'query_time_seconds': query_time
                        })
                        
                        logger.info(f"问题: {query[:50]}...")
                        logger.info(f"相关性: {relevance:.3f}")
                        
            processed_articles += 1
            
        logger.info(f"大规模SQuAD验证完成，测试了 {len(results)} 个问题")
        return results
        
    def validate_with_generated_docs_limited(self, datasets_dir: Path):
        """使用生成的大量文档进行验证"""
        logger.info("=== 大量文档验证 ===")
        
        test_docs_dir = datasets_dir / "test_documents"
        doc_files = list(test_docs_dir.glob("*.txt"))
        
        logger.info(f"找到 {len(doc_files)} 个测试文档")
        
        results = []
        processed_docs = 0
        
        # 处理所有文档
        for doc_file in doc_files:
            with open(doc_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 创建文档
            doc = self._create_document(
                title=doc_file.stem,
                content=content
            )
            
            if not self.process_document(doc.id):
                continue
                
            processed_docs += 1
            
            # 生成测试查询
            topic = doc_file.stem.split('_')[0]
            queries = self._generate_test_queries(topic)
            
            for query in queries:
                start_time = time.time()
                search_results = self._search_documents(query)
                query_time = time.time() - start_time
                
                if search_results:
                    relevance = search_results[0]['relevance_score']
                    results.append({
                        'dataset': 'Generated Docs',
                        'question': query,
                        'relevance_score': relevance,
                        'retrieved_docs': len(search_results),
                        'source_doc': doc_file.stem,
                        'query_time_seconds': query_time
                    })
                    
                    logger.info(f"查询: {query}")
                    logger.info(f"相关性: {relevance:.3f}")
                    
        logger.info(f"大量文档验证完成，处理了 {processed_docs} 个文档，测试了 {len(results)} 个查询")
        return results
        
    def _generate_test_queries(self, topic: str) -> List[str]:
        """为主题生成测试查询"""
        query_templates = [
            f"{topic}是什么？",
            f"{topic}的主要应用有哪些？",
            f"{topic}的技术原理是什么？",
            f"{topic}有什么优势？",
            f"{topic}面临的挑战是什么？",
            f"如何学习{topic}？",
            f"{topic}的发展趋势如何？",
            f"{topic}与其他技术的区别？"
        ]
        
        return random.sample(query_templates, min(3, len(query_templates)))
        
    def performance_test(self):
        """性能测试"""
        logger.info("=== 性能测试 ===")
        
        # 测试并发查询性能
        import threading
        import time
        
        queries = [
            "人工智能的发展历史",
            "机器学习算法分类",
            "深度学习网络架构",
            "自然语言处理技术",
            "计算机视觉应用"
        ]
        
        results = []
        
        def query_worker(query, thread_id):
            start_time = time.time()
            search_results = self._search_documents(query)
            end_time = time.time()
            
            results.append({
                'thread_id': thread_id,
                'query': query,
                'response_time': end_time - start_time,
                'results_count': len(search_results) if search_results else 0
            })
            
        # 启动多线程查询
        threads = []
        for i, query in enumerate(queries * 5):  # 每个查询执行5次
            thread = threading.Thread(target=query_worker, args=(query, i))
            threads.append(thread)
            thread.start()
            
        # 等待所有线程完成
        for thread in threads:
            thread.join()
            
        # 计算性能指标
        response_times = [r['response_time'] for r in results]
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        min_response_time = min(response_times)
        
        self.results['performance_metrics'] = {
            'concurrent_queries': len(results),
            'avg_response_time': avg_response_time,
            'max_response_time': max_response_time,
            'min_response_time': min_response_time,
            'queries_per_second': len(results) / max(response_times) if response_times else 0
        }
        
        logger.info(f"性能测试完成:")
        logger.info(f"  并发查询数: {len(results)}")
        logger.info(f"  平均响应时间: {avg_response_time:.3f}秒")
        logger.info(f"  最大响应时间: {max_response_time:.3f}秒")
        logger.info(f"  最小响应时间: {min_response_time:.3f}秒")
        
    def _create_document(self, title: str, content: str):
        """创建文档"""
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            
            # 读取文件内容
            with open(tmp_file.name, 'rb') as f:
                file_content = f.read()
                
            # 创建文档对象
            doc = Document.objects.create(
                title=title,
                file_type='txt',
                owner_id=self.user.id
            )
            
            # 保存文件
            doc.file.save(
                f"{title}.txt",
                ContentFile(file_content),
                save=False
            )
            doc.save()
            
            # 清理临时文件
            os.unlink(tmp_file.name)
            
            return doc
            
    def process_document(self, doc_id: int) -> bool:
        """处理文档并建立索引"""
        try:
            processor = DocumentProcessor()
            success = processor.process_document(doc_id)
            
            if success:
                # 建立向量索引
                vector_db = VectorDBService.get_instance()
                doc = Document.objects.get(id=doc_id)
                vector_db.index_document(doc)
            
            return success
        except Exception as e:
            logger.error(f"处理文档失败: {str(e)}")
            return False
            
    def _search_documents(self, query: str):
        """搜索文档"""
        try:
            vector_db = VectorDBService.get_instance()
            results = vector_db.search(query, top_k=5)
            
            formatted_results = []
            for result in results:
                formatted_results.append({
                    'chunk_id': result.get('id'),
                    'relevance_score': 1 - result.get('score', 1),  # 转换为相关性分数
                    'content_preview': result.get('content', '')[:200],
                    'document_title': result.get('title', 'Unknown')
                })
                    
            return formatted_results
        except Exception as e:
            logger.error(f"搜索失败: {str(e)}")
            return []
            
    def generate_comprehensive_report(self):
        """生成综合报告"""
        end_time = time.time()
        total_time = end_time - self.start_time
        
        # 合并所有结果
        all_results = []
        for dataset_results in self.results.values():
            if isinstance(dataset_results, list):
                all_results.extend(dataset_results)
                
        if not all_results:
            logger.warning("没有测试结果，无法生成报告")
            return
            
        # 计算统计指标
        relevance_scores = [r['relevance_score'] for r in all_results if 'relevance_score' in r]
        query_times = [r['query_time_seconds'] for r in all_results if 'query_time_seconds' in r]
        
        # 统计数据量
        from documents.models import Document
        from documents.models.models import DocumentChunk
        total_documents = Document.objects.filter(owner_id=self.user.id).count()
        total_chunks = DocumentChunk.objects.filter(document__owner_id=self.user.id).count()
        
        # 统计各数据集的数据量
        dataset_stats = {}
        for dataset_name in set(r.get('dataset', 'Unknown') for r in all_results):
            dataset_results = [r for r in all_results if r.get('dataset') == dataset_name]
            dataset_stats[dataset_name] = {
                'questions_count': len(dataset_results),
                'unique_documents': len(set(r.get('source_doc', r.get('article_title', '')) for r in dataset_results))
            }
        
        report = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'test_duration_seconds': total_time,
            'total_questions': len(all_results),
            'datasets_tested': list(set(r.get('dataset', 'Unknown') for r in all_results)),
            'data_volume_statistics': {
                'total_documents_in_system': total_documents,
                'total_document_chunks': total_chunks,
                'dataset_breakdown': dataset_stats,
                'avg_chunks_per_document': total_chunks / total_documents if total_documents > 0 else 0
            },
            'performance_metrics': self.results.get('performance_metrics', {}),
            'statistical_analysis': {
                'relevance_metrics': {
                    'avg_relevance': sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0,
                    'max_relevance': max(relevance_scores) if relevance_scores else 0,
                    'min_relevance': min(relevance_scores) if relevance_scores else 0,
                    'relevance_distribution': {
                        'excellent_0.8+': len([s for s in relevance_scores if s >= 0.8]),
                        'good_0.6-0.8': len([s for s in relevance_scores if 0.6 <= s < 0.8]),
                        'fair_0.4-0.6': len([s for s in relevance_scores if 0.4 <= s < 0.6]),
                        'poor_below_0.4': len([s for s in relevance_scores if s < 0.4])
                    }
                },
                'query_time_metrics': {
                    'avg_query_time': sum(query_times) / len(query_times) if query_times else 0,
                    'max_query_time': max(query_times) if query_times else 0,
                    'min_query_time': min(query_times) if query_times else 0,
                    'query_time_distribution': {
                        'very_fast_0-0.1s': len([t for t in query_times if t < 0.1]),
                        'fast_0.1-0.5s': len([t for t in query_times if 0.1 <= t < 0.5]),
                        'medium_0.5-1s': len([t for t in query_times if 0.5 <= t < 1.0]),
                        'slow_1s+': len([t for t in query_times if t >= 1.0])
                    }
                }
            },
            'detailed_results': all_results[:100]  # 只保存前100个详细结果
        }
        
        # 保存报告
        datasets_dir = Path(project_root) / "validation_datasets"
        report_file = datasets_dir / f"large_scale_report_{int(time.time())}.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            
        logger.info("=== 大规模验证报告 ===")
        logger.info(f"测试总时间: {total_time:.2f}秒")
        logger.info(f"测试问题总数: {len(all_results)}")
        logger.info(f"系统文档总数: {report['data_volume_statistics']['total_documents_in_system']}")
        logger.info(f"文档块总数: {report['data_volume_statistics']['total_document_chunks']}")
        logger.info(f"平均每文档块数: {report['data_volume_statistics']['avg_chunks_per_document']:.1f}")
        logger.info(f"平均相关性: {report['statistical_analysis']['relevance_metrics']['avg_relevance']:.3f}")
        logger.info(f"平均查询时间: {report['statistical_analysis']['query_time_metrics']['avg_query_time']:.3f}秒")
        logger.info(f"查询时间分布: {report['statistical_analysis']['query_time_metrics']['query_time_distribution']}")
        logger.info(f"性能指标: {report['performance_metrics']}")
        logger.info(f"详细报告: {report_file}")
        
        return report
        

def main():
    """主函数"""
    logger.info("开始大规模数据集验证测试")
    
    validator = LargeScaleValidator()
    
    try:
        # 下载和准备数据
        datasets_dir = validator.download_large_datasets()
        
        # 执行大规模验证测试（限制数量避免API过度调用）
        validator.results['squad_large'] = validator.validate_with_large_squad_limited(datasets_dir)
        validator.results['generated_docs'] = validator.validate_with_generated_docs_limited(datasets_dir)
        
        # 性能测试
        validator.performance_test()
        
        # 生成综合报告
        validator.generate_comprehensive_report()
        
    except Exception as e:
        logger.exception(f"测试过程中出现错误: {str(e)}")
        return False
        
    logger.info("大规模数据集验证完成")
    return True


if __name__ == "__main__":
    main()