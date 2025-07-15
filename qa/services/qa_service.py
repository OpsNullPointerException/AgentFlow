from loguru import logger
from typing import List, Dict, Any, Optional

from ..models import Conversation, Message, MessageDocumentReference
from .rag_service import RAGService
from .llm_service import LLMService

# loguru不需要getLogger

class QAService:
    """问答服务，负责处理用户问题并生成回答"""
    
    def __init__(self, embedding_model_version=None):
        """
        初始化问答服务
        
        Args:
            embedding_model_version: 嵌入模型版本，如果未指定则使用settings中的配置
        """
        self.embedding_model_version = embedding_model_version
        self.rag_service = RAGService(embedding_model_version=embedding_model_version)
        self.llm_service = LLMService()
        
    def process_query(self, conversation_id: int, query: str, user_id: int) -> Dict[str, Any]:
        """
        处理用户查询并生成回答
        
        Args:
            conversation_id: 对话ID
            query: 用户的问题
            user_id: 用户ID
            
        Returns:
            包含回答内容和相关文档的字典
        """
        try:
            # 1. 获取对话
            conversation = self._get_or_create_conversation(conversation_id, user_id)
            
            # 2. 获取对话历史
            history = self._get_conversation_history(conversation.id)
            
            # 3. 调用RAG系统检索相关文档
            relevant_docs = self.rag_service.retrieve_relevant_documents(query)
            
            # 4. 格式化上下文
            context = self.rag_service.format_context_for_llm(relevant_docs, query)
            
            # 5. 调用LLM生成回答
            llm_response = self.llm_service.generate_response(query, context, history)
            
            # 6. 保存用户问题和LLM回答到对话历史
            user_message = self._save_message(conversation.id, "user", query)
            assistant_message = self._save_message(conversation.id, "assistant", llm_response["answer"])
            
            # 7. 保存文档引用
            self._save_document_references(assistant_message.id, relevant_docs)
            
            # 8. 更新对话时间
            self._update_conversation_time(conversation.id)
            
            return {
                "answer": llm_response["answer"],
                "referenced_documents": self._format_document_references(relevant_docs),
                "error": llm_response.get("error", False),
                "conversation_id": conversation.id
            }
            
        except Exception as e:
            logger.exception(f"处理查询时发生错误: {str(e)}")
            return {
                "answer": f"处理您的问题时出现系统错误: {str(e)}",
                "referenced_documents": [],
                "error": True
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
            user_id=user_id
        )
    
    def _get_conversation_history(self, conversation_id: int) -> List[Dict[str, str]]:
        """获取格式化的对话历史"""
        messages = Message.objects.filter(
            conversation_id=conversation_id
        ).order_by('created_at')[:10]  # 最近10条消息
        
        history = []
        for message in messages:
            history.append({
                "role": message.message_type,  # 'user' 或 'assistant'
                "content": message.content
            })
        
        return history
    
    def _save_message(self, conversation_id: int, message_type: str, content: str) -> Message:
        """保存消息到对话历史"""
        return Message.objects.create(
            conversation_id=conversation_id,
            message_type=message_type,
            content=content
        )
    
    def _save_document_references(self, message_id: int, documents: List[Dict[str, Any]]) -> None:
        """保存文档引用"""
        for doc in documents:
            if 'id' in doc and 'score' in doc:
                MessageDocumentReference.objects.create(
                    message_id=message_id,
                    document_id=doc['id'],
                    relevance_score=doc['score'],
                    chunk_indices=doc.get('chunk_indices', [])
                )
    
    def _update_conversation_time(self, conversation_id: int) -> None:
        """更新对话的最后更新时间"""
        Conversation.objects.filter(id=conversation_id).update()  # 自动更新updated_at
    
    def _format_document_references(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """格式化文档引用以返回给客户端"""
        formatted_refs = []
        for doc in documents:
            if 'id' in doc and 'content' in doc:
                formatted_refs.append({
                    'document_id': doc['id'],
                    'title': doc.get('title', '无标题文档'),
                    'content_preview': doc['content'][:200] + '...' if len(doc['content']) > 200 else doc['content'],
                    'relevance_score': doc.get('score', 0.0)
                })
        return formatted_refs