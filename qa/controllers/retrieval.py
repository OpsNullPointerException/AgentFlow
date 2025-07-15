import time
from typing import List, Dict, Any

from qa.controllers import router
from qa.schemas.retrieval import RetrievalIn, RetrievalResultOut, DocumentSearchResultOut
from qa.services.rag_service import RAGService
from documents.services.vector_db_service import VectorDBService


@router.post("/retrieve", response=RetrievalResultOut, summary="检索相关文档")
def retrieve_documents(request, data: RetrievalIn):
    """
    基于查询文本检索相关文档

    使用向量数据库搜索与查询语义相关的文档。可以指定返回的结果数量和使用的嵌入模型版本。
    """
    # 记录开始时间
    start_time = time.time()
    
    # 使用RAGService执行检索
    rag_service = RAGService(embedding_model_version=data.embedding_model_version)
    
    # 执行搜索
    search_results = rag_service.retrieve_relevant_documents(query=data.query, top_k=data.top_k)

    # 计算搜索时间
    search_time = time.time() - start_time

    # 格式化结果
    formatted_results = [
        DocumentSearchResultOut(
            id=result["id"],
            title=result["title"],
            content=result["content"],
            score=result["score"],
            chunk_index=result["chunk_index"],
            embedding_model_version=result.get("embedding_model_version", None),
        )
        for result in search_results
    ]

    # 返回结果
    return {
        "results": formatted_results,
        "total": len(formatted_results),
        "query": data.query,
        "search_time": round(search_time, 3),
    }
