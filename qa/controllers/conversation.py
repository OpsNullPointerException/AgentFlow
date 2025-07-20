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
from qa.services.qa_service import QAService
from loguru import logger

@router.get("/conversations", response=List[ConversationOut])
def list_conversations(request):
    """获取当前用户的所有对话"""
    return Conversation.objects.filter(user_id=request.auth.id)

@router.post("/conversations", response=ConversationOut)
def create_conversation(request, data: ConversationIn):
    """创建新对话"""
    conversation = Conversation.objects.create(
        title=data.title,
        user_id=request.auth.id
    )
    return conversation

@router.get("/conversations/{conversation_id}", response=ConversationDetailOut)
def get_conversation(request, conversation_id: int):
    """获取对话详情，包括所有消息"""
    # 获取对话
    conversation = get_object_or_404(Conversation, id=conversation_id, user_id=request.auth.id)
    
    # 获取关联的消息
    messages = Message.objects.filter(conversation_id=conversation.id).order_by('created_at')
    
    # 获取每个消息的文档引用
    messages_with_refs = []
    for message in messages:
        # 获取引用的文档
        refs = []
        if message.message_type == 'assistant':  # 只有助手消息才有文档引用
            doc_refs = MessageDocumentReference.objects.filter(message_id=message.id)
            for doc_ref in doc_refs:
                try:
                    doc = Document.objects.get(id=doc_ref.document_id)
                    refs.append({
                        "id": doc.id,
                        "title": doc.title,
                        "relevance_score": doc_ref.relevance_score,
                        "chunk_indices": doc_ref.chunk_indices
                    })
                except Document.DoesNotExist:
                    # 文档可能已被删除
                    pass
        
        # 构建消息对象
        message_dict = {
            "id": message.id,
            "content": message.content,
            "message_type": message.message_type,
            "created_at": message.created_at,
            "referenced_documents": refs
        }
        messages_with_refs.append(message_dict)
    
    # 构建结果对象
    result = {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "messages": messages_with_refs
    }
    
    return result

@router.post("/conversations/{conversation_id}/messages", response=MessageOut)
def create_message(request, conversation_id: int, data: MessageIn):
    """向对话中添加新消息并获取回复"""
    try:
        # 1. 验证对话存在并属于当前用户
        conversation = get_object_or_404(Conversation, id=conversation_id, user_id=request.auth.id)
        
        # 2. 记录用户消息
        user_message = Message.objects.create(
            conversation_id=conversation.id,
            content=data.content,
            message_type='user'
        )
        
        # 3. 调用QA服务处理查询
        logger.info(f"开始处理用户查询，对话ID: {conversation_id}, 查询内容: {data.content[:50]}...")
        qa_service = QAService()
        qa_response = qa_service.process_query(
            conversation_id=conversation_id,
            query=data.content,
            user_id=request.auth.id
        )
        
        # 4. 获取助手回复信息
        # 注意：QA服务内部已经创建了消息记录，我们只需获取消息对象
        assistant_message = Message.objects.filter(
            conversation_id=conversation_id,
            message_type='assistant'
        ).order_by('-created_at').first()
        
        if not assistant_message:
            # 如果没有找到助手消息（极少数情况下可能发生），创建一个错误消息
            logger.error(f"QA服务处理成功但未找到助手消息记录，对话ID: {conversation_id}")
            with transaction.atomic():
                assistant_message = Message.objects.create(
                    conversation_id=conversation.id,
                    content=qa_response.get("answer", "处理请求时发生错误"),
                    message_type='assistant'
                )
        
        # 5. 更新对话时间
        conversation.save()  # 触发updated_at更新
        
        # 6. 返回助手消息
        logger.info(f"用户查询处理完成，对话ID: {conversation_id}")
        return assistant_message
        
    except Exception as e:
        # 处理异常情况
        logger.exception(f"处理消息时出错: {str(e)}")
        # 创建一个错误响应消息
        with transaction.atomic():
            error_message = Message.objects.create(
                conversation_id=conversation.id,
                content=f"处理您的请求时发生错误: {str(e)}",
                message_type='assistant'
            )
        return error_message

@router.delete("/conversations/{conversation_id}")
def delete_conversation(request, conversation_id: int):
    """删除对话"""
    conversation = get_object_or_404(Conversation, id=conversation_id, user_id=request.auth.id)
    conversation.delete()
    return {"success": True}