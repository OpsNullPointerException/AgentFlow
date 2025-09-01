from ninja import Schema
from typing import List, Optional, Dict, Any


class RetrievalIn(Schema):
    """检索请求的输入Schema"""

    query: str  # 查询文本
    top_k: int = 5  # 返回结果数量，默认5条
    embedding_model_version: Optional[str] = None  # 嵌入模型版本，可选
    enable_rerank: bool = True  # 是否启用重排序，默认启用
    rerank_method: str = "llm_rerank"  # 重排序方法，可选: "llm_rerank", "llm_score", "cross_encoder", "bm25", "keyword_boost", "hybrid"
    rerank_top_k: Optional[int] = None  # 重排序后返回的文档数量，如果为None则返回所有召回文档


class DocumentChunkOut(Schema):
    """文档块输出Schema"""

    chunk_id: int
    content: str
    chunk_index: int
    embedding_model_version: Optional[str] = None


class DocumentSearchResultOut(Schema):
    """文档搜索结果输出Schema"""

    id: int
    title: str
    content: str
    score: float  # 原始相关性分数
    chunk_index: int
    embedding_model_version: Optional[str] = None
    rerank_score: Optional[float] = None  # 重排序分数
    final_score: Optional[float] = None  # 最终分数（结合原始分数和重排序分数）
    rerank_method: Optional[str] = None  # 使用的重排序方法


class RetrievalResultOut(Schema):
    """检索结果输出Schema"""

    results: List[DocumentSearchResultOut]
    total: int
    query: str
    search_time: float  # 搜索耗时（秒）
    rerank_enabled: bool  # 是否启用了重排序
    rerank_method: Optional[str] = None  # 使用的重排序方法
    rerank_time: Optional[float] = None  # 重排序耗时（秒）


class RerankInfoOut(Schema):
    """重排序信息输出Schema"""
    
    rerank_enabled: bool  # 是否启用重排序
    rerank_method: Optional[str] = None  # 使用的重排序方法
    rerank_time: Optional[float] = None  # 重排序耗时（秒）


class RetrievalDocumentsOut(Schema):
    """RAG服务文档检索结果输出Schema"""
    
    documents: List[DocumentSearchResultOut]  # 检索到的文档列表
    rerank_info: RerankInfoOut  # 重排序信息
