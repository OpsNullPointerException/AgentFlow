from django.shortcuts import get_object_or_404
from django.db import transaction
from typing import List
from qa.controllers import router
from qa.schemas.conversation import (
    ConversationIn, 
    ConversationOut, 
    ConversationDetailOut,
    MessageIn,
    MessageOut
)
from qa.models import Conversation, Message, MessageDocumentReference
from documents.models import Document

@router.get("/conversations", response=List[ConversationOut])
def list_conversations(request):
    """获取当前用户的所有对话"""
    return Conversation.objects.filter(user=request.auth)

@router.post("/conversations", response=ConversationOut)
def create_conversation(request, data: ConversationIn):
    """创建新对话"""
    conversation = Conversation.objects.create(
        title=data.title,
        user=request.auth
    )
    return conversation

@router.get("/conversations/{conversation_id}", response=ConversationDetailOut)
def get_conversation(request, conversation_id: int):
    """获取对话详情，包括所有消息"""
    conversation = get_object_or_404(Conversation, id=conversation_id, user=request.auth)
    return conversation

@router.post("/conversations/{conversation_id}/messages", response=MessageOut)
def create_message(request, conversation_id: int, data: MessageIn):
    """向对话中添加新消息并获取回复"""
    conversation = get_object_or_404(Conversation, id=conversation_id, user=request.auth)
    
    # 创建用户消息
    user_message = Message.objects.create(
        conversation=conversation,
        content=data.content,
        message_type='user'
    )
    
    # TODO: 在实际应用中，这里应该调用LLM服务获取回复
    # 1. 获取对话历史
    # 2. 调用RAG系统检索相关文档
    # 3. 将检索结果与问题一起发送给LLM
    # 4. 接收LLM回复并保存
    
    # 模拟LLM回复（实际应用中这部分应该由LLM生成）
    with transaction.atomic():
        assistant_message = Message.objects.create(
            conversation=conversation,
            content=f"这是对'{data.content}'的模拟回复。在实际应用中，这部分内容将由LLM生成，基于文档检索结果。",
            message_type='assistant'
        )
        
        # 模拟添加文档引用（实际应用中应该是基于RAG检索结果）
        documents = Document.objects.filter(owner=request.auth)[:2]  # 仅用于演示
        for i, doc in enumerate(documents):
            MessageDocumentReference.objects.create(
                message=assistant_message,
                document=doc,
                relevance_score=0.8 - (i * 0.1),  # 模拟不同的相关性分数
                chunk_indices=[1, 2]  # 模拟块索引
            )
    
    # 更新对话时间
    conversation.save()  # 触发updated_at更新
    
    return assistant_message

@router.delete("/conversations/{conversation_id}")
def delete_conversation(request, conversation_id: int):
    """删除对话"""
    conversation = get_object_or_404(Conversation, id=conversation_id, user=request.auth)
    conversation.delete()
    return {"success": True}