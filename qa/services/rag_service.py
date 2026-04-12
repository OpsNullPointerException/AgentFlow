import time
from typing import Optional

from loguru import logger

from documents.services.vector_db_service import VectorDBService
from documents.services.hybrid_search import HybridSearch
from qa.schemas.retrieval import RerankInfoOut, RetrievalDocumentsOut, DocumentSearchResultOut

from .reranker_service import RerankerService

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
        self.reranker_service = RerankerService()

    def retrieve_relevant_documents(
        self,
        query: str,
        top_k: int = 5,
        enable_rerank: bool = True,
        rerank_method: str = "llm_rerank",
        rerank_top_k: Optional[int] = None,
        doc_category: Optional[str] = "user",
        use_hybrid: bool = True,
        vector_weight: float = 0.5,
        bm25_weight: float = 0.5,
    ) -> RetrievalDocumentsOut:
        """
        检索与查询相关的文档，支持混合检索和重排序

        Args:
            query: 用户查询
            top_k: 初始检索的文档数量
            enable_rerank: 是否启用重排序
            rerank_method: 重排序方法
            rerank_top_k: 重排序后返回的文档数量
            doc_category: 文档分类过滤
            use_hybrid: 是否使用混合检索（向量+BM25）
            vector_weight: 向量检索权重
            bm25_weight: BM25检索权重

        Returns:
            RetrievalDocumentsOut: 包含文档列表和重排序信息的schema对象
        """
        # 1. 混合检索或纯向量检索
        initial_top_k = max(top_k * 2, 20) if enable_rerank else top_k

        if use_hybrid:
            logger.info("使用混合检索（向量+BM25）")
            documents = HybridSearch.search_static(
                query=query,
                top_k=initial_top_k,
                embedding_model_version=self.embedding_model_version,
                vector_weight=vector_weight,
                bm25_weight=bm25_weight,
                doc_category=doc_category
            )
        else:
            logger.info("使用纯向量检索")
            documents = VectorDBService.search_static(
                query=query,
                top_k=initial_top_k,
                embedding_model_version=self.embedding_model_version
            )

        rerank_info = {"rerank_enabled": enable_rerank, "rerank_method": None, "rerank_time": None}

        # 2. 重排序（如果启用）
        if enable_rerank and documents:
            logger.info(f"对 {len(documents)} 个文档进行重排序，方法: {rerank_method}")
            start_time = time.time()

            try:
                # 执行重排序
                reranked_documents = self.reranker_service.rerank_documents(
                    query=query, documents=documents, method=rerank_method, top_k=rerank_top_k or top_k
                )

                rerank_time = time.time() - start_time
                rerank_info.update({"rerank_method": rerank_method, "rerank_time": round(rerank_time, 3)})

                logger.info(f"重排序完成，耗时: {rerank_time:.3f}秒，返回 {len(reranked_documents)} 个文档")
                documents = reranked_documents

            except Exception as e:
                logger.error(f"重排序失败，使用原始结果: {str(e)}")
                # 重排序失败时，截取原始结果
                documents = documents[: rerank_top_k or top_k]
        else:
            # 未启用重排序时，截取所需数量的文档
            documents = documents[:top_k]

        return RetrievalDocumentsOut(documents=documents, rerank_info=RerankInfoOut(**rerank_info))

    @staticmethod
    def retrieve_relevant_documents_static(
        query: str,
        top_k: int = 5,
        embedding_model_version=None,
        enable_rerank: bool = True,
        rerank_method: str = "llm_rerank",
        rerank_top_k: Optional[int] = None,
    ) -> RetrievalDocumentsOut:
        """
        静态方法版本，检索与查询相关的文档，支持重排序

        Args:
            query: 用户查询
            top_k: 初始检索的文档数量
            embedding_model_version: 嵌入模型版本
            enable_rerank: 是否启用重排序
            rerank_method: 重排序方法
            rerank_top_k: 重排序后返回的文档数量

        Returns:
            RetrievalDocumentsOut: 包含文档列表和重排序信息的schema对象
        """
        rag_service = RAGService(embedding_model_version=embedding_model_version)
        return rag_service.retrieve_relevant_documents(
            query=query,
            top_k=top_k,
            enable_rerank=enable_rerank,
            rerank_method=rerank_method,
            rerank_top_k=rerank_top_k,
        )

    def format_context_for_llm(self, retrieved_docs: list[DocumentSearchResultOut], query: str) -> str:
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
            title = doc.title or f"文档 {i + 1}"
            content = doc.content or ""

            # 格式化为便于LLM理解的形式
            context += f"[文档{i + 1}：{title}]\n{content}\n\n"

        return context

    def filter_by_relevance(
        self,
        query: str,
        documents: list[DocumentSearchResultOut],
        threshold: float = 0.3,
    ) -> list[DocumentSearchResultOut]:
        """
        用 cross-encoder 评估文档相关性，过滤掉不相关的文档。

        Args:
            query: 用户查询
            documents: 检索到的文档列表
            threshold: 相关性分数阈值，低于此值的文档会被过滤

        Returns:
            过滤后的相关文档列表
        """
        if not documents:
            return []

        try:
            # 用 cross-encoder 对文档打分
            scored_docs = self.reranker_service._rerank_with_cross_encoder(query, documents)

            # 按阈值过滤
            filtered = [doc for doc in scored_docs if (doc.rerank_score or 0) >= threshold]
            logger.info(
                f"Relevance filter: {len(filtered)}/{len(documents)} docs kept "
                f"(threshold={threshold}, query={query[:50]})"
            )
            return filtered

        except Exception as e:
            logger.warning(f"Cross-encoder filter failed, keeping all docs: {e}")
            return documents
