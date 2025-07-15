from ninja import Schema
from typing import List, Optional
from datetime import datetime

class ConversationIn(Schema):
    """用于创建对话的输入Schema"""
    title: str

class MessageIn(Schema):
    """用于创建消息的输入Schema"""
    content: str

class DocumentReferenceOut(Schema):
    """文档引用输出Schema"""
    id: int
    title: str
    relevance_score: float
    chunk_indices: List[int]

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