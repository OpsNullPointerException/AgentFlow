"""
智能记忆管理 - 基于相关性和重要性的记忆保留

替换简单的buffer_window/summary模式，实现动态记忆管理：
- 保留高相关性的历史记忆
- 保留高重要性的用户交互
- 自动压缩低重要性的内容

兼容LangChain ConversationMemory接口
"""

from typing import Any, Dict, Optional
from datetime import datetime
import re
from loguru import logger

# 兼容LangChain的消息对象
class Message:
    """基础消息类，兼容LangChain"""
    def __init__(self, content: str, msg_type: str):
        self.content = content
        self.type = msg_type


class ChatMemory:
    """聊天记忆管理，提供LangChain兼容接口"""

    def __init__(self):
        self.messages = []

    def add_user_message(self, content: str):
        """添加用户消息"""
        self.messages.append(Message(content, "human"))

    def add_ai_message(self, content: str):
        """添加AI消息"""
        self.messages.append(Message(content, "ai"))

    def clear(self):
        """清空消息"""
        self.messages = []


class MemoryImportance:
    """记忆重要性评分"""

    @staticmethod
    def score_message(message: str, message_type: str) -> float:
        """
        评估消息的重要性评分 (0-1)

        Args:
            message: 消息内容
            message_type: 'human' 或 'ai'

        Returns:
            重要性评分
        """
        score = 0.0

        # 基础分
        if message_type == "human":
            score = 0.5  # 用户消息基础分
        else:
            score = 0.3  # AI消息基础分

        # 长度权重 - 更长的消息通常更重要
        length_bonus = min(len(message) / 500, 0.2)
        score += length_bonus

        # 特殊关键词权重
        keywords = {
            "重要": 0.3,
            "关键": 0.25,
            "错误": 0.2,
            "问题": 0.15,
            "解决": 0.15,
            "结果": 0.1,
            "成功": 0.1,
            "失败": 0.15,
        }

        for keyword, weight in keywords.items():
            if keyword in message.lower():
                score += weight

        # 数据查询相关权重
        if re.search(r"SELECT|FROM|WHERE|COUNT|SUM|GROUP", message, re.I):
            score += 0.2
        if re.search(r"\d+\s*行|\d+\s*条|\d+%", message):
            score += 0.1

        return min(score, 1.0)

    @staticmethod
    def score_by_recency(message_time: datetime, current_time: datetime) -> float:
        """
        基于新鲜度评分

        Args:
            message_time: 消息时间
            current_time: 当前时间

        Returns:
            新鲜度评分 (0-1)
        """
        age_hours = (current_time - message_time).total_seconds() / 3600
        # 最近1小时：1.0，最近24小时衰减到0.5，超过24小时：0.2
        if age_hours <= 1:
            return 1.0
        elif age_hours <= 24:
            return 0.5 + 0.5 * (1 - age_hours / 24)
        else:
            return 0.2


class SmartMemoryManager:
    """智能记忆管理器 - LangChain兼容接口"""

    def __init__(
        self,
        max_messages: int = 20,
        importance_threshold: float = 0.3,
        max_tokens: int = 2000,
    ):
        """
        初始化智能记忆管理器

        Args:
            max_messages: 最大消息保留数
            importance_threshold: 重要性阈值（低于此分数的消息可被删除）
            max_tokens: 最大token限制
        """
        self.max_messages = max_messages
        self.importance_threshold = importance_threshold
        self.max_tokens = max_tokens
        self.messages = []  # 内部消息存储
        self.chat_memory = ChatMemory()  # LangChain兼容接口
        self.memory_key = "chat_history"
        self.return_messages = True

    def add_message(
        self, content: str, message_type: str, timestamp: Optional[datetime] = None
    ):
        """添加消息到记忆"""
        if timestamp is None:
            timestamp = datetime.now()

        message = {
            "content": content,
            "type": message_type,
            "timestamp": timestamp,
            "importance": MemoryImportance.score_message(content, message_type),
        }

        self.messages.append(message)
        # 同时更新LangChain兼容的chat_memory
        if message_type == "human":
            self.chat_memory.add_user_message(content)
        else:
            self.chat_memory.add_ai_message(content)

        self._trim_messages()

    def _trim_messages(self):
        """根据容量和重要性修剪消息"""
        # 1. 如果超过最大消息数，删除最旧的低重要性消息
        if len(self.messages) > self.max_messages:
            self._trim_by_count()

        # 2. 如果超过token限制，继续删除低重要性消息
        if self._estimate_tokens() > self.max_tokens:
            self._trim_by_tokens()

        # 3. 同步到chat_memory
        self._sync_to_chat_memory()

    def _trim_by_count(self):
        """按消息数修剪"""
        # 计算每条消息的总分 = 内容重要性 * 新鲜度
        now = datetime.now()
        for msg in self.messages:
            recency_score = MemoryImportance.score_by_recency(msg["timestamp"], now)
            msg["total_score"] = msg["importance"] * recency_score

        # 排序：最不重要的消息排在前面
        sorted_messages = sorted(self.messages, key=lambda m: m["total_score"])

        # 删除最不重要的消息直到达到限制
        target_count = max(self.max_messages - 2, 5)  # 至少保留5条
        to_remove = len(sorted_messages) - target_count

        if to_remove > 0:
            self.messages = sorted_messages[to_remove:]
            logger.info(f"按数量修剪：删除了{to_remove}条消息")

    def _trim_by_tokens(self):
        """按token数修剪"""
        now = datetime.now()
        for msg in self.messages:
            recency_score = MemoryImportance.score_by_recency(msg["timestamp"], now)
            msg["total_score"] = msg["importance"] * recency_score

        # 排序并删除低分消息直到达到token限制
        sorted_messages = sorted(self.messages, key=lambda m: m["total_score"])

        current_tokens = self._estimate_tokens()
        removed = 0

        for i, msg in enumerate(sorted_messages):
            if current_tokens <= self.max_tokens * 0.8:  # 保持在80%以下
                break
            current_tokens -= self._estimate_message_tokens(msg["content"])
            removed += 1

        if removed > 0:
            self.messages = sorted_messages[removed:]
            logger.info(
                f"按token数修剪：删除了{removed}条消息，当前token数：{self._estimate_tokens()}"
            )

    def _sync_to_chat_memory(self):
        """同步内部消息到chat_memory（LangChain兼容）"""
        self.chat_memory.clear()
        for msg in self.messages:
            if msg["type"] == "human":
                self.chat_memory.add_user_message(msg["content"])
            else:
                self.chat_memory.add_ai_message(msg["content"])

    def _estimate_tokens(self) -> int:
        """估算所有消息的总token数"""
        return sum(self._estimate_message_tokens(msg["content"]) for msg in self.messages)

    @staticmethod
    def _estimate_message_tokens(content: str) -> int:
        """估算消息的token数（粗略估算：4字符 = 1token）"""
        return len(content) // 4

    def get_messages(self) -> list[dict[str, str]]:
        """获取当前保留的消息"""
        return [{"type": msg["type"], "content": msg["content"]} for msg in self.messages]

    def get_summary(self) -> dict[str, Any]:
        """获取记忆摘要"""
        return {
            "total_messages": len(self.messages),
            "total_tokens": self._estimate_tokens(),
            "high_importance": len([m for m in self.messages if m["importance"] > 0.6]),
            "messages": self.get_messages(),
        }

    def retrieve_relevant_memory(
        self,
        query: str,
        top_k: int = 5
    ) -> str:
        """
        检索相关记忆

        评分策略：
        1. 关键词匹配相似度（基于query中的词）
        2. importance * recency（已有）
        3. 综合得分 = keyword_similarity * 0.5 + (importance * recency) * 0.5

        Args:
            query: 当前查询文本
            top_k: 返回的最相关记忆数量

        Returns:
            格式化的历史对话字符串
        """
        if not self.messages:
            return ""

        # 计算每条消息的综合分数
        now = datetime.now()
        scored_messages = []

        for msg in self.messages:
            # 1. 计算recency分数
            recency_score = MemoryImportance.score_by_recency(msg["timestamp"], now)

            # 2. 计算importance * recency
            importance_recency = msg["importance"] * recency_score

            # 3. 计算关键词匹配相似度（简单版：检查query中的词是否出现在消息中）
            query_words = set(query.lower().split())
            msg_words = set(msg["content"].lower().split())

            if query_words:
                # 计算Jaccard相似度：交集 / 并集
                intersection = len(query_words & msg_words)
                union = len(query_words | msg_words)
                keyword_similarity = intersection / union if union > 0 else 0.0
            else:
                keyword_similarity = 0.0

            # 4. 综合得分 = 关键词相似度 * 0.5 + importance*recency * 0.5
            combined_score = keyword_similarity * 0.5 + importance_recency * 0.5

            scored_messages.append({
                **msg,
                "combined_score": combined_score
            })

        # 排序并取top_k
        scored_messages.sort(key=lambda x: x["combined_score"], reverse=True)
        top_messages = scored_messages[:top_k]

        # 格式化为字符串
        if not top_messages:
            return ""

        context_lines = ["【历史相关对话】"]
        for msg in top_messages:
            role = "用户" if msg["type"] == "human" else "助手"
            # 截断过长的消息
            content = msg["content"][:200] + "..." if len(msg["content"]) > 200 else msg["content"]
            context_lines.append(f"{role}: {content}")

        return "\n".join(context_lines)

    def get_stats(self) -> dict[str, Any]:
        """获取记忆统计（兼容LangChain接口）"""
        return {
            "total_conversations": len(self.messages),
            "total_users": 1,  # 简化：总是1
            "total_messages": len(self.messages),
            "total_tokens": self._estimate_tokens(),
        }

    def clear(self):
        """清空所有消息"""
        self.messages = []
        self.chat_memory.clear()
        logger.info("记忆已清空")

