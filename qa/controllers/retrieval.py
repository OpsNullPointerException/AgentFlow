import time

from qa.controllers import router
from qa.schemas.retrieval import DocumentSearchResultOut, RetrievalIn, RetrievalResultOut
from qa.services.rag_service import RAGService


@router.post("/retrieve", response=RetrievalResultOut, summary="检索相关文档")
def retrieve_documents(request, data: RetrievalIn):
    """
    基于查询文本检索相关文档

    使用向量数据库搜索与查询语义相关的文档。支持重排序功能以提高检索结果的相关性。
    可以指定返回的结果数量、使用的嵌入模型版本和重排序方法。
    """
    # 记录开始时间
    start_time = time.time()

    # 使用RAGService执行检索
    rag_service = RAGService(embedding_model_version=data.embedding_model_version)

    # 执行搜索和重排序
    retrieval_result = rag_service.retrieve_relevant_documents(
        query=data.query,
        top_k=data.top_k,
        enable_rerank=data.enable_rerank,
        rerank_method=data.rerank_method,
        rerank_top_k=data.rerank_top_k,
    )

    # 解包结果
    search_results = retrieval_result.documents
    rerank_info = retrieval_result.rerank_info

    # 计算搜索时间
    search_time = time.time() - start_time

    # 返回结果
    return RetrievalResultOut(
        results=search_results,
        total=len(search_results),
        query=data.query,
        search_time=round(search_time, 3),
        rerank_enabled=rerank_info.rerank_enabled,
        rerank_method=rerank_info.rerank_method,
        rerank_time=rerank_info.rerank_time,
    )
