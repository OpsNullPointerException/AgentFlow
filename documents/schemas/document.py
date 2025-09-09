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
    task_id: Optional[str] = None
    file_size: Optional[int] = None
    
    @staticmethod
    def resolve_file_size(obj):
        """计算文件大小"""
        try:
            if obj.file and hasattr(obj.file, 'size'):
                return obj.file.size
            return 0
        except:
            return 0


class TaskStatusOut(Schema):
    """任务状态输出Schema"""

    task_id: Optional[str] = None
    status: str
    document_status: str
    result: Optional[dict] = None


class DocumentChunkOut(Schema):
    """返回给前端的文档块Schema"""

    id: int
    chunk_index: int
    content: str


class DocumentDetailOut(DocumentOut):
    """包含文档块信息的文档详情Schema"""

    chunks: List[DocumentChunkOut] = []


class ReindexDocumentIn(Schema):
    """用于重新索引文档的输入Schema"""

    embedding_model_version: Optional[str] = None


class DocumentListOut(Schema):
    """分页文档列表响应Schema"""
    
    documents: List[DocumentOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool
