#!/usr/bin/env python
"""
测试文档处理到搜索的完整流程
这个脚本会创建测试文档，处理文档，进行向量索引，然后执行搜索
每一步都会输出详细日志，以验证流程是否正常
"""

import os
import sys
import tempfile
from loguru import logger
import uuid
import time
from pathlib import Path

# 将项目根目录添加到系统路径
current_path = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_path)  # 获取项目根目录
sys.path.insert(0, project_root)  # 使用insert而不是append，确保优先查找
print(f"Added project root to sys.path: {project_root}")
print(f"Current sys.path: {sys.path}")

# 检查目录结构
documents_dir = os.path.join(project_root, "documents")
services_dir = os.path.join(documents_dir, "services")
print(f"Documents directory exists: {os.path.exists(documents_dir)}")
print(f"Services directory exists: {os.path.exists(services_dir)}")
print(f"document_processor.py exists: {os.path.exists(os.path.join(services_dir, 'document_processor.py'))}")

# 设置Django环境
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smartdocs_project.settings")
django.setup()

# 导入需要的模块
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

# 导入模型和服务
try:
    from documents.models import Document, DocumentChunk
    print("成功导入Document和DocumentChunk模型")
    
    from documents.services.document_processor import DocumentProcessor
    print("成功导入DocumentProcessor")
    
    from documents.services.vector_db_service import VectorDBService
    print("成功导入VectorDBService")
    
    from documents.services.embedding_service import EmbeddingService
    print("成功导入EmbeddingService")
except ImportError as e:
    print(f"导入错误: {e}")
    
    # 尝试直接加载模块
    import importlib.util
    
    def load_module(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        if spec:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        return None
    
    # 尝试直接加载必要的模块
    doc_processor_path = os.path.join(services_dir, "document_processor.py")
    vector_db_path = os.path.join(services_dir, "vector_db_service.py")
    embedding_path = os.path.join(services_dir, "embedding_service.py")
    
    try:
        # 手动导入模块
        document_processor_module = load_module("document_processor", doc_processor_path)
        vector_db_module = load_module("vector_db_service", vector_db_path)
        embedding_module = load_module("embedding_service", embedding_path)
        
        if document_processor_module:
            DocumentProcessor = document_processor_module.DocumentProcessor
            print("手动加载DocumentProcessor成功")
        
        if vector_db_module:
            VectorDBService = vector_db_module.VectorDBService
            print("手动加载VectorDBService成功")
        
        if embedding_module:
            EmbeddingService = embedding_module.EmbeddingService
            print("手动加载EmbeddingService成功")
    except Exception as e:
        print(f"手动导入失败: {e}")
        sys.exit(1)

# 设置日志
# logging.basicConfig(
#     level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# )
# loguru不需要getLogger

# 测试配置
TEST_USER_ID = 1  # 使用ID为1的用户
TEST_EMBEDDING_MODEL = "text-embedding-v4"  # 使用的嵌入模型版本


def create_test_document(content, title="测试文档", file_type="txt"):
    """创建测试文档记录和文件"""
    logger.info("步骤1: 创建测试文档")

    # 创建文档记录
    doc = Document.objects.create(
        title=title,
        file_type=file_type,
        description="测试文档描述",
        owner_id=TEST_USER_ID,
        status="pending",
    )

    # 创建临时文件
    file_name = f"{uuid.uuid4()}.{file_type}"
    file_path = f"documents/{TEST_USER_ID}/{file_name}"

    # 保存文件内容
    logger.info(f"创建文件: {file_path}")
    default_storage.save(file_path, ContentFile(content.encode("utf-8")))

    # 更新文档记录中的文件路径
    doc.file = file_path
    doc.save()

    logger.info(f"文档创建成功: ID={doc.id}, 标题='{doc.title}'")
    return doc


def process_document(doc_id):
    """处理文档(提取文本并分块)"""
    logger.info(f"步骤2: 处理文档 (ID={doc_id})")

    # 使用DocumentProcessor处理文档
    processor = DocumentProcessor(embedding_model_version=TEST_EMBEDDING_MODEL)

    # 记录处理开始时间
    start_time = time.time()

    # 处理文档
    success = processor.process_document(doc_id)

    # 计算处理时间
    process_time = time.time() - start_time

    if success:
        logger.info(f"文档处理成功，耗时: {process_time:.2f}秒")

        # 查询生成了多少个文档块
        chunks = DocumentChunk.objects.filter(document_id=doc_id)
        logger.info(f"生成了{chunks.count()}个文档块")

        # 检查块内容和嵌入模型版本
        for i, chunk in enumerate(chunks):
            logger.info(
                f"块{i + 1}: 长度={len(chunk.content)}字符, "
                f"模型版本={chunk.embedding_model_version}"
            )
            if i == 0:  # 只打印第一个块的部分内容
                preview = chunk.content[:100] + ("..." if len(chunk.content) > 100 else "")
                logger.info(f"块内容预览: '{preview}'")
    else:
        logger.error("文档处理失败")

    return success


def index_document(doc_id):
    """将文档索引到向量数据库"""
    logger.info(f"步骤3: 索引文档 (ID={doc_id})")

    # 使用VectorDBService索引文档
    vector_db = VectorDBService(embedding_model_version=TEST_EMBEDDING_MODEL)

    # 获取文档
    doc = Document.objects.get(id=doc_id)

    # 记录索引开始时间
    start_time = time.time()

    # 索引文档
    success = vector_db.index_document(doc)

    # 计算索引时间
    index_time = time.time() - start_time

    if success:
        logger.info(f"文档索引成功，耗时: {index_time:.2f}秒")
        logger.info(f"当前索引包含{vector_db.index.ntotal}个向量")

        # 检查映射大小
        logger.info(f"chunk_mapping包含{len(vector_db.chunk_mapping)}个映射条目")

        # 检查向量ID是否保存到数据库
        chunks_with_vector_id = DocumentChunk.objects.filter(
            document_id=doc_id, vector_id__isnull=False
        ).count()
        logger.info(f"有{chunks_with_vector_id}个文档块保存了向量ID")
    else:
        logger.error("文档索引失败")

    return success


def search_documents(query):
    """搜索相关文档"""
    logger.info(f"步骤4: 搜索相关文档 (查询='{query}')")

    # 使用VectorDBService搜索
    vector_db = VectorDBService(embedding_model_version=TEST_EMBEDDING_MODEL)

    # 记录搜索开始时间
    start_time = time.time()

    # 执行搜索
    results = vector_db.search(query, top_k=5)

    # 计算搜索时间
    search_time = time.time() - start_time

    logger.info(f"搜索完成，耗时: {search_time:.2f}秒，找到{len(results)}个结果")

    # 显示搜索结果
    for i, result in enumerate(results):
        logger.info(
            f"结果{i + 1}: 文档='{result['title']}', "
            f"相关性分数={result['score']:.4f}, "
            f"模型版本={result['embedding_model_version']}"
        )

        # 显示内容预览
        content_preview = result["content"][:100] + ("..." if len(result["content"]) > 100 else "")
        logger.info(f"内容预览: '{content_preview}'")

    return results


def verify_mapping_persistence():
    """验证映射持久化是否正常"""
    logger.info("步骤5: 验证映射持久化")

    # 检查映射文件是否存在
    from django.conf import settings

    mapping_file = os.path.join(settings.VECTOR_STORE_PATH, "chunk_mapping.pkl")

    if os.path.exists(mapping_file):
        file_size = os.path.getsize(mapping_file)
        logger.info(f"映射文件存在: {mapping_file}, 大小: {file_size / 1024:.2f} KB")

        # 创建一个新的VectorDBService实例，验证是否能加载映射
        new_vector_db = VectorDBService()
        logger.info(f"重新加载的chunk_mapping包含{len(new_vector_db.chunk_mapping)}个映射条目")

        return True
    else:
        logger.error(f"映射文件不存在: {mapping_file}")
        return False


def run_full_test():
    """运行完整流程测试"""
    logger.info("=== 开始测试文档处理到搜索的完整流程 ===")
    logger.info(f"使用嵌入模型: {TEST_EMBEDDING_MODEL}")

    # 1. 创建测试文档
    test_content = """
    SmartDocs是一个企业级文档智能问答系统，它可以帮助企业快速构建基于自有文档的智能客服和知识库。
    系统使用先进的大语言模型技术，结合检索增强生成(RAG)方法，可以准确理解用户问题并给出精准答案。
    主要功能包括：文档上传和管理、文本提取和向量化、语义检索、上下文理解和多轮对话。
    系统支持PDF、Word、TXT等多种文档格式，并提供用户友好的Web界面。
    """

    doc = create_test_document(test_content, title="SmartDocs简介")

    # 2. 处理文档
    if process_document(doc.id):
        # 3. 索引文档
        if index_document(doc.id):
            # 4. 搜索文档
            search_results = search_documents("智能问答系统的主要功能是什么")

            # 5. 验证映射持久化
            verify_mapping_persistence()

    logger.info("=== 测试完成 ===")


if __name__ == "__main__":
    run_full_test()
