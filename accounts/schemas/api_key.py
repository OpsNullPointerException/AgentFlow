from ninja import Schema
from datetime import datetime


class ApiKeyOut(Schema):
    """API密钥输出Schema"""
    id: int
    name: str
    key: str  # 注意：通常只在创建时返回完整的key
    is_active: bool
    created_at: str


class ApiKeyIn(Schema):
    """API密钥创建输入Schema"""
    name: str