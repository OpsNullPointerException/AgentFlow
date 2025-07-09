import numpy as np
import logging
import os
from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)


class EmbeddingService:
    """向量嵌入服务，负责文本向量化"""

    def __init__(self):
        # 设置DashScope API密钥
        self.api_key = settings.DASHSCOPE_API_KEY
        if not self.api_key:
            logger.warning("DASHSCOPE_API_KEY未设置，向量嵌入服务将无法正常工作")
        else:
            # 设置环境变量，用于OpenAI客户端
            os.environ["DASHSCOPE_API_KEY"] = self.api_key
        
        # 创建OpenAI客户端（使用DashScope兼容模式）
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        # 向量嵌入维度
        self.vector_dim = 1024

    def get_embedding(self, text: str) -> np.ndarray:
        """获取文本的向量表示"""
        if not self.api_key:
            # 如果API密钥未设置，返回随机向量（仅用于测试）
            logger.warning("使用随机向量替代真实嵌入（仅用于测试）")
            return np.random.rand(self.vector_dim).astype("float32")

        try:
            # 使用OpenAI兼容模式调用DashScope API获取嵌入向量
            logger.info(f"使用OpenAI兼容模式调用DashScope API，密钥: {self.api_key[:5]}***")
            response = self.client.embeddings.create(
                model="text-embedding-v4",
                input=text,
                dimensions=self.vector_dim,
                encoding_format="float"
            )
            
            # 获取嵌入向量
            embedding = np.array(response.data[0].embedding).astype("float32")
            logger.info(f"成功获取嵌入向量，维度: {len(embedding)}")
            return embedding

        except Exception as e:
            logger.exception(f"获取嵌入时发生异常: {str(e)}")
            # 返回随机向量（应急措施）
            return np.random.rand(self.vector_dim).astype("float32")
