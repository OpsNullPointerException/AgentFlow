from typing import List, Dict, Any, Generator, Optional
import json
from django.db import transaction
from django.shortcuts import get_object_or_404

from qa.schemas.conversation import DocumentReferenceOut, MessageOut

from ..models import Conversation, Message, MessageDocumentReference
from ..models.constants import MessageType
from documents.models import Document
from documents.models.models import DocumentChunk
from qa.services.qa_service import QAService
from loguru import logger


class ConversationService:
    """对话服务，负责处理对话相关的业务逻辑"""

    def __init__(self):
        self.qa_service = QAService()

    def get_user_conversations(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户的所有对话"""
        conversations = Conversation.objects.filter(user_id=user_id)
        return list(conversations.values())

    def create_conversation(self, user_id: int, title: str) -> Dict[str, Any]:
        """创建新对话"""
        conversation = Conversation.objects.create(title=title, user_id=user_id)
        return conversation.__dict__

    def delete_conversation(self, conversation_id: int, user_id: int) -> bool:
        """删除对话"""
        conversation = get_object_or_404(Conversation, id=conversation_id, user_id=user_id)
        conversation.delete()
        return True

    def get_conversation_with_messages(self, conversation_id: int, user_id: int) -> Dict[str, Any]:
        """获取对话详情，包括所有消息和文档引用"""
        # 获取对话
        conversation = get_object_or_404(Conversation, id=conversation_id, user_id=user_id)

        # 获取关联的消息
        messages = Message.objects.filter(conversation_id=conversation.id).order_by("created_at")

        # 获取每个消息的文档引用
        messages_with_refs = []
        for message in messages:
            # 将字符串类型转换为枚举类型
            message_type = MessageType(message.message_type)
            refs = self._get_message_document_references(message.id, message_type)

            # 构建消息对象
            message_dict = {
                "id": message.id,
                "content": message.content,
                "message_type": message.message_type,
                "created_at": message.created_at,
                "referenced_documents": refs,
            }
            messages_with_refs.append(message_dict)

        # 构建结果对象
        result = {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "messages": messages_with_refs,
        }

        return result

    def create_message(self, conversation_id: int, user_id: int, content: str, model: str = None) -> MessageOut:
        """向对话中添加新消息并获取回复"""
        try:
            # 验证对话存在并属于当前用户
            get_object_or_404(Conversation, id=conversation_id, user_id=user_id)

            # 使用QA服务处理查询，支持模型参数
            logger.info(f"开始处理用户查询，对话ID: {conversation_id}, 查询内容: {content[:50]}..., 模型: {model}")
            qa_response = self.qa_service.process_query(
                conversation_id=conversation_id,
                query=content,
                user_id=user_id,
                model=model or "qwen-turbo",
                memory_type="buffer_window",
            )

            # 获取助手回复信息
            assistant_message = (
                Message.objects.filter(conversation_id=conversation_id, message_type="assistant")
                .order_by("-created_at")
                .first()
            )

            if not assistant_message:
                # 如果没有找到助手消息，创建一个错误消息
                logger.error(f"QA服务处理成功但未找到助手消息记录，对话ID: {conversation_id}")
                with transaction.atomic():
                    assistant_message = Message.objects.create(
                        conversation_id=conversation_id,
                        content=qa_response.answer if hasattr(qa_response, "answer") else str(qa_response),
                        message_type="assistant",
                        model=model or "qwen-turbo",
                    )

            # 更新对话时间
            self._update_conversation_time(conversation_id)

            # 构建返回对象，包括文档引用
            message_data = {
                "id": assistant_message.id,
                "content": assistant_message.content,
                "message_type": assistant_message.message_type,
                "created_at": assistant_message.created_at,
                "model": assistant_message.model or model or "qwen-turbo",
                "referenced_documents": self._get_message_document_references(
                    assistant_message.id, MessageType.ASSISTANT
                ),
            }

            logger.info(f"用户查询处理完成，对话ID: {conversation_id}")

            return message_data

        except Exception as e:
            # 处理异常情况
            logger.exception(f"处理消息时出错: {str(e)}")
            # 创建一个错误响应消息
            with transaction.atomic():
                error_message = Message.objects.create(
                    conversation_id=conversation_id,
                    content=f"处理您的请求时发生错误: {str(e)}",
                    message_type="assistant",
                    model=model or "qwen-turbo",
                )

            return {
                "id": error_message.id,
                "content": error_message.content,
                "message_type": error_message.message_type,
                "created_at": error_message.created_at,
                "model": error_message.model,
                "referenced_documents": [],
            }

    def create_message_stream(
        self, conversation_id: int, user_id: int, content: str, model: str = "qwen-turbo"
    ) -> Generator[str, None, None]:
        """SSE流式处理生成器 - 产生符合SSE协议的数据块"""
        try:
            # 发送一个初始心跳消息，测试连接是否正常
            logger.info(f"开始SSE流式传输")

            # 验证对话存在并属于当前用户
            conversation = get_object_or_404(Conversation, id=conversation_id, user_id=user_id)

            logger.info(
                f"开始流式处理用户查询，对话ID: {conversation_id}, 查询内容: {content[:50] if len(content) > 50 else content}, 使用模型: {model}"
            )

            # 使用QAService的优化流式处理方法
            # QAService会自动处理：用户消息保存、助手消息创建、文档检索、LLM调用、记忆管理等
            chunk_count = 0
            for chunk in self.qa_service.process_query_stream(
                conversation_id=conversation_id,
                query=content,
                user_id=user_id,
                model=model,
                memory_type="buffer_window",
            ):
                chunk_count += 1
                # 将Python对象转换为JSON字符串，确保中文字符正确编码
                json_data = json.dumps(chunk, ensure_ascii=False)
                # 格式化为SSE协议标准格式: "data: {json}\n\n"
                sse_data = f"data: {json_data}\n\n"
                yield sse_data

            logger.info(f"SSE流式处理完成，对话ID: {conversation_id}, 共发送 {chunk_count} 个数据块")

        except Exception as e:
            logger.exception(f"SSE流式处理出错: {str(e)}")
            error_data = {
                "error": True,
                "error_message": str(e),
                "finished": True,
                "answer_delta": f"\n\n处理失败: {str(e)}",
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    def _get_message_document_references(
        self, message_id: int, message_type: MessageType
    ) -> List[DocumentReferenceOut]:
        """获取消息的文档引用"""
        refs = list[DocumentReferenceOut]()
        if message_type == MessageType.ASSISTANT:  # 只有助手消息才有文档引用
            doc_refs = MessageDocumentReference.objects.filter(message_id=message_id)
            for doc_ref in doc_refs:
                try:
                    doc = Document.objects.get(id=doc_ref.document_id)

                    # 查找文档块以获取内容预览
                    chunk_content = ""
                    try:
                        # 尝试找到第一个文档块来获取内容预览
                        first_chunk = DocumentChunk.objects.filter(document_id=doc.id).first()
                        if first_chunk:
                            chunk_content = first_chunk.content[:200] + (
                                "..." if len(first_chunk.content) > 200 else ""
                            )
                    except Exception as e:
                        logger.warning(f"获取文档块内容失败: {str(e)}")

                    # 使用与流式响应一致的格式
                    refs.append(
                        DocumentReferenceOut(
                            document_id=doc.id,
                            title=doc.title,
                            content_preview=chunk_content or f"文档ID: {doc.id}, 标题: {doc.title}",
                            relevance_score=doc_ref.relevance_score,
                            chunk_indices=doc_ref.chunk_indices or [],
                        )
                    )
                except Document.DoesNotExist:
                    # 文档可能已被删除
                    pass
        return refs

    def _update_conversation_time(self, conversation_id: int) -> None:
        """更新对话的最后更新时间"""
        Conversation.objects.filter(id=conversation_id).update()  # 自动更新updated_at
