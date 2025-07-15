from ninja import Schema
from typing import List, Optional, Dict, Any

class RetrievalIn(Schema):
    """检索请求的输入Schema"""
    query: str  # 查询文本
    top_k: int = 5  # 返回结果数量，默认5条
    embedding_model_version: Optional[str] = None  # 嵌入模型版本，可选

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
    score: float  # 相关性分数
    chunk_index: int
    embedding_model_version: Optional[str] = None

class RetrievalResultOut(Schema):
    """检索结果输出Schema"""
    results: List[DocumentSearchResultOut]
    total: int
    query: str
    search_time: float  # 搜索耗时（秒）