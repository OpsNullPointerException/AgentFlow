import os
import numpy as np
import faiss
from typing import List, Dict, Any, Optional
from loguru import logger
from django.conf import settings
import pickle
import zlib  # 添加zlib用于压缩和解压缩数据
from pathlib import Path
import gc  # 添加垃圾回收模块
import threading
import time
import hashlib

from ..models import Document, DocumentChunk
# 替换直接导入为使用工厂函数
from .embedding_factory import get_embedding_service
from common.utils.cache_utils import RedisCache, cached

# loguru不需要getLogger


class VectorDBService:
    """向量数据库服务，用于存储和检索文档向量"""

    # 单例模式相关变量（使用字典存储不同模型版本的实例）
    _instances = {}
    _instance_lock = threading.Lock()
    _initialized_lock = threading.Lock()
    _is_initialized = {}  # 使用字典跟踪每个模型版本是否已预加载
    
    # Redis键前缀
    REDIS_META_KEY = "smartdocs:faiss:meta:{}"  # 用于存储元数据
    REDIS_UPDATE_FLAG_KEY = "smartdocs:faiss:updated:{}"  # 用于标记索引更新
    REDIS_EXPIRY = 60 * 60 * 24 * 7  # 7天过期

    @classmethod
    def get_instance(cls, embedding_model_version=None):
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
            if not getattr(instance, '_initialized', False):
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
        self.embedding_model_version = embedding_model_version
        logger.info(f"初始化VectorDBService，使用嵌入模型: {self.embedding_model_version}")

        # 调用真正的初始化方法
        self._init(embedding_model_version)
        self._initialized = True
    
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

        # 从嵌入服务获取实际向量维度，而不是使用配置中的固定值
        self.vector_dim = self.embedding_service.vector_dim  # 使用嵌入服务的实际向量维度
        logger.info(f"使用向量维度: {self.vector_dim} (来自嵌入服务的实际维度)")
        
        self.vector_store_path = settings.VECTOR_STORE_PATH
        self.index_file = os.path.join(self.vector_store_path, "faiss_index.bin")
        self.mapping_file = os.path.join(self.vector_store_path, "chunk_mapping.pkl")

        # 确保向量库目录存在
        Path(self.vector_store_path).mkdir(parents=True, exist_ok=True)

        # 初始化或加载索引
        self._init_index()

    def _get_redis_key(self, key_template):
        """获取带版本号的Redis键"""
        # 生成安全的版本名，替换不适合作为键的字符
        safe_version = self.embedding_model_version.replace('/', '_').replace('-', '_')
        return key_template.format(safe_version)
    
    def _mark_index_updated_in_redis(self) -> bool:
        """
        在Redis中标记索引已更新，存储索引元数据和文件修改时间
        
        Returns:
            bool: 是否成功标记
        """
        try:
            # 获取Redis客户端连接
            from common.utils.cache_utils import RedisCache
            
            # 获取索引文件的修改时间
            index_mtime = 0
            mapping_mtime = 0
            
            if os.path.exists(self.index_file):
                index_mtime = os.path.getmtime(self.index_file)
            if os.path.exists(self.mapping_file):
                mapping_mtime = os.path.getmtime(self.mapping_file)
            
            # 创建元数据
            meta_data = {
                "vector_count": self.index.ntotal,
                "embedding_model_version": self.embedding_model_version,
                "timestamp": time.time(),
                "index_mtime": index_mtime,
                "mapping_mtime": mapping_mtime,
                "vector_dim": self.vector_dim,
                "file_path": self.index_file,
                "mapping_file": self.mapping_file
            }
            meta_bytes = pickle.dumps(meta_data)
            
            # 保存元数据和更新标记到Redis
            meta_key = self._get_redis_key(self.REDIS_META_KEY)
            update_flag_key = self._get_redis_key(self.REDIS_UPDATE_FLAG_KEY)
            
            RedisCache.set(meta_key, meta_bytes, self.REDIS_EXPIRY)
            RedisCache.set(update_flag_key, str(time.time()), self.REDIS_EXPIRY)
            
            logger.info(
                f"索引更新已标记到Redis (模型版本: {self.embedding_model_version})，"
                f"包含{self.index.ntotal}个向量"
            )
            return True
        except Exception as e:
            logger.error(f"标记索引更新到Redis失败: {str(e)}")
            return False
    
    def _check_index_updated_in_redis(self) -> bool:
        """
        检查Redis中是否有索引更新标记，以及本地文件是否需要更新
        
        Returns:
            bool: 是否有更新
        """
        try:
            # 获取Redis客户端
            from common.utils.cache_utils import RedisCache
            
            # 获取元数据
            meta_key = self._get_redis_key(self.REDIS_META_KEY)
            meta_bytes = RedisCache.get(meta_key)
            
            if not meta_bytes:
                return False
                
            try:
                meta_data = pickle.loads(meta_bytes)
                redis_index_mtime = meta_data.get('index_mtime', 0)
                redis_mapping_mtime = meta_data.get('mapping_mtime', 0)
                
                # 检查本地文件是否存在
                if not os.path.exists(self.index_file) or not os.path.exists(self.mapping_file):
                    return False
                
                # 检查本地文件的修改时间是否与Redis中的匹配
                local_index_mtime = os.path.getmtime(self.index_file)
                local_mapping_mtime = os.path.getmtime(self.mapping_file)
                
                # 如果Redis中记录的时间比本地文件更新，则表示有其他进程更新了文件
                if redis_index_mtime > local_index_mtime or redis_mapping_mtime > local_mapping_mtime:
                    logger.info(
                        f"检测到索引文件有更新 (模型版本: {self.embedding_model_version})，"
                        f"Redis记录时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(redis_index_mtime))}，"
                        f"本地文件时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(local_index_mtime))}"
                    )
                    return True
                    
            except Exception as e:
                logger.error(f"解析索引元数据失败: {str(e)}")
                
            return False
        except Exception as e:
            logger.error(f"检查索引更新失败: {str(e)}")
            return False

    def _init_index(self) -> None:
        """初始化FAISS索引，使用Redis更新标记来检测文件变化"""
        # 1. 检查是否有其他进程更新了索引文件
        if self._check_index_updated_in_redis():
            logger.info("检测到其他进程更新了索引文件，将重新加载")
            
        # 2. 尝试从文件加载
        if os.path.exists(self.index_file) and os.path.exists(self.mapping_file):
            # 加载现有索引
            try:
                logger.info(f"从文件加载FAISS索引: {self.index_file}")
                self.index = faiss.read_index(self.index_file)
                with open(self.mapping_file, "rb") as f:
                    self.chunk_mapping = pickle.load(f)
                logger.info(f"已加载现有FAISS索引，包含{self.index.ntotal}个向量")
                
                # 更新Redis中的标记
                self._mark_index_updated_in_redis()
            except Exception as e:
                logger.error(f"加载索引失败: {str(e)}，将创建新索引")
                self._create_new_index()
        else:
            # 3. 创建新索引
            self._create_new_index()

    def _create_new_index(self) -> None:
        """创建新的FAISS索引"""
        # 使用内积索引，效率更高，且内存占用更小
        # 对于更大规模应用，可以考虑使用HNSW或IVF索引
        self.index = faiss.IndexFlatIP(self.vector_dim)
        self.chunk_mapping = {}  # 存储向量ID到文档块ID的映射
        logger.info("已创建新的FAISS索引")

    def _save_index(self) -> None:
        """保存索引到文件和更新Redis标记"""
        try:
            # 保存到文件
            faiss.write_index(self.index, self.index_file)
            with open(self.mapping_file, "wb") as f:
                pickle.dump(self.chunk_mapping, f)
            logger.info(f"FAISS索引已保存到文件，包含{self.index.ntotal}个向量")
            
            # 更新Redis中的标记
            self._mark_index_updated_in_redis()
        except Exception as e:
            logger.error(f"保存索引失败: {str(e)}")

    def index_document(self, document: Document) -> bool:
        """将文档索引到向量数据库"""
        try:
            # 检查文档状态
            if document.status == "failed":
                logger.warning(f"文档{document.id}状态为failed，跳过索引")
                return False

            # 获取文档分块
            chunks = DocumentChunk.objects.filter(document_id=document.id)

            if not chunks:
                logger.warning(f"文档{document.id}没有分块，无法索引")
                return False

            # 获取分块文本向量，分批处理以减少内存使用
            start_idx = self.index.ntotal
            batch_size = 10  # 每批处理的块数量，调整此值可以平衡内存使用和处理效率
            total_vectors = 0

            # 分批处理文档块
            for i in range(0, chunks.count(), batch_size):
                # 获取当前批次的文档块
                batch_chunks = chunks[i : i + batch_size]
                vectors = []
                chunk_ids = []

                # 处理每个文档块
                for chunk in batch_chunks:
                    try:
                        # 获取块文本向量
                        vector = self.embedding_service.get_embedding(chunk.content)
                        vectors.append(vector)
                        chunk_ids.append(chunk.id)
                    except Exception as e:
                        logger.error(f"处理文档块{chunk.id}时出错: {str(e)}")

                if not vectors:
                    continue

                # 将向量转换为NumPy数组
                vectors_array = np.array(vectors).astype("float32")

                # 归一化向量以提高检索质量
                faiss.normalize_L2(vectors_array)

                # 添加到FAISS索引
                self.index.add(vectors_array)
                batch_start_idx = start_idx + total_vectors

                # 更新映射并保存向量ID到数据库
                for j, chunk_id in enumerate(chunk_ids):
                    vector_idx = batch_start_idx + j
                    self.chunk_mapping[vector_idx] = chunk_id

                    # 保存向量ID到数据库
                    try:
                        # 检查batch_chunks的类型并相应处理
                        if hasattr(batch_chunks, "get"):
                            # 如果是QuerySet，使用get方法
                            chunk = batch_chunks.get(id=chunk_id)
                        else:
                            # 如果是列表或元组，使用循环查找
                            chunk = None
                            for c in batch_chunks:
                                if c.id == chunk_id:
                                    chunk = c
                                    break
                        
                        if chunk:
                            # 更新文档块的向量ID
                            chunk.vector_id = vector_idx
                            chunk.save()
                    except Exception as e:
                        logger.error(f"保存向量ID到数据库失败: {str(e)}")

                total_vectors += len(vectors)

                # 释放内存
                del vectors
                del vectors_array

                # 每处理一批次，进行垃圾回收
                gc.collect()

                # 回收内存
                del batch_chunks

            # 保存索引（同时会标记Redis更新）
            self._save_index()
            
            # 清除查询缓存，因为新的文档可能会影响搜索结果
            self.clear_search_cache()

            logger.info(f"文档{document.id}的{total_vectors}个向量已成功索引，缓存已清除")
            return True

        except Exception as e:
            logger.exception(f"索引文档{document.id}失败: {str(e)}")
            return False

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """根据查询文本搜索相关文档块"""
        try:
            # 检查索引是否为空
            if self.index.ntotal == 0:
                logger.warning("向量索引为空，无法进行搜索")
                return []

            # 将查询文本转换为向量并归一化
            query_vector = self.embedding_service.get_embedding(query)
            query_vector = np.array([query_vector]).astype("float32")  # 转换为2D数组
            faiss.normalize_L2(query_vector)  # 归一化查询向量

            # 在向量数据库中检索最相似的向量
            distances, indices = self.index.search(query_vector, min(top_k, self.index.ntotal))

            # 获取检索结果
            results = []
            version_mismatch_count = 0  # 跟踪模型版本不匹配的块数量

            for i, idx in enumerate(indices[0]):  # indices是二维数组，取第一个结果
                if idx < 0:  # faiss在结果不足时会返回-1
                    continue

                chunk_id = self.chunk_mapping.get(int(idx))
                if chunk_id is None:
                    continue

                try:
                    # 不使用select_related，因为document_id是整数字段而非关系字段
                    chunk = DocumentChunk.objects.get(id=chunk_id)

                    # 检查嵌入模型版本是否匹配
                    document = Document.objects.get(id=chunk.document_id)
                    
                    # 如果文档使用的嵌入模型与当前不同，记录并跳过
                    if document.embedding_model_version != self.embedding_model_version:
                        version_mismatch_count += 1
                        continue

                    results.append({
                        "id": document.id,
                        "title": document.title,
                        "content": chunk.content,
                        "score": float(distances[0][i]),  # 转换numpy.float32为Python float
                        "chunk_index": chunk.chunk_index,
                        "embedding_model_version": document.embedding_model_version,
                    })
                except (DocumentChunk.DoesNotExist, Document.DoesNotExist):
                    # 如果文档块或文档不存在，跳过
                    continue

            if version_mismatch_count > 0:
                logger.warning(f"跳过了{version_mismatch_count}个模型版本不匹配的文档块")

            # 按相似度分数排序
            results = sorted(results, key=lambda x: x["score"], reverse=True)
            return results
        except Exception as e:
            logger.exception(f"搜索失败: {str(e)}")
            return []

    @cached(prefix="vector_search", timeout=60*60)  # 缓存1小时
    @staticmethod
    def search_static(query: str, top_k: int = 5, embedding_model_version=None) -> List[Dict[str, Any]]:
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
        from common.utils.cache_utils import RedisCache
        
        pattern = "smartdocs:cache:vector_search:*"
        count = RedisCache.clear_pattern(pattern)
        
        if count:
            logger.info(f"已清除{count}个向量搜索缓存")
        
        return count

    @staticmethod
    def preload_index_async(embedding_model_version=None):
        """
        异步预加载索引，避免阻塞Django启动进程
        
        Args:
            embedding_model_version: 要预加载的嵌入模型版本
        """
        import threading
        
        def _preload_in_thread(model_version):
            try:
                logger.info(f"开始异步预加载索引 (模型版本: {model_version})...")
                # 使用单例方法获取实例，而不是直接实例化
                instance = VectorDBService.get_instance(embedding_model_version=model_version)
                logger.info(f"索引异步预加载完成 (模型版本: {model_version})")
            except Exception as e:
                logger.error(f"索引异步预加载失败: {str(e)}")
        
        # 使用线程异步加载
        thread = threading.Thread(
            target=_preload_in_thread,
            args=(embedding_model_version,),
            daemon=True  # 设置为守护线程，避免阻止程序退出
        )
        thread.start()
        
        return thread  # 返回线程对象，便于测试和管理
