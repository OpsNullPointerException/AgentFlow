import numpy as np
from loguru import logger
import os
from django.conf import settings
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
        
        logger.info(f"初始化EmbeddingService，使用模型: {self.embedding_model_version}")
        
        # 创建OpenAI客户端（使用DashScope兼容模式）
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

    @retry(
        max_tries=3,
        delay=1.5,
        backoff_factor=2.0,
        exceptions=[EmbeddingAPIError, requests.exceptions.RequestException],
        on_retry=log_retry
    )
    def get_embedding(self, text: str) -> np.ndarray:
        """获取文本的向量表示"""
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
                encoding_format="float"
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
