#!/usr/bin/env python
"""
使用开源数据集验证SmartDocs系统的可用性
重点测试RAG检索准确性和问答质量
"""

import os
import sys
import json
import requests
import pandas as pd
from pathlib import Path
from loguru import logger
import time
from typing import List, Dict, Any

# Django环境设置
current_path = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_path)
sys.path.insert(0, project_root)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smartdocs_project.settings")
import django
django.setup()

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from documents.models import Document, DocumentChunk
from documents.services.document_processor import DocumentProcessor
from documents.services.vector_db_service import VectorDBService
from qa.services.qa_service import QAService


class DatasetValidator:
    """数据集验证器"""
    
    def __init__(self):
        self.data_dir = Path(project_root) / "validation_datasets"
        self.data_dir.mkdir(exist_ok=True)
        self.embedding_model = "text-embedding-v4"
        self.results = []
        
    def download_dataset(self, url: str, filename: str) -> Path:
        """下载数据集文件"""
        file_path = self.data_dir / filename
        
        if file_path.exists():
            logger.info(f"数据集已存在: {file_path}")
            return file_path
            
        try:
            logger.info(f"下载数据集: {url}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            with open(file_path, 'wb') as f:
                f.write(response.content)
                
            logger.info(f"下载完成: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return None
    
    def validate_with_squad(self):
        """使用SQuAD数据集验证"""
        logger.info("=== SQuAD 数据集验证 ===")
        
        # 下载SQuAD 2.0开发集
        url = "https://rajpurkar.github.io/SQuAD-explorer/dataset/dev-v2.0.json"
        file_path = self.download_dataset(url, "squad_dev_v2.json")
        
        if not file_path or not file_path.exists():
            logger.error("无法获取SQuAD数据集")
            return []
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                squad_data = json.load(f)
                
            results = []
            
            # 只测试前3篇文章，避免过长时间
            for article_idx, article in enumerate(squad_data['data'][:3]):
                logger.info(f"处理文章 {article_idx + 1}: {article['title']}")
                
                # 为每个段落创建文档
                for para_idx, paragraph in enumerate(article['paragraphs'][:2]):
                    context = paragraph['context']
                    title = f"{article['title']}_段落_{para_idx + 1}"
                    
                    # 创建并处理文档
                    doc = self.create_document(context, title)
                    if not self.process_document(doc.id):
                        continue
                        
                    # 测试问答
                    for qa in paragraph['qas'][:3]:  # 每段测试3个问题
                        question = qa['question']
                        answers = [ans['text'] for ans in qa['answers']]
                        is_impossible = qa.get('is_impossible', False)
                        
                        # 执行检索
                        search_results = self.search_documents(question)
                        
                        # 评估结果
                        evaluation = self.evaluate_retrieval(
                            question, answers, search_results, is_impossible
                        )
                        
                        result = {
                            'dataset': 'SQuAD',
                            'article': article['title'],
                            'question': question,
                            'expected_answers': answers,
                            'is_impossible': is_impossible,
                            'retrieval_results': len(search_results),
                            'top_score': search_results[0]['score'] if search_results else 0,
                            'contains_answer': evaluation['contains_answer'],
                            'relevance_score': evaluation['relevance_score']
                        }
                        
                        results.append(result)
                        logger.info(f"问题: {question[:50]}...")
                        logger.info(f"相关性: {evaluation['relevance_score']:.3f}")
                        
            return results
            
        except Exception as e:
            logger.error(f"SQuAD验证失败: {e}")
            return []
    
    def validate_with_msmarco(self):
        """使用MS MARCO样本数据验证"""
        logger.info("=== MS MARCO 数据集验证 ===")
        
        # 使用MS MARCO样本数据
        sample_data = [
            {
                "query": "what is the population of seattle",
                "passages": [
                    {
                        "title": "Seattle Demographics",
                        "text": "Seattle is a major city in Washington state. The population of Seattle is approximately 750,000 people as of the latest census data. The metropolitan area has over 3.9 million residents."
                    },
                    {
                        "title": "Washington State Cities", 
                        "text": "Washington state has several major cities including Seattle, Spokane, and Tacoma. These cities vary significantly in size and economic importance."
                    }
                ]
            },
            {
                "query": "how does machine learning work",
                "passages": [
                    {
                        "title": "Introduction to Machine Learning",
                        "text": "Machine learning is a subset of artificial intelligence that enables computers to learn from data without being explicitly programmed. It uses algorithms to identify patterns in data and make predictions or decisions."
                    },
                    {
                        "title": "Types of Machine Learning",
                        "text": "There are three main types of machine learning: supervised learning, unsupervised learning, and reinforcement learning. Each type has different applications and methodologies."
                    }
                ]
            }
        ]
        
        results = []
        
        for item in sample_data:
            query = item['query']
            
            # 为每个passage创建文档
            for passage in item['passages']:
                doc = self.create_document(passage['text'], passage['title'])
                if not self.process_document(doc.id):
                    continue
            
            # 执行搜索
            search_results = self.search_documents(query)
            
            # 评估结果
            evaluation = self.evaluate_retrieval_simple(query, search_results)
            
            result = {
                'dataset': 'MS MARCO',
                'query': query,
                'retrieval_results': len(search_results),
                'top_score': search_results[0]['score'] if search_results else 0,
                'avg_score': sum(r['score'] for r in search_results) / len(search_results) if search_results else 0,
                'relevance_score': evaluation['relevance_score']
            }
            
            results.append(result)
            logger.info(f"查询: {query}")
            logger.info(f"检索到 {len(search_results)} 个结果")
            
        return results
    
    def validate_with_chinese_data(self):
        """使用中文数据验证"""
        logger.info("=== 中文数据集验证 ===")
        
        # 中文测试数据
        chinese_data = [
            {
                "documents": [
                    {
                        "title": "人工智能发展历史",
                        "content": "人工智能的发展可以追溯到20世纪50年代。1950年，阿兰·图灵提出了著名的图灵测试。1956年，达特茅斯会议标志着人工智能学科的正式诞生。经过几十年的发展，人工智能技术在近年来取得了突破性进展。"
                    },
                    {
                        "title": "深度学习技术",
                        "content": "深度学习是机器学习的一个分支，它模仿人脑神经网络的结构和功能。深度学习使用多层神经网络来处理数据，能够自动学习数据的特征表示。卷积神经网络、循环神经网络和Transformer是深度学习的重要架构。"
                    }
                ],
                "questions": [
                    "人工智能是什么时候诞生的？",
                    "图灵测试是谁提出的？",
                    "深度学习有哪些重要架构？",
                    "什么是卷积神经网络？"
                ]
            },
            {
                "documents": [
                    {
                        "title": "自然语言处理应用",
                        "content": "自然语言处理（NLP）是人工智能的重要应用领域。主要包括机器翻译、情感分析、文本摘要、问答系统等任务。现代NLP技术大量使用深度学习方法，特别是基于Transformer的预训练模型如BERT、GPT等。"
                    },
                    {
                        "title": "计算机视觉发展",
                        "content": "计算机视觉致力于让计算机能够理解和分析视觉信息。主要任务包括图像分类、目标检测、语义分割、人脸识别等。深度学习技术，特别是卷积神经网络的发展，极大地推动了计算机视觉领域的进步。"
                    }
                ],
                "questions": [
                    "自然语言处理包括哪些任务？",
                    "BERT是什么？",
                    "计算机视觉的主要任务有哪些？",
                    "什么技术推动了计算机视觉的发展？"
                ]
            }
        ]
        
        results = []
        
        for data_group in chinese_data:
            # 创建文档
            doc_ids = []
            for doc_data in data_group['documents']:
                doc = self.create_document(doc_data['content'], doc_data['title'])
                if self.process_document(doc.id):
                    doc_ids.append(doc.id)
            
            # 测试问题
            for question in data_group['questions']:
                search_results = self.search_documents(question)
                
                evaluation = self.evaluate_retrieval_simple(question, search_results)
                
                result = {
                    'dataset': 'Chinese',
                    'question': question,
                    'retrieval_results': len(search_results),
                    'top_score': search_results[0]['score'] if search_results else 0,
                    'relevance_score': evaluation['relevance_score']
                }
                
                results.append(result)
                logger.info(f"问题: {question}")
                logger.info(f"相关性: {evaluation['relevance_score']:.3f}")
        
        return results
    
    def create_document(self, content: str, title: str) -> Document:
        """创建文档"""
        import uuid
        
        doc = Document.objects.create(
            title=title,
            file_type="txt",
            description="验证测试文档",
            owner_id=1,
            status="pending"
        )
        
        # 保存文件
        file_name = f"{uuid.uuid4()}.txt"
        file_path = f"documents/1/{file_name}"
        default_storage.save(file_path, ContentFile(content.encode("utf-8")))
        
        doc.file = file_path
        doc.save()
        
        return doc
    
    def process_document(self, doc_id: int) -> bool:
        """处理文档"""
        try:
            processor = DocumentProcessor(embedding_model_version=self.embedding_model)
            success = processor.process_document(doc_id)
            
            if success:
                # 索引文档
                vector_db = VectorDBService(embedding_model_version=self.embedding_model)
                doc = Document.objects.get(id=doc_id)
                return vector_db.index_document(doc)
            
            return False
            
        except Exception as e:
            logger.error(f"处理文档失败: {e}")
            return False
    
    def search_documents(self, query: str) -> List[Dict]:
        """搜索文档"""
        try:
            vector_db = VectorDBService(embedding_model_version=self.embedding_model)
            return vector_db.search(query, top_k=5)
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []
    
    def evaluate_retrieval(self, question: str, expected_answers: List[str], 
                          search_results: List[Dict], is_impossible: bool = False) -> Dict:
        """评估检索结果"""
        if not search_results:
            return {'contains_answer': False, 'relevance_score': 0.0}
        
        contains_answer = False
        max_relevance = 0.0
        
        if not is_impossible and expected_answers:
            for result in search_results:
                content = result['content'].lower()
                
                for answer in expected_answers:
                    if answer.lower() in content:
                        contains_answer = True
                        max_relevance = max(max_relevance, result['score'])
        
        # 即使没有精确匹配，也给出基于相似度的分数
        avg_score = sum(r['score'] for r in search_results) / len(search_results)
        relevance_score = max(max_relevance, avg_score * 0.5)
        
        return {
            'contains_answer': contains_answer,
            'relevance_score': relevance_score
        }
    
    def evaluate_retrieval_simple(self, query: str, search_results: List[Dict]) -> Dict:
        """简单评估检索结果"""
        if not search_results:
            return {'relevance_score': 0.0}
        
        # 基于检索分数评估
        avg_score = sum(r['score'] for r in search_results) / len(search_results)
        top_score = search_results[0]['score']
        
        # 综合评分
        relevance_score = (top_score * 0.6 + avg_score * 0.4)
        
        return {'relevance_score': relevance_score}
    
    def generate_report(self, all_results: List[Dict]):
        """生成验证报告"""
        logger.info("=== 数据集验证报告 ===")
        
        # 按数据集分组统计
        datasets = {}
        for result in all_results:
            dataset = result['dataset']
            if dataset not in datasets:
                datasets[dataset] = []
            datasets[dataset].append(result)
        
        overall_stats = {
            'total_questions': len(all_results),
            'avg_relevance': sum(r['relevance_score'] for r in all_results) / len(all_results) if all_results else 0,
            'retrieval_success_rate': sum(1 for r in all_results if r['retrieval_results'] > 0) / len(all_results) if all_results else 0
        }
        
        # 生成报告
        report = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'overall_statistics': overall_stats,
            'dataset_details': {}
        }
        
        for dataset_name, results in datasets.items():
            stats = {
                'count': len(results),
                'avg_relevance': sum(r['relevance_score'] for r in results) / len(results),
                'retrieval_success_rate': sum(1 for r in results if r['retrieval_results'] > 0) / len(results),
                'avg_top_score': sum(r['top_score'] for r in results) / len(results)
            }
            
            if 'contains_answer' in results[0]:
                stats['answer_found_rate'] = sum(1 for r in results if r['contains_answer']) / len(results)
            
            report['dataset_details'][dataset_name] = stats
            
            logger.info(f"\n{dataset_name} 数据集:")
            logger.info(f"  测试问题数: {stats['count']}")
            logger.info(f"  平均相关性: {stats['avg_relevance']:.3f}")
            logger.info(f"  检索成功率: {stats['retrieval_success_rate']:.1%}")
            logger.info(f"  平均Top1分数: {stats['avg_top_score']:.3f}")
            if 'answer_found_rate' in stats:
                logger.info(f"  答案发现率: {stats['answer_found_rate']:.1%}")
        
        logger.info(f"\n整体统计:")
        logger.info(f"  总测试问题: {overall_stats['total_questions']}")
        logger.info(f"  平均相关性: {overall_stats['avg_relevance']:.3f}")
        logger.info(f"  检索成功率: {overall_stats['retrieval_success_rate']:.1%}")
        
        # 保存详细报告
        report_file = self.data_dir / f"validation_report_{int(time.time())}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"详细报告已保存: {report_file}")
        
        return report


def main():
    """主函数"""
    validator = DatasetValidator()
    
    logger.info("开始数据集验证测试")
    
    all_results = []
    
    # 1. SQuAD验证
    try:
        squad_results = validator.validate_with_squad()
        all_results.extend(squad_results)
        logger.info(f"SQuAD验证完成，测试了 {len(squad_results)} 个问题")
    except Exception as e:
        logger.error(f"SQuAD验证失败: {e}")
    
    # 2. MS MARCO验证
    try:
        msmarco_results = validator.validate_with_msmarco()
        all_results.extend(msmarco_results)
        logger.info(f"MS MARCO验证完成，测试了 {len(msmarco_results)} 个查询")
    except Exception as e:
        logger.error(f"MS MARCO验证失败: {e}")
    
    # 3. 中文数据验证
    try:
        chinese_results = validator.validate_with_chinese_data()
        all_results.extend(chinese_results)
        logger.info(f"中文数据验证完成，测试了 {len(chinese_results)} 个问题")
    except Exception as e:
        logger.error(f"中文数据验证失败: {e}")
    
    # 生成综合报告
    if all_results:
        validator.generate_report(all_results)
    else:
        logger.warning("没有获得任何验证结果")
    
    logger.info("数据集验证完成")


if __name__ == "__main__":
    main()