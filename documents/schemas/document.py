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
