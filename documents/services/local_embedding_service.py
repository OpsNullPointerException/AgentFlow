import numpy as np
from loguru import logger
from typing import Optional
import os
from django.conf import settings


class LocalEmbeddingService:
    """本地向量嵌入服务，使用sentence-transformers而不依赖外部API"""

    def __init__(self, embedding_model_version: Optional[str] = None):
        """
        初始化本地向量嵌入服务

        Args:
            embedding_model_version: 嵌入模型版本，如果未指定则使用settings中的配置
        """
        # 检查是否使用了API模型名称
        api_models = ["text-embedding-ada-002", "text-embedding-3-small", "text-embedding-3-large", "text-embedding-v4"]
        default_local_model = settings.LOCAL_EMBEDDING_MODEL

        # 如果是API模型，自动替换为默认本地模型
        if embedding_model_version in api_models:
            logger.warning(f"检测到API模型名称: {embedding_model_version}, 自动替换为本地模型: {default_local_model}")
            self.embedding_model_version = default_local_model
        else:
            self.embedding_model_version = embedding_model_version or default_local_model

        # 设置向量维度 (根据选择的模型来定)
        self.model_dimensions = {
            "all-MiniLM-L6-v2": 384,
            "paraphrase-multilingual-MiniLM-L12-v2": 384,
            "all-mpnet-base-v2": 768,
            "BAAI/bge-small-zh-v1.5": 384,
            "BAAI/bge-base-zh-v1.5": 768,
            "BAAI/bge-large-zh-v1.5": 1024,
            "text-embedding-ada-002": 1536,  # 兼容性设置
        }

        self.vector_dim = self.model_dimensions.get(self.embedding_model_version, settings.EMBEDDING_MODEL_DIMENSIONS)

        logger.info(
            f"初始化本地EmbeddingService，使用模型: {self.embedding_model_version}，向量维度: {self.vector_dim}"
        )

        # 延迟导入sentence_transformers，避免依赖未安装时的导入错误
        try:
            from sentence_transformers import SentenceTransformer

            self.SentenceTransformer = SentenceTransformer

            # 加载模型
            self._load_model()
        except ImportError:
            logger.error("sentence-transformers未安装，请运行: pip install sentence-transformers")
            self.model = None

    def _load_model(self):
        """加载嵌入模型，优先使用本地缓存"""
        try:
            # 检查模型缓存目录
            os_cache_dir = os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
            logger.info(f"模型将缓存到: {os_cache_dir}")

            # 首先尝试仅使用本地文件加载模型
            logger.info(f"尝试从本地缓存加载模型: {self.embedding_model_version}")
            try:
                self.model = self.SentenceTransformer(
                    self.embedding_model_version,
                    local_files_only=True,  # 只使用本地缓存
                )
                logger.info("成功从本地缓存加载模型")
            except Exception as local_err:
                # 本地加载失败，尝试联网加载
                logger.warning(f"从本地加载模型失败: {str(local_err)}，尝试联网下载...")
                self.model = self.SentenceTransformer(
                    self.embedding_model_version,
                    cache_folder=os_cache_dir,  # 指定缓存目录
                )
                logger.info("成功通过网络下载并加载模型")

            logger.info(f"模型加载成功，实际向量维度: {self.model.get_sentence_embedding_dimension()}")

            # 更新向量维度为模型的实际维度
            self.vector_dim = self.model.get_sentence_embedding_dimension()
        except Exception as e:
            logger.exception(f"加载模型时出错: {str(e)}")
            self.model = None
            raise RuntimeError(f"无法加载嵌入模型: {str(e)}")

    def get_embedding(self, text: str) -> np.ndarray:
        """
        获取文本的向量表示

        Args:
            text: 输入文本

        Returns:
            文本的向量表示
        """
        if not self.model:
            # 如果模型未加载成功，返回随机向量
            logger.warning("模型未加载，返回随机向量（仅用于测试）")
            return np.random.rand(self.vector_dim).astype("float32")

        try:
            # 使用本地模型生成嵌入
            start_text = text[:100] + "..." if len(text) > 100 else text
            logger.info(f"生成文本嵌入，文本开头: {start_text}")

            # 使用sentence-transformers生成嵌入
            embedding = self.model.encode(text, normalize_embeddings=True)

            # 确保类型为float32
            embedding = np.array(embedding).astype("float32")

            logger.info(f"成功生成嵌入，维度: {len(embedding)}")
            return embedding

        except Exception as e:
            logger.exception(f"生成嵌入向量时出错: {str(e)}")
            # 错误时返回随机向量
            return np.random.rand(self.vector_dim).astype("float32")
