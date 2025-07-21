from django.http import HttpRequest, StreamingHttpResponse
from typing import List
from qa.controllers import router
from qa.schemas.conversation import (
    ConversationIn,
    ConversationOut,
    ConversationDetailOut,
    MessageIn,
    MessageOut,
)
from qa.services.conversation_service import ConversationService
from accounts.controllers.auth import get_user_from_token
from loguru import logger


@router.get("/conversations", response=List[ConversationOut])
def list_conversations(request):
    """获取当前用户的所有对话"""
    # 使用ConversationService处理业务逻辑
    conversation_service = ConversationService()
    return conversation_service.get_user_conversations(user_id=request.auth.id)


@router.post("/conversations", response=ConversationOut)
def create_conversation(request:HttpRequest, data: ConversationIn):
    """创建新对话"""
    conversation_service = ConversationService()
    return conversation_service.create_conversation(user_id=request.auth.id, title=data.title)


@router.get("/conversations/{conversation_id}", response=ConversationDetailOut)
def get_conversation(request:HttpRequest, conversation_id: int):
    """获取对话详情，包括所有消息"""
    conversation_service = ConversationService()
    return conversation_service.get_conversation_with_messages(
        conversation_id=conversation_id, user_id=request.auth.id
    )


@router.post("/conversations/{conversation_id}/messages", response=MessageOut)
def create_message(request, conversation_id: int, data: MessageIn):
    """向对话中添加新消息并获取回复"""
    conversation_service = ConversationService()
    return conversation_service.create_message(
        conversation_id=conversation_id,
        user_id=request.auth.id,
        content=data.content,
        model=getattr(data, "model", None),
    )


@router.get("/conversations/{conversation_id}/messages/stream", auth=None, response=None)
def create_message_stream(request, conversation_id: int):
    """向对话中添加新消息并获取流式回复（SSE）- GET方法用于EventSource"""

    # 从查询参数中获取内容、令牌和模型
    message_content = request.GET.get("content", "")
    token = request.GET.get("token", "")
    model = request.GET.get("model", "qwen-turbo")  # 默认使用qwen-turbo

    if not message_content:
        return {"error": "缺少必要的content参数"}

    if not token:
        return {"error": "缺少认证令牌"}

    logger.info(f"收到流式请求，对话ID: {conversation_id}, 使用模型: {model}")

    # 手动验证令牌
    user = get_user_from_token(token)
    if not user:
        return {"error": "无效的令牌或令牌已过期"}, 401

    # 使用ConversationService处理流式响应
    conversation_service = ConversationService()

    # 返回流式响应
    response = StreamingHttpResponse(
        conversation_service.create_message_stream(
            conversation_id=conversation_id, user_id=user.id, content=message_content, model=model
        ),
        content_type="text/event-stream",
    )

    # 添加SSE所需的响应头
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # 禁用Nginx缓冲
    return response


@router.delete("/conversations/{conversation_id}")
def delete_conversation(request, conversation_id: int):
    """删除对话"""
    conversation_service = ConversationService()
    success = conversation_service.delete_conversation(
        conversation_id=conversation_id, user_id=request.auth.id
    )
    return {"success": success}
