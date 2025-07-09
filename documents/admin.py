from django.contrib import admin
from .models import Document, DocumentChunk

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'file_type', 'status', 'owner_id', 'created_at')
    list_filter = ('file_type', 'status')
    search_fields = ('title', 'description')
    date_hierarchy = 'created_at'

@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ('document_id', 'chunk_index')
    list_filter = ()  # 移除document过滤器
    search_fields = ('content',)
