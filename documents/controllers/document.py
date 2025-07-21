from ninja import Router, File
from ninja.files import UploadedFile
from typing import List
from django.shortcuts import get_object_or_404
import threading

from documents.models import Document
from documents.services.vector_db_service import VectorDBService
from documents.services.document_processor import DocumentProcessor
from documents.schemas.document import DocumentIn, DocumentOut, DocumentDetailOut, ReindexDocumentIn

# 创建路由器
router = Router(tags=["documents"])

@router.get("/", response=List[DocumentOut])
def list_documents(request):
    """获取当前用户的所有文档 - 支持带斜杠和不带斜杠的URL"""
    return Document.objects.filter(owner_id=request.auth.id)

@router.get("/{document_id}", response=DocumentDetailOut)
def get_document(request, document_id: int):
    """获取文档详情，包括文档块"""
    document = get_object_or_404(Document, id=document_id, owner_id=request.auth.id)
    return document

@router.post("/", response=DocumentOut)
def create_document(request, document_in: DocumentIn, file: UploadedFile = File(...)):
    """上传新文档"""
    # 确定文件类型
    file_extension = file.name.split('.')[-1].lower()
    file_type_mapping = {
        'pdf': 'pdf',
        'docx': 'docx',
        'txt': 'txt'
    }
    file_type = file_type_mapping.get(file_extension, 'txt')
    
    # 创建文档对象
    document = Document.objects.create(
        title=document_in.title,
        description=document_in.description,
        file=file,
        file_type=file_type,
        owner_id=request.auth.id,
        status='pending'
    )
    
    # 在后台线程处理文档，避免阻塞API响应
    def process_document_async(document_id):
        processor = DocumentProcessor()
        processor.process_document(document_id)
    
    # 启动后台线程处理文档
    threading.Thread(
        target=process_document_async,
        args=(document.id,),
        daemon=True
    ).start()
    
    return document

@router.delete("/{document_id}")
def delete_document(request, document_id: int):
    """删除文档"""
    document = get_object_or_404(Document, id=document_id, owner_id=request.auth.id)
    
    # 删除文档
    document.delete()
    
    # 清除所有向量搜索缓存，因为删除文档会影响搜索结果
    VectorDBService.clear_search_cache()
    
    return {"success": True}

@router.post("/{document_id}/reindex", response=DocumentOut)
def reindex_document(request, document_id: int, reindex_data: ReindexDocumentIn = None):
    """重新索引文档，可选择不同的嵌入模型版本"""
    # 获取文档
    document = get_object_or_404(Document, id=document_id, owner_id=request.auth.id)
    
    # 获取嵌入模型版本
    embedding_model_version = None
    if reindex_data:
        embedding_model_version = reindex_data.embedding_model_version
    
    # 如果未指定嵌入模型版本，则使用设置中的版本
    if not embedding_model_version:
        from django.conf import settings
        # 根据配置选择合适的嵌入模型版本
        if getattr(settings, 'EMBEDDING_SERVICE_TYPE', 'api') == 'local':
            embedding_model_version = settings.LOCAL_EMBEDDING_MODEL
        else:
            embedding_model_version = settings.EMBEDDING_MODEL_VERSION
    
    # 在后台线程重新处理文档
    def reprocess_document_async(doc_id, embed_model_version):
        processor = DocumentProcessor(embedding_model_version=embed_model_version)
        processor.process_document(doc_id)
    
    # 更新文档状态
    document.status = 'pending'
    document.error_message = ''
    document.embedding_model_version = embedding_model_version  # 记录使用的模型版本
    document.save()
    
    # 启动后台线程处理文档
    threading.Thread(
        target=reprocess_document_async,
        args=(document.id, embedding_model_version),
        daemon=True
    ).start()
    
    return document