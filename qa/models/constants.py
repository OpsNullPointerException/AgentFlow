from enum import Enum


class MessageType(str, Enum):
    """消息类型枚举"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# 枚举与Django模型选择映射
MESSAGE_TYPE_CHOICES = (
    (MessageType.USER.value, "用户消息"),
    (MessageType.ASSISTANT.value, "助手消息"),
    (MessageType.SYSTEM.value, "系统消息"),
)
