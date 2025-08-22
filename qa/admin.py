from django.contrib import admin
from .models import Conversation, Message, MessageDocumentReference


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "user_id", "created_at", "updated_at")
    list_filter = ()  # 移除user过滤器
    search_fields = ("title",)
    date_hierarchy = "created_at"


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("conversation_id", "message_type", "created_at")
    list_filter = ("message_type",)  # 移除conversation过滤器
    search_fields = ("content",)


@admin.register(MessageDocumentReference)
class MessageDocumentReferenceAdmin(admin.ModelAdmin):
    list_display = ("message_id", "document_id", "relevance_score")
    list_filter = ()  # 移除document过滤器
