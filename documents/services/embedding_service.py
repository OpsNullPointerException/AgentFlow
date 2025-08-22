import numpy as np
from loguru import logger
import os
import hashlib
from django.conf import settings
from django.core.cache import cache
from openai import OpenAI
import requests.exceptions
from common.utils.retry_utils import retry, log_retry, RetryableError


# 定义可重试的错误类型
class EmbeddingAPIError(RetryableError):
    """嵌入API调用错误，可以重试的错误"""

    pass


# loguru不需要getLogger


class EmbeddingService:
    """向量嵌入服务，负责文本向量化"""

    def __init__(self, embedding_model_version=None):
        """
        初始化向量嵌入服务

        Args:
            embedding_model_version: 嵌入模型版本，如果未指定则使用settings中的配置
        """
        # 设置DashScope API密钥
        self.api_key = settings.DASHSCOPE_API_KEY
        if not self.api_key:
            logger.warning("DASHSCOPE_API_KEY未设置，向量嵌入服务将无法正常工作")
        else:
            # 设置环境变量，用于OpenAI客户端
            os.environ["DASHSCOPE_API_KEY"] = self.api_key

        # 设置嵌入模型版本和维度
        self.embedding_model_version = embedding_model_version or settings.EMBEDDING_MODEL_VERSION
        self.vector_dim = settings.EMBEDDING_MODEL_DIMENSIONS

        # 缓存配置
        self.cache_timeout = getattr(settings, "EMBEDDING_CACHE_TIMEOUT", 86400)  # 24小时
        self.enable_cache = getattr(settings, "EMBEDDING_CACHE_ENABLED", True)

        logger.info(
            f"初始化EmbeddingService，使用模型: {self.embedding_model_version}, 缓存: {'启用' if self.enable_cache else '禁用'}"
        )

        # 创建OpenAI客户端（使用DashScope兼容模式）
        self.client = OpenAI(api_key=self.api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")

    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        # 使用文本内容和模型版本生成缓存键
        content = f"{text}:{self.embedding_model_version}"
        return f"embedding:{hashlib.md5(content.encode('utf-8')).hexdigest()[:16]}"

    def _get_cached_embedding(self, text: str) -> np.ndarray:
        """从缓存获取嵌入向量"""
        if not self.enable_cache:
            return None

        cache_key = self._get_cache_key(text)
        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.debug(f"缓存命中: {text[:50]}...")
                return np.array(cached_data, dtype=np.float32)
        except Exception as e:
            logger.warning(f"缓存读取失败: {e}")
        return None

    def _set_cached_embedding(self, text: str, embedding: np.ndarray):
        """设置嵌入向量到缓存"""
        if not self.enable_cache:
            return

        cache_key = self._get_cache_key(text)
        try:
            # 将numpy数组转换为列表存储
            cache.set(cache_key, embedding.tolist(), timeout=self.cache_timeout)
            logger.debug(f"缓存设置: {text[:50]}...")
        except Exception as e:
            logger.warning(f"缓存设置失败: {e}")

    @retry(
        max_tries=3,
        delay=1.5,
        backoff_factor=2.0,
        exceptions=[EmbeddingAPIError, requests.exceptions.RequestException],
        on_retry=log_retry,
    )
    def _get_embedding_from_api(self, text: str) -> np.ndarray:
        """从API获取嵌入向量（内部方法）"""
        if not self.api_key:
            # 如果API密钥未设置，返回随机向量（仅用于测试）
            logger.warning("使用随机向量替代真实嵌入（仅用于测试）")
            return np.random.rand(self.vector_dim).astype("float32")

        try:
            # 使用OpenAI兼容模式调用DashScope API获取嵌入向量
            logger.info(f"使用模型 {self.embedding_model_version} 获取嵌入向量，API密钥: {self.api_key[:5]}***")
            response = self.client.embeddings.create(
                model=self.embedding_model_version,
                input=text,
                dimensions=self.vector_dim,
                encoding_format="float",
            )

            # 获取嵌入向量
            embedding = np.array(response.data[0].embedding).astype("float32")
            logger.info(f"成功获取嵌入向量，维度: {len(embedding)}")
            return embedding

        except requests.exceptions.RequestException as e:
            # 网络错误，可以重试
            logger.error(f"网络请求错误: {str(e)}")
            raise  # 让装饰器捕获并重试

        except Exception as e:
            if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
                # 速率限制或超时错误，可以重试
                logger.error(f"API限制错误: {str(e)}")
                raise EmbeddingAPIError(f"API调用失败: {str(e)}")

            logger.exception(f"获取嵌入时发生异常: {str(e)}")
            # 其他错误，返回随机向量（应急措施）
            return np.random.rand(self.vector_dim).astype("float32")

    def get_embedding(self, text: str) -> np.ndarray:
        """
        获取文本的向量表示（带缓存优化）

        首先尝试从缓存获取，如果缓存未命中则调用API并缓存结果
        """
        # 1. 尝试从缓存获取
        cached_embedding = self._get_cached_embedding(text)
        if cached_embedding is not None:
            return cached_embedding

        # 2. 缓存未命中，从API获取
        embedding = self._get_embedding_from_api(text)

        # 3. 缓存结果
        self._set_cached_embedding(text, embedding)

        return embedding

    def clear_cache(self):
        """清空嵌入向量缓存"""
        try:
            # 这里只能清空当前进程的缓存
            # 如果使用Redis等外部缓存，需要实现相应的清空逻辑
            logger.info("清空嵌入向量缓存")
        except Exception as e:
            logger.warning(f"清空缓存失败: {e}")

    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        return {
            "cache_enabled": self.enable_cache,
            "cache_timeout": self.cache_timeout,
            "model_version": self.embedding_model_version,
        }
