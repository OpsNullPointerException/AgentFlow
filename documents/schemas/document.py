from ninja import Schema
from typing import List, Optional
from datetime import datetime

class DocumentIn(Schema):
    """用于创建文档的输入Schema"""
    title: str
    description: Optional[str] = None

class DocumentOut(Schema):
    """返回给前端的文档Schema"""
    id: int
    title: str
    description: Optional[str] = None
    file_type: str
    status: str
    created_at: datetime
    updated_at: datetime

class DocumentChunkOut(Schema):
    """返回给前端的文档块Schema"""
    id: int
    chunk_index: int
    content: str

class DocumentDetailOut(DocumentOut):
    """包含文档块信息的文档详情Schema"""
    chunks: List[DocumentChunkOut] = []