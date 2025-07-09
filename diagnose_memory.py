import os
import sys
import django
import psutil
import logging
import time
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 设置Django环境
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smartdocs_project.settings")
django.setup()

# 导入所需模块
from documents.services.document_processor import DocumentProcessor
from documents.services.vector_db_service import VectorDBService
from documents.services.embedding_service import EmbeddingService
from documents.models import Document, DocumentChunk

def get_memory_usage():
    """获取当前进程的内存使用情况"""
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss / (1024 * 1024)  # 转换为MB

def diagnose_embedding_service():
    """测试EmbeddingService的内存使用"""
    logger.info("==== 测试EmbeddingService ====")
    mem_before = get_memory_usage()
    logger.info(f"初始内存使用: {mem_before:.2f} MB")
    
    try:
        service = EmbeddingService()
        logger.info(f"创建EmbeddingService后内存使用: {get_memory_usage():.2f} MB (增加: {get_memory_usage() - mem_before:.2f} MB)")
        
        # 测试小文本
        test_text = "这是一个测试文本，用于测试向量嵌入服务的内存使用情况"
        vector = service.get_embedding(test_text)
        logger.info(f"小文本向量化后内存使用: {get_memory_usage():.2f} MB (增加: {get_memory_usage() - mem_before:.2f} MB)")
        logger.info(f"向量维度: {len(vector)}")
        
        # 测试中等文本
        medium_text = "这是一个测试文本" * 100  # 约700字节
        vector = service.get_embedding(medium_text)
        logger.info(f"中等文本向量化后内存使用: {get_memory_usage():.2f} MB (增加: {get_memory_usage() - mem_before:.2f} MB)")
        
        # 清理
        del vector
        import gc
        gc.collect()
        logger.info(f"清理后内存使用: {get_memory_usage():.2f} MB (增加: {get_memory_usage() - mem_before:.2f} MB)")
        
    except Exception as e:
        logger.exception("测试EmbeddingService时出错")
    
    logger.info("==== EmbeddingService测试完成 ====")

def diagnose_vector_db_service():
    """测试VectorDBService的内存使用"""
    logger.info("==== 测试VectorDBService ====")
    mem_before = get_memory_usage()
    logger.info(f"初始内存使用: {mem_before:.2f} MB")
    
    try:
        service = VectorDBService()
        logger.info(f"创建VectorDBService后内存使用: {get_memory_usage():.2f} MB (增加: {get_memory_usage() - mem_before:.2f} MB)")
        
        # 创建测试向量
        import numpy as np
        test_vectors = np.random.rand(10, 1024).astype('float32')  # 10个向量，每个1024维
        logger.info(f"创建测试向量后内存使用: {get_memory_usage():.2f} MB (增加: {get_memory_usage() - mem_before:.2f} MB)")
        
        # 添加到索引
        if service.index.ntotal == 0:
            service.index.add(test_vectors)
            logger.info(f"向索引添加向量后内存使用: {get_memory_usage():.2f} MB (增加: {get_memory_usage() - mem_before:.2f} MB)")
        
        # 测试查询
        query_vector = np.random.rand(1, 1024).astype('float32')
        distances, indices = service.index.search(query_vector, 5)
        logger.info(f"查询后内存使用: {get_memory_usage():.2f} MB (增加: {get_memory_usage() - mem_before:.2f} MB)")
        
        # 清理
        del test_vectors
        del query_vector
        import gc
        gc.collect()
        logger.info(f"清理后内存使用: {get_memory_usage():.2f} MB (增加: {get_memory_usage() - mem_before:.2f} MB)")
        
    except Exception as e:
        logger.exception("测试VectorDBService时出错")
    
    logger.info("==== VectorDBService测试完成 ====")

def diagnose_document_processor():
    """测试DocumentProcessor的内存使用，但不实际处理文档"""
    logger.info("==== 测试DocumentProcessor ====")
    mem_before = get_memory_usage()
    logger.info(f"初始内存使用: {mem_before:.2f} MB")
    
    try:
        processor = DocumentProcessor()
        logger.info(f"创建DocumentProcessor后内存使用: {get_memory_usage():.2f} MB (增加: {get_memory_usage() - mem_before:.2f} MB)")
        
        # 检查数据库连接
        try:
            doc_count = Document.objects.count()
            chunk_count = DocumentChunk.objects.count()
            logger.info(f"数据库连接正常: {doc_count}个文档, {chunk_count}个文档块")
        except Exception as e:
            logger.error(f"数据库连接出错: {str(e)}")
        
        # 清理
        import gc
        gc.collect()
        logger.info(f"清理后内存使用: {get_memory_usage():.2f} MB (增加: {get_memory_usage() - mem_before:.2f} MB)")
        
    except Exception as e:
        logger.exception("测试DocumentProcessor时出错")
    
    logger.info("==== DocumentProcessor测试完成 ====")

if __name__ == "__main__":
    logger.info("开始内存诊断...")
    
    # 诊断各组件
    diagnose_embedding_service()
    time.sleep(1)  # 暂停一下，以便观察
    
    diagnose_vector_db_service()
    time.sleep(1)
    
    diagnose_document_processor()
    
    logger.info(f"诊断完成，最终内存使用: {get_memory_usage():.2f} MB")