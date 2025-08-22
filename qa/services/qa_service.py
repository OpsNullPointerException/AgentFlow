import hashlib
from typing import Any, Dict, Generator, List, Optional, Union

from django.conf import settings
from django.core.cache import cache

# LangChain Memory imports
from langchain.memory import (
    ConversationBufferWindowMemory,
    ConversationSummaryBufferMemory,
    ConversationTokenBufferMemory,
)
from langchain.schema import AIMessage, HumanMessage
from loguru import logger

from ..models import Conversation, Message, MessageDocumentReference
from ..schemas.conversation import MemoryInfoOut, QueryResponseOut
from .llm_service import LLMService
from .rag_service import RAGService


class QAService:
    """问答服务，负责处理用户问题并生成回答"""

    def __init__(self, embedding_model_version: Optional[str] = None):
        """
        初始化问答服务

        Args:
            embedding_model_version: 嵌入模型版本，如果未指定则使用settings中的配置
        """
        self.embedding_model_version = embedding_model_version
        self.rag_service = RAGService(embedding_model_version=embedding_model_version)
        self.llm_service = LLMService()
        # 用于缓存不同对话的memory实例
        self._memory_cache: dict[
            str, Union[ConversationBufferWindowMemory, ConversationTokenBufferMemory, ConversationSummaryBufferMemory]
        ] = {}

        # 优化的缓存配置
        self.retrieval_cache_timeout = getattr(settings, "QA_RETRIEVAL_CACHE_TIMEOUT", 3600)  # 1小时
        self.enable_retrieval_cache = getattr(settings, "QA_RETRIEVAL_CACHE_ENABLED", True)

        logger.info(f"初始化QAService, 检索缓存: {'启用' if self.enable_retrieval_cache else '禁用'}")

    def _get_retrieval_cache_key(self, query: str) -> str:
        """生成检索缓存键"""
        content = f"retrieval:{query}:{self.embedding_model_version}"
        return f"qa:retrieval:{hashlib.md5(content.encode('utf-8')).hexdigest()[:16]}"

    def _get_cached_retrieval(self, query: str) -> Optional[list[dict[str, Any]]]:
        """从缓存获取检索结果"""
        if not self.enable_retrieval_cache:
            return None

        cache_key = self._get_retrieval_cache_key(query)
        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.debug(f"检索缓存命中: {query[:50]}...")
                return cached_data
        except Exception as e:
            logger.warning(f"检索缓存读取失败: {e}")
        return None

    def _set_cached_retrieval(self, query: str, results: list[dict[str, Any]]):
        """设置检索结果到缓存"""
        if not self.enable_retrieval_cache:
            return

        cache_key = self._get_retrieval_cache_key(query)
        try:
            cache.set(cache_key, results, timeout=self.retrieval_cache_timeout)
            logger.debug(f"检索缓存设置: {query[:50]}...")
        except Exception as e:
            logger.warning(f"检索缓存设置失败: {e}")

    def process_query(
        self, conversation_id: int, query: str, user_id: int, memory_type: str = "buffer_window"
    ) -> QueryResponseOut:
        """
        处理用户查询并生成回答

        Args:
            conversation_id: 对话ID
            query: 用户的问题
            user_id: 用户ID
            memory_type: 记忆策略类型

        Returns:
            QueryResponseOut: 标准化的查询响应
        """
        try:
            # 1. 获取对话
            conversation = self._get_or_create_conversation(conversation_id, user_id)

            # 2. 获取对话历史（使用LangChain Memory）
            history = self._get_conversation_history(conversation.id, memory_type)

            # 3. 调用RAG系统检索相关文档（使用缓存优化）
            relevant_docs = self._get_cached_retrieval(query)
            if relevant_docs is None:
                # 缓存未命中，从RAG服务获取
                relevant_docs = self.rag_service.retrieve_relevant_documents(query)
                # 缓存结果
                self._set_cached_retrieval(query, relevant_docs)
            else:
                logger.info(f"使用缓存的检索结果，查询: {query[:50]}...")

            # 4. 格式化上下文
            context = self.rag_service.format_context_for_llm(relevant_docs, query)

            # 5. 调用LLM生成回答
            llm_response = self.llm_service.generate_response(query, context, history)

            # 6. 保存用户问题和LLM回答到对话历史（自动同步到Memory）
            user_message = self._save_message(conversation.id, "user", query)
            assistant_message = self._save_message(conversation.id, "assistant", llm_response["answer"])

            # 7. 保存文档引用
            self._save_document_references(assistant_message.id, relevant_docs)

            # 8. 更新对话时间
            self._update_conversation_time(conversation.id)

            # 9. 获取记忆状态信息
            memory_info = self.get_memory_info(conversation.id)

            # 格式化记忆信息为schema格式
            formatted_memory_info = {}
            for mem_type, info in memory_info.items():
                formatted_memory_info[mem_type] = MemoryInfoOut(
                    message_count=info["message_count"],
                    memory_type=info["memory_type"],
                    window_size=info.get("window_size"),
                )

            return QueryResponseOut(
                answer=llm_response["answer"],
                referenced_documents=self._format_document_references(relevant_docs),
                memory_info=formatted_memory_info,
                memory_type=memory_type,
                error=llm_response.get("error", False),
                conversation_id=conversation.id,
                tokens_used=llm_response.get("tokens_used"),
                model=llm_response.get("model"),
            )

        except Exception as e:
            logger.exception(f"处理查询时发生错误: {str(e)}")
            return QueryResponseOut(
                answer=f"处理您的问题时出现系统错误: {str(e)}",
                referenced_documents=[],
                memory_info={},
                memory_type=memory_type,
                error=True,
                conversation_id=conversation_id,
            )

    def process_query_stream(
        self,
        conversation_id: int,
        query: str,
        user_id: int,
        model: str = "qwen-turbo",
        memory_type: str = "buffer_window",
    ) -> Generator:
        """
        流式处理用户查询并生成回答

        Args:
            conversation_id: 对话ID
            query: 用户的问题
            user_id: 用户ID
            model: 使用的LLM模型名称，默认为"qwen-turbo"
            memory_type: 记忆策略类型

        Returns:
            生成器，每次返回一小段回答
        """
        try:
            # 1. 获取对话
            conversation = self._get_or_create_conversation(conversation_id, user_id)

            # 2. 获取对话历史（使用LangChain Memory）
            history = self._get_conversation_history(conversation.id, memory_type)

            # 3. 保存用户问题（自动同步到Memory）
            user_message = self._save_message(conversation.id, "user", query)

            # 4. 创建空的助手回复，后续更新
            assistant_message = self._save_message(conversation.id, "assistant", "")

            # 5. 更新对话时间
            self._update_conversation_time(conversation.id)

            # 先发送一个开始信号
            yield {
                "answer_delta": "",
                "finished": False,
                "model": model,
                "message_id": assistant_message.id,
                "status": "processing",
            }

            # 6. 调用RAG系统检索相关文档（可能耗时）
            relevant_docs = self.rag_service.retrieve_relevant_documents(query)

            # 7. 格式化上下文
            context = self.rag_service.format_context_for_llm(relevant_docs, query)

            # 8. 保存文档引用
            self._save_document_references(assistant_message.id, relevant_docs)

            # 收集完整响应以便更新数据库和Memory
            full_response = ""

            # 9. 流式调用LLM并实时返回
            logger.info(f"使用模型 {model} 和记忆策略 {memory_type} 流式生成回答")

            # 预先获取不变的信息，避免每次都重新计算
            formatted_docs = self._format_document_references(relevant_docs)

            for chunk in self.llm_service.generate_response_stream(query, context, history, model=model):
                # 如果是增量内容，更新累计响应
                if chunk.get("answer_delta"):
                    full_response += chunk["answer_delta"]

                # 添加基本信息（不耗时的操作）
                chunk["message_id"] = assistant_message.id
                chunk["referenced_documents"] = formatted_docs
                chunk["memory_type"] = memory_type

                # 立即yield，不等待其他操作
                yield chunk

                # 如果是最后一块，异步更新数据库和Memory
                if chunk.get("finished", False):
                    # 更新数据库中的消息内容
                    self._update_message_content(assistant_message.id, full_response)

                    # 同步完整回答到Memory
                    self._sync_assistant_message_to_memory(conversation.id, full_response)

        except Exception as e:
            logger.exception(f"流式处理查询时发生错误: {str(e)}")
            yield {
                "answer_delta": f"处理您的问题时出现系统错误: {str(e)}",
                "error": True,
                "finished": True,
                "referenced_documents": [],
            }

    def _get_or_create_conversation(self, conversation_id: Optional[int], user_id: int) -> Conversation:
        """获取或创建对话"""
        if conversation_id:
            try:
                # 尝试获取现有对话
                return Conversation.objects.get(id=conversation_id, user_id=user_id)
            except Conversation.DoesNotExist:
                # 如果不存在，创建新对话
                pass

        # 创建新对话
        return Conversation.objects.create(
            title=f"新对话 {Conversation.objects.filter(user_id=user_id).count() + 1}",
            user_id=user_id,
        )

    def _get_conversation_history(
        self, conversation_id: int, memory_type: str = "buffer_window"
    ) -> list[dict[str, str]]:
        """获取格式化的对话历史，使用LangChain Memory管理"""
        try:
            # 获取或创建memory实例
            memory = self._get_memory_for_conversation(conversation_id, memory_type)

            # 从memory获取历史消息
            messages = memory.chat_memory.messages

            # 转换为现有系统的格式
            history = []
            for message in messages:
                if isinstance(message, HumanMessage):
                    history.append({"role": "user", "content": message.content})
                elif isinstance(message, AIMessage):
                    history.append({"role": "assistant", "content": message.content})

            logger.info(f"从LangChain Memory获取对话历史: {len(history)}条消息")
            return history

        except Exception as e:
            logger.warning(f"LangChain Memory获取失败，使用简单方式: {str(e)}")
            # 降级到原来的简单方式
            return self._get_simple_conversation_history(conversation_id)

    def _get_simple_conversation_history(self, conversation_id: int) -> list[dict[str, str]]:
        """简单的对话历史获取（备用方案）"""
        messages = Message.objects.filter(conversation_id=conversation_id).order_by("created_at")[-10:]

        history = []
        for message in messages:
            history.append(
                {
                    "role": message.message_type,
                    "content": message.content,
                }
            )
        return history

    def _get_memory_for_conversation(
        self, conversation_id: int, memory_type: str = "buffer_window"
    ) -> Union[ConversationBufferWindowMemory, ConversationTokenBufferMemory, ConversationSummaryBufferMemory]:
        """为对话获取或创建LangChain Memory实例"""
        cache_key = f"{conversation_id}_{memory_type}"

        if cache_key not in self._memory_cache:
            # 创建新的memory实例
            memory = self._create_memory_instance(memory_type)

            # 从数据库加载历史对话到memory
            self._load_history_to_memory(conversation_id, memory)

            self._memory_cache[cache_key] = memory
            logger.info(f"创建{memory_type}记忆实例，对话ID: {conversation_id}")

        return self._memory_cache[cache_key]

    def _create_memory_instance(
        self, memory_type: str
    ) -> Union[ConversationBufferWindowMemory, ConversationTokenBufferMemory, ConversationSummaryBufferMemory]:
        """创建指定类型的LangChain Memory实例"""
        if memory_type == "buffer_window":
            return ConversationBufferWindowMemory(k=10, return_messages=True)
        elif memory_type == "token_buffer":
            # 使用TokenBuffer记忆，限制为1500个token
            return ConversationTokenBufferMemory(
                llm=self.llm_service.get_llm_instance(), max_token_limit=1500, return_messages=True
            )
        elif memory_type == "summary_buffer":
            # 使用摘要缓冲记忆
            return ConversationSummaryBufferMemory(
                llm=self.llm_service.get_llm_instance(), max_token_limit=1000, return_messages=True
            )
        else:
            logger.warning(f"未知记忆类型: {memory_type}, 使用默认buffer_window")
            return ConversationBufferWindowMemory(k=10, return_messages=True)

    def _load_history_to_memory(
        self,
        conversation_id: int,
        memory: Union[ConversationBufferWindowMemory, ConversationTokenBufferMemory, ConversationSummaryBufferMemory],
    ) -> None:
        """从数据库加载历史对话到LangChain memory"""
        messages = Message.objects.filter(conversation_id=conversation_id).order_by("created_at")

        for message in messages:
            if message.message_type == "user":
                memory.chat_memory.add_user_message(message.content)
            elif message.message_type == "assistant":
                memory.chat_memory.add_ai_message(message.content)

        logger.info(f"已加载 {len(messages)} 条历史消息到LangChain Memory")

    def _save_message(self, conversation_id: int, message_type: str, content: str) -> Message:
        """保存消息到对话历史并同步到LangChain Memory"""
        # 保存到数据库
        message = Message.objects.create(conversation_id=conversation_id, message_type=message_type, content=content)

        # 同步到所有该对话的memory缓存
        try:
            for cache_key in list(self._memory_cache.keys()):
                if cache_key.startswith(f"{conversation_id}_"):
                    memory = self._memory_cache[cache_key]
                    if message_type == "user":
                        memory.chat_memory.add_user_message(content)
                    elif message_type == "assistant":
                        memory.chat_memory.add_ai_message(content)
        except Exception as e:
            logger.warning(f"同步消息到LangChain Memory失败: {str(e)}")

        return message

    def _update_message_content(self, message_id: int, content: str) -> None:
        """更新消息内容"""
        Message.objects.filter(id=message_id).update(content=content)

    def _sync_assistant_message_to_memory(self, conversation_id: int, content: str) -> None:
        """同步助手消息到Memory（用于流式处理的最终同步）"""
        try:
            for cache_key in list(self._memory_cache.keys()):
                if cache_key.startswith(f"{conversation_id}_"):
                    memory = self._memory_cache[cache_key]
                    # 如果最后一条消息还是空的助手消息，更新它
                    if (
                        memory.chat_memory.messages
                        and isinstance(memory.chat_memory.messages[-1], AIMessage)
                        and not memory.chat_memory.messages[-1].content
                    ):
                        memory.chat_memory.messages[-1].content = content
                    elif not memory.chat_memory.messages or not isinstance(memory.chat_memory.messages[-1], AIMessage):
                        # 如果没有助手消息或最后一条不是助手消息，添加新的
                        memory.chat_memory.add_ai_message(content)
        except Exception as e:
            logger.warning(f"同步助手消息到Memory失败: {str(e)}")

    def _save_document_references(self, message_id: int, documents: list[dict[str, Any]]) -> None:
        """保存文档引用"""
        for doc in documents:
            if "id" in doc and "score" in doc:
                # 使用get_or_create避免创建重复记录
                MessageDocumentReference.objects.get_or_create(
                    message_id=message_id,
                    document_id=doc["id"],
                    defaults={
                        "relevance_score": doc["score"],
                        "chunk_indices": doc.get("chunk_indices", []),
                    },
                )

    def _update_conversation_time(self, conversation_id: int) -> None:
        """更新对话的最后更新时间"""
        Conversation.objects.filter(id=conversation_id).update()  # 自动更新updated_at

    def _format_document_references(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """格式化文档引用以返回给客户端"""
        formatted_refs = []
        for doc in documents:
            if "id" in doc and "content" in doc:
                formatted_refs.append(
                    {
                        "document_id": doc["id"],
                        "title": doc.get("title", "无标题文档"),
                        "content_preview": doc["content"][:200] + "..."
                        if len(doc["content"]) > 200
                        else doc["content"],
                        "relevance_score": doc.get("score", 0.0),
                    }
                )
        return formatted_refs

    def get_memory_info(self, conversation_id: int) -> dict[str, Any]:
        """获取对话的记忆状态信息"""
        info = {}
        for cache_key, memory in self._memory_cache.items():
            if cache_key.startswith(f"{conversation_id}_"):
                memory_type = cache_key.split("_", 1)[1]
                info[memory_type] = {
                    "message_count": len(memory.chat_memory.messages),
                    "memory_type": type(memory).__name__,
                }
                if hasattr(memory, "k"):
                    info[memory_type]["window_size"] = memory.k
        return info
