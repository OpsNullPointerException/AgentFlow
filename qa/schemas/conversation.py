from ninja import Schema
from typing import List, Optional, Dict, Any
from datetime import datetime

class ConversationIn(Schema):
    """用于创建对话的输入Schema"""
    title: str

class MessageIn(Schema):
    """用于创建消息的输入Schema"""
    content: str

class DocumentReferenceOut(Schema):
    """文档引用输出Schema"""
    document_id: int  # 文档ID
    title: str
    content_preview: Optional[str] = None  # 添加可选的content_preview字段
    relevance_score: float
    chunk_indices: List[int] = []  # 设置默认为空列表

class MessageOut(Schema):
    """消息输出Schema"""
    id: int
    content: str
    message_type: str
    created_at: datetime
    referenced_documents: List[DocumentReferenceOut] = []

class ConversationOut(Schema):
    """对话输出Schema"""
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

class ConversationDetailOut(ConversationOut):
    """对话详情输出Schema"""
    messages: List[MessageOut] = []

class MessageStreamOut(Schema):
    """流式消息输出Schema"""
    answer_delta: str
    finished: bool
    error: bool = False
    error_message: str = ""
    model: str = ""