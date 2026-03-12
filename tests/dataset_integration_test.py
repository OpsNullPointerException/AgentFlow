#!/usr/bin/env python
"""
开源数据集集成测试脚本
用于测试SmartDocs系统在不同数据集上的表现
"""

import os
import sys
import json
import requests
import zipfile
from pathlib import Path
from loguru import logger
import time

# Django环境设置
current_path = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_path)
sys.path.insert(0, project_root)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smartdocs_project.settings")
import django
django.setup()

from documents.models import Document, DocumentChunk
from documents.services.document_processor import DocumentProcessor
from documents.services.vector_db_service import VectorDBService


class DatasetTester:
    """数据集测试类"""
    
    def __init__(self):
        self.data_dir = Path(project_root) / "test_datasets"
        self.data_dir.mkdir(exist_ok=True)
        self.embedding_model = "text-embedding-v4"
        
    def download_dataset(self, dataset_name, url, extract=True):
        """下载数据集"""
        logger.info(f"下载数据集: {dataset_name}")
        
        file_path = self.data_dir / f"{dataset_name}.zip"
        
        if file_path.exists():
            logger.info(f"数据集已存在: {file_path}")
            return file_path
            
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            logger.info(f"下载完成: {file_path}")
            
            if extract and file_path.suffix == '.zip':
                self.extract_dataset(file_path)
                
            return file_path
            
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return None
    
    def extract_dataset(self, zip_path):
        """解压数据集"""
        extract_dir = zip_path.with_suffix('')
        
        if extract_dir.exists():
            logger.info(f"数据集已解压: {extract_dir}")
            return extract_dir
            
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            logger.info(f"解压完成: {extract_dir}")
            return extract_dir
        except Exception as e:
            logger.error(f"解压失败: {e}")
            return None
    
    def test_squad_format(self, data_file):
        """测试SQuAD格式数据"""
        logger.info("测试SQuAD格式数据集")
        
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            results = []
            
            for article in data['data'][:5]:  # 只测试前5篇文章
                title = article['title']
                
                for paragraph in article['paragraphs'][:2]:  # 每篇文章测试2个段落
                    context = paragraph['context']
                    
                    # 创建测试文档
                    doc = self.create_test_document(context, title)
                    
                    # 处理和索引文档
                    if self.process_and_index_document(doc.id):
                        
                        # 测试问答
                        for qa in paragraph['qas'][:3]:  # 每个段落测试3个问题
                            question = qa['question']
                            expected_answers = [ans['text'] for ans in qa['answers']]
                            
                            # 执行搜索
                            search_results = self.search_documents(question)
                            
                            # 评估结果
                            result = self.evaluate_search_result(
                                question, expected_answers, search_results
                            )
                            results.append(result)
                            
                            logger.info(f"问题: {question}")
                            logger.info(f"预期答案: {expected_answers}")
                            logger.info(f"检索分数: {result['retrieval_score']:.3f}")
                            
            return results
            
        except Exception as e:
            logger.error(f"测试SQuAD数据失败: {e}")
            return []
    
    def test_dureader_format(self, data_file):
        """测试DuReader格式数据"""
        logger.info("测试DuReader格式数据集")
        
        try:
            results = []
            
            with open(data_file, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i >= 20:  # 只测试前20条
                        break
                        
                    data = json.loads(line.strip())
                    
                    question = data['question']
                    documents = data['documents']
                    
                    # 为每个文档创建记录
                    for doc_data in documents[:3]:  # 每个问题测试3个文档
                        title = doc_data.get('title', f'文档_{i}')
                        content = ' '.join(doc_data['paragraphs'])
                        
                        # 创建测试文档
                        doc = self.create_test_document(content, title)
                        
                        # 处理和索引文档
                        if self.process_and_index_document(doc.id):
                            
                            # 执行搜索
                            search_results = self.search_documents(question)
                            
                            # 评估结果
                            result = self.evaluate_search_result(
                                question, [data.get('answer', '')], search_results
                            )
                            results.append(result)
                            
                            logger.info(f"问题: {question}")
                            logger.info(f"检索分数: {result['retrieval_score']:.3f}")
                            
            return results
            
        except Exception as e:
            logger.error(f"测试DuReader数据失败: {e}")
            return []
    
    def create_test_document(self, content, title):
        """创建测试文档"""
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        import uuid
        
        doc = Document.objects.create(
            title=title,
            file_type="txt",
            description="数据集测试文档",
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
    
    def process_and_index_document(self, doc_id):
        """处理和索引文档"""
        try:
            # 处理文档
            processor = DocumentProcessor(embedding_model_version=self.embedding_model)
            if not processor.process_document(doc_id):
                return False
            
            # 索引文档
            vector_db = VectorDBService(embedding_model_version=self.embedding_model)
            doc = Document.objects.get(id=doc_id)
            return vector_db.index_document(doc)
            
        except Exception as e:
            logger.error(f"处理文档失败: {e}")
            return False
    
    def search_documents(self, query):
        """搜索文档"""
        try:
            vector_db = VectorDBService(embedding_model_version=self.embedding_model)
            return vector_db.search(query, top_k=5)
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []
    
    def evaluate_search_result(self, question, expected_answers, search_results):
        """评估搜索结果"""
        if not search_results:
            return {
                'question': question,
                'expected_answers': expected_answers,
                'retrieval_score': 0.0,
                'found_relevant': False
            }
        
        # 简单的文本匹配评估
        best_score = 0.0
        found_relevant = False
        
        for result in search_results:
            content = result['content'].lower()
            
            for answer in expected_answers:
                if answer.lower() in content:
                    found_relevant = True
                    best_score = max(best_score, result['score'])
        
        return {
            'question': question,
            'expected_answers': expected_answers,
            'retrieval_score': best_score,
            'found_relevant': found_relevant,
            'top_result_score': search_results[0]['score'] if search_results else 0.0
        }
    
    def generate_test_report(self, results, dataset_name):
        """生成测试报告"""
        logger.info(f"生成 {dataset_name} 测试报告")
        
        if not results:
            logger.warning("没有测试结果")
            return
        
        total_questions = len(results)
        relevant_found = sum(1 for r in results if r['found_relevant'])
        avg_retrieval_score = sum(r['retrieval_score'] for r in results) / total_questions
        avg_top_score = sum(r['top_result_score'] for r in results) / total_questions
        
        report = f"""
=== {dataset_name} 测试报告 ===
总问题数: {total_questions}
找到相关答案: {relevant_found} ({relevant_found/total_questions*100:.1f}%)
平均检索分数: {avg_retrieval_score:.3f}
平均Top1分数: {avg_top_score:.3f}
相关性命中率: {relevant_found/total_questions*100:.1f}%
        """
        
        logger.info(report)
        
        # 保存详细报告
        report_file = self.data_dir / f"{dataset_name}_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                'dataset': dataset_name,
                'summary': {
                    'total_questions': total_questions,
                    'relevant_found': relevant_found,
                    'hit_rate': relevant_found/total_questions,
                    'avg_retrieval_score': avg_retrieval_score,
                    'avg_top_score': avg_top_score
                },
                'detailed_results': results
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"详细报告已保存: {report_file}")


def main():
    """主函数"""
    tester = DatasetTester()
    
    # 测试数据集列表
    datasets = [
        {
            'name': 'squad_sample',
            'description': 'SQuAD 2.0 样本数据',
            'url': 'https://raw.githubusercontent.com/rajpurkar/SQuAD-explorer/master/dataset/dev-v2.0.json',
            'test_func': tester.test_squad_format
        }
        # 可以添加更多数据集
    ]
    
    logger.info("开始数据集集成测试")
    
    for dataset in datasets:
        logger.info(f"测试数据集: {dataset['description']}")
        
        # 下载数据集
        data_file = tester.download_dataset(dataset['name'], dataset['url'], False)
        
        if data_file and data_file.exists():
            # 运行测试
            results = dataset['test_func'](data_file)
            
            # 生成报告
            tester.generate_test_report(results, dataset['name'])
        else:
            logger.error(f"无法获取数据集: {dataset['name']}")
    
    logger.info("数据集测试完成")


if __name__ == "__main__":
    main()