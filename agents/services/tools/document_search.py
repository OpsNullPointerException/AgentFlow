"""文档搜索工具"""

from typing import Optional, Type
from langchain.callbacks.manager import CallbackManagerForToolRun
from langchain.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, Field

from qa.services.rag_service import RAGService


class DocumentSearchInput(BaseModel):
    """文档搜索工具输入"""
    query: str = Field(..., description="搜索查询")
    top_k: int = Field(5, description="返回的文档数量")
    enable_rerank: bool = Field(True, description="是否启用重排序")


class DocumentSearchTool(BaseTool):
    """文档搜索工具 - 集成现有的RAG服务"""

    name: str = "document_search"
    description: str = "搜索相关文档内容。当用户询问关于文档、知识库中的信息时使用此工具。"
    args_schema: Type[BaseModel] = DocumentSearchInput
    rag_service: RAGService = Field(default=None, description="RAG服务实例")

    def __init__(self, embedding_model_version: Optional[str] = None, **kwargs):
        rag_service = RAGService(embedding_model_version=embedding_model_version)
        super().__init__(rag_service=rag_service, **kwargs)

    def _run(
        self,
        query: str,
        top_k: int = 5,
        enable_rerank: bool = True,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """执行文档搜索"""
        try:
            logger.info(f"Agent执行文档搜索: {query}")

            retrieval_result = self.rag_service.retrieve_relevant_documents(
                query=query, top_k=top_k, enable_rerank=enable_rerank
            )

            if not retrieval_result.documents:
                return "未找到相关文档。"

            results = []
            for i, doc in enumerate(retrieval_result.documents, 1):
                result = f"文档 {i}:\n"
                result += f"标题: {doc.title}\n"
                result += f"内容: {doc.content[:500]}...\n"
                result += f"相关性: {doc.score:.3f}\n"
                results.append(result)

            return "\n".join(results)

        except Exception as e:
            logger.error(f"文档搜索工具执行失败: {e}")
            return f"搜索失败: {str(e)}"
