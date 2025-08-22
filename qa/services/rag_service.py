from typing import List, Dict, Any
from loguru import logger

from documents.services.vector_db_service import VectorDBService

# loguru不需要getLogger


class RAGService:
    """检索增强生成服务，负责文档检索和上下文处理"""

    def __init__(self, embedding_model_version=None):
        """
        初始化RAG服务

        Args:
            embedding_model_version: 嵌入模型版本，如果未指定则使用settings中的配置
        """
        self.embedding_model_version = embedding_model_version

    def retrieve_relevant_documents(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        检索与查询相关的文档

        Args:
            query: 用户查询
            top_k: 返回的最相关文档数量

        Returns:
            相关文档列表
        """
        # 调用向量数据库服务进行检索，传递嵌入模型版本
        return VectorDBService.search_static(query, top_k, embedding_model_version=self.embedding_model_version)

    @staticmethod
    def retrieve_relevant_documents_static(
        query: str, top_k: int = 5, embedding_model_version=None
    ) -> List[Dict[str, Any]]:
        """
        静态方法版本，检索与查询相关的文档

        Args:
            query: 用户查询
            top_k: 返回的最相关文档数量
            embedding_model_version: 嵌入模型版本

        Returns:
            相关文档列表
        """
        # 调用向量数据库服务进行检索
        return VectorDBService.search_static(query, top_k, embedding_model_version=embedding_model_version)

    def format_context_for_llm(self, retrieved_docs: List[Dict[str, Any]], query: str) -> str:
        """
        将检索到的文档和查询格式化为LLM可处理的上下文

        Args:
            retrieved_docs: 检索到的文档列表
            query: 原始查询

        Returns:
            格式化后的上下文字符串
        """
        if not retrieved_docs:
            return "没有找到相关的文档内容。"

        context = "以下是相关文档内容：\n\n"
        for i, doc in enumerate(retrieved_docs):
            # 添加文档标题和内容
            title = doc.get("title", f"文档 {i + 1}")
            content = doc.get("content", "")

            # 格式化为便于LLM理解的形式
            context += f"[文档{i + 1}：{title}]\n{content}\n\n"

        return context
