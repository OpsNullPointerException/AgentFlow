from typing import List, Dict, Any
import logging

from documents.services.vector_db_service import VectorDBService

logger = logging.getLogger(__name__)

class RAGService:
    """检索增强生成服务，负责文档检索和上下文处理"""
    
    @staticmethod
    def retrieve_relevant_documents(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        检索与查询相关的文档
        
        Args:
            query: 用户查询
            top_k: 返回的最相关文档数量
            
        Returns:
            相关文档列表
        """
        # 调用向量数据库服务进行检索
        return VectorDBService.search_static(query, top_k)
    
    @staticmethod
    def format_context_for_llm(retrieved_docs: List[Dict[str, Any]], query: str) -> str:
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
            title = doc.get('title', f"文档 {i+1}")
            content = doc.get('content', '')
            
            # 格式化为便于LLM理解的形式
            context += f"[文档{i+1}：{title}]\n{content}\n\n"
        
        return context