import gc
import threading
import time
from typing import List, Self

from django.conf import settings
from django.db.models import F
from pgvector.django import VectorField
from loguru import logger

from common.utils.cache_utils import RedisCache, cached
from qa.schemas.retrieval import DocumentSearchResultOut

from ..models import Document, DocumentChunk
from .embedding_factory import get_embedding_service


class VectorDBService:
    """向量数据库服务，使用PostgreSQL+pgvector存储和检索文档向量"""

    # 单例模式相关变量（使用字典存储不同模型版本的实例）
    _instances = {}
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls, embedding_model_version=None) -> Self:
        """
        获取单例实例，确保相同嵌入模型版本只有一个实例

        Args:
            embedding_model_version: 嵌入模型版本，如果未指定则使用settings中的配置

        Returns:
            VectorDBService: 单例实例
        """
        # 规范化模型版本，确保None使用默认值
        model_version = embedding_model_version or settings.EMBEDDING_MODEL_VERSION

        # 使用锁保证线程安全
        with cls._instance_lock:
            # 如果该模型版本的实例不存在，则创建
            if model_version not in cls._instances:
                logger.info(f"创建新的VectorDBService实例 (模型版本: {model_version})")
                cls._instances[model_version] = super(VectorDBService, cls).__new__(cls)
                cls._instances[model_version]._initialized = False

            instance = cls._instances[model_version]

            # 如果该实例尚未初始化，调用初始化方法
            if not getattr(instance, "_initialized", False):
                instance._init(model_version)
                instance._initialized = True

            return instance

    def __new__(cls, embedding_model_version=None):
        """
        重写__new__方法，确保直接实例化也使用单例模式

        Args:
            embedding_model_version: 嵌入模型版本

        Returns:
            VectorDBService: 单例实例
        """
        return cls.get_instance(embedding_model_version)

    def _init(self, embedding_model_version=None):
        """
        真正的初始化方法，由单例模式控制调用

        Args:
            embedding_model_version: 嵌入模型版本
        """
        # 记录使用的嵌入模型版本
        self.embedding_model_version = embedding_model_version or settings.EMBEDDING_MODEL_VERSION
        logger.info(f"初始化VectorDBService，使用嵌入模型: {self.embedding_model_version}")

        # 使用工厂函数初始化嵌入服务，传递模型版本
        self.embedding_service = get_embedding_service(embedding_model_version=self.embedding_model_version)

        # 从嵌入服务获取实际向量维度
        self.vector_dim = self.embedding_service.vector_dim
        logger.info(f"使用向量维度: {self.vector_dim} (来自嵌入服务的实际维度)")

    def index_document(self, document: Document) -> bool:
        """将文档索引到向量数据库（pgvector）"""
        try:
            # 检查文档状态
            if document.status == "failed":
                logger.warning(f"文档{document.id}状态为failed，跳过索引")
                return False

            # 获取文档分块
            chunks = DocumentChunk.objects.filter(document_id=document.id)

            if not chunks.exists():
                logger.warning(f"文档{document.id}没有分块，无法索引")
                return False

            # 分批处理文档块以减少内存使用
            batch_size = 10
            total_vectors = 0

            for i in range(0, chunks.count(), batch_size):
                batch_chunks = list(chunks[i : i + batch_size])
                vectors_data = []

                # 处理每个文档块
                for chunk in batch_chunks:
                    try:
                        # 获取块文本向量
                        vector = self.embedding_service.get_embedding(chunk.content)
                        vectors_data.append((chunk.id, vector))
                    except Exception as e:
                        logger.error(f"处理文档块{chunk.id}时出错: {str(e)}")

                if not vectors_data:
                    continue

                # 批量更新向量到数据库
                for chunk_id, vector in vectors_data:
                    try:
                        chunk = DocumentChunk.objects.get(id=chunk_id)
                        chunk.embedding = vector
                        chunk.save(update_fields=["embedding"])
                    except DocumentChunk.DoesNotExist:
                        logger.error(f"文档块{chunk_id}不存在")
                    except Exception as e:
                        logger.error(f"保存向量到数据库失败: {str(e)}")

                total_vectors += len(vectors_data)

                # 每处理一批次，进行垃圾回收
                gc.collect()

                logger.info(f"已处理{min(i + batch_size, chunks.count())}/{chunks.count()}个文档块")

            # 清除查询缓存
            self.clear_search_cache()

            logger.info(f"文档{document.id}的{total_vectors}个向量已成功索引")
            return True

        except Exception as e:
            logger.exception(f"索引文档{document.id}失败: {str(e)}")
            return False

    def search(self, query: str, top_k: int = 5) -> List[DocumentSearchResultOut]:
        """根据查询文本搜索相关文档块（使用pgvector）"""
        try:
            # 检查是否有索引向量
            indexed_count = DocumentChunk.objects.filter(embedding__isnull=False).count()
            if indexed_count == 0:
                logger.warning("向量索引为空，无法进行搜索")
                return []

            # 将查询文本转换为向量
            query_vector = self.embedding_service.get_embedding(query)

            # 使用pgvector的<=>操作符进行向量相似度搜索
            # 直接使用Django ORM的 __isnull 过滤和原生查询
            from django.db.models import Case, When, Value, FloatField
            from pgvector.django import CosineDistance

            # 使用余弦距离搜索
            results_qs = (
                DocumentChunk.objects
                .filter(embedding__isnull=False)
                .annotate(distance=CosineDistance("embedding", query_vector))
                .order_by("distance")[:top_k]
            )

            # 获取检索结果
            results = []
            version_mismatch_count = 0

            for chunk in results_qs:
                try:
                    # 检查关联的文档
                    document = Document.objects.get(id=chunk.document_id)

                    # 如果文档已被删除，跳过
                    if document.is_deleted:
                        continue

                    # 如果文档使用的嵌入模型与当前不同，记录并跳过
                    if document.embedding_model_version != self.embedding_model_version:
                        version_mismatch_count += 1
                        continue

                    # 构建完整的内容：包含标题上下文
                    full_content = chunk.content
                    if chunk.section_path:
                        full_content = f"[{chunk.section_path}]\n\n{full_content}"

                    # 计算相似度分数（pgvector返回的是距离，需要转换为相似度）
                    # 余弦距离范围是 0-2，转换为相似度 1-0
                    similarity_score = 1 - (chunk.distance / 2)

                    results.append(
                        DocumentSearchResultOut(
                            id=document.id,
                            title=document.title,
                            content=full_content,
                            score=float(similarity_score),
                            chunk_index=chunk.chunk_index,
                            embedding_model_version=document.embedding_model_version,
                            rerank_score=None,
                            final_score=None,
                            rerank_method=None,
                        )
                    )
                except (DocumentChunk.DoesNotExist, Document.DoesNotExist):
                    continue

            if version_mismatch_count > 0:
                logger.warning(f"跳过了{version_mismatch_count}个模型版本不匹配的文档块")

            logger.info(f"检索完成，返回{len(results)}个结果")
            return results

        except Exception as e:
            logger.exception(f"搜索失败: {str(e)}")
            return []

    @cached(prefix="vector_search", timeout=60 * 60)
    @staticmethod
    def search_static(query: str, top_k: int = 5, embedding_model_version=None) -> List[DocumentSearchResultOut]:
        """
        静态方法版本的搜索，方便缓存和共享

        Args:
            query: 查询文本
            top_k: 返回结果数量
            embedding_model_version: 嵌入模型版本

        Returns:
            检索结果列表
        """
        instance = VectorDBService.get_instance(embedding_model_version=embedding_model_version)
        return instance.search(query, top_k)

    @staticmethod
    def clear_search_cache():
        """清除所有向量搜索缓存"""
        pattern = "smartdocs:cache:vector_search:*"
        count = RedisCache.clear_pattern(pattern)

        if count:
            logger.info(f"已清除{count}个向量搜索缓存")

        return count
