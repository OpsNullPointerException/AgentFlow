from ninja import Router, Schema, File
from ninja.files import UploadedFile
from typing import List, Optional
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from datetime import datetime

from .models import Document, DocumentChunk
from .services.vector_db_service import VectorDBService

# 定义Schema
class DocumentIn(Schema):
    """用于创建文档的输入Schema"""
    title: str
    description: Optional[str] = None

class DocumentOut(Schema):
    """返回给前端的文档Schema"""
    id: int
    title: str
    description: Optional[str] = None
    file_type: str
    status: str
    created_at: datetime
    updated_at: datetime

class DocumentChunkOut(Schema):
    """返回给前端的文档块Schema"""
    id: int
    chunk_index: int
    content: str

class DocumentDetailOut(DocumentOut):
    """包含文档块信息的文档详情Schema"""
    chunks: List[DocumentChunkOut] = []

# 创建路由器
router = Router(tags=["documents"])

@router.get("/", response=List[DocumentOut])
def list_documents(request):
    """获取当前用户的所有文档"""
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
    
    # TODO: 在实际应用中，这里应该触发异步任务来处理文档
    # 例如：process_document.delay(document.id)
    
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