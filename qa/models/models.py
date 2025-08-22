from django.db import models


class Conversation(models.Model):
    """对话模型，表示一次完整的对话会话"""
    id = models.AutoField(primary_key=True)
    title = models.CharField("标题", max_length=255)
    # 使用整数字段替代外键
    user_id = models.IntegerField("用户ID")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "对话"
        verbose_name_plural = "对话"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class Message(models.Model):
    """消息模型，存储对话中的单条消息"""

    MESSAGE_TYPES = (
        ("user", "用户消息"),
        ("assistant", "助手消息"),
        ("system", "系统消息"),
    )

    # 使用整数字段替代外键
    conversation_id = models.IntegerField("对话ID")
    content = models.TextField("内容")
    message_type = models.CharField("消息类型", max_length=10, choices=MESSAGE_TYPES)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    # 不再使用ManyToManyField，改为通过MessageDocumentReference手动关联

    class Meta:
        verbose_name = "消息"
        verbose_name_plural = "消息"
        ordering = ["conversation_id", "created_at"]

    def __str__(self):
        return f"{self.get_message_type_display()} - {self.content[:50]}"


class MessageDocumentReference(models.Model):
    """消息与文档的关联模型，存储消息引用的文档及相关信息"""

    # 使用整数字段替代外键
    message_id = models.IntegerField("消息ID")
    document_id = models.IntegerField("文档ID")
    relevance_score = models.FloatField("相关性分数", default=0.0)
    chunk_indices = models.JSONField("引用的块索引", default=list)

    class Meta:
        verbose_name = "消息文档引用"
        verbose_name_plural = "消息文档引用"
        unique_together = ("message_id", "document_id")

    def __str__(self):
        return f"消息ID:{self.message_id} -> 文档ID:{self.document_id}"
