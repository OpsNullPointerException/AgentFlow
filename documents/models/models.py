from django.db import models
from django.contrib.auth.models import User
import uuid
import os

def document_file_path(instance, filename):
    """为上传的文档生成唯一的文件路径"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('documents', str(instance.owner_id), filename)

class Document(models.Model):
    """文档模型，存储用户上传的文档信息"""
    DOCUMENT_TYPES = (
        ('pdf', 'PDF文档'),
        ('docx', 'Word文档'),
        ('txt', '文本文档'),
    )
    
    STATUS_CHOICES = (
        ('pending', '待处理'),
        ('processing', '处理中'),
        ('processed', '已处理'),
        ('failed', '处理失败'),
    )
    
    title = models.CharField('标题', max_length=255)
    file = models.FileField('文件', upload_to=document_file_path)
    file_type = models.CharField('文件类型', max_length=10, choices=DOCUMENT_TYPES)
    description = models.TextField('描述', blank=True, null=True)
    # 使用整数字段替代外键
    owner_id = models.IntegerField('用户ID')
    status = models.CharField('处理状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField('错误信息', blank=True, null=True)
    
    # 存储处理文档时使用的嵌入模型版本
    embedding_model_version = models.CharField('嵌入模型版本', max_length=50, null=True, blank=True)
    
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    
    class Meta:
        verbose_name = '文档'
        verbose_name_plural = '文档'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title

class DocumentChunk(models.Model):
    """文档分块模型，存储文档的分块内容和向量表示"""
    # 使用整数字段替代外键
    document_id = models.IntegerField('文档ID')
    content = models.TextField('内容')
    chunk_index = models.IntegerField('块索引')
    vector_id = models.CharField('向量ID', max_length=255, blank=True, null=True)
    
    # 存储块向量化时使用的嵌入模型版本
    embedding_model_version = models.CharField('嵌入模型版本', max_length=50, null=True, blank=True)
    
    class Meta:
        verbose_name = '文档块'
        verbose_name_plural = '文档块'
        ordering = ['document_id', 'chunk_index']
        unique_together = ('document_id', 'chunk_index')
    
    def __str__(self):
        return f"文档ID:{self.document_id} - 块{self.chunk_index}"
