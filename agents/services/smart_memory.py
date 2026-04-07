"""
智能记忆管理 - 基于相关性和重要性的记忆保留 + 数据库持久化

替换简单的buffer_window/summary模式，实现动态记忆管理：
- 保留高相关性的历史记忆
- 保留高重要性的用户交互
- 自动压缩低重要性的内容
- 持久化到数据库，跨会话加载

兼容LangChain ConversationMemory接口
"""

from typing import Any, Dict, Optional
from datetime import datetime, timedelta
import re
import json
from loguru import logger

# 兼容LangChain的消息对象
class Message:
    """基础消息类，兼容LangChain"""
    def __init__(self, content: str, msg_type: str):
        self.content = content
        self.type = msg_type


class ChatMemory:
    """聊天记忆管理 - 与SmartMemoryManager.messages同步（LangChain兼容接口）"""

    def __init__(self, messages_ref: list = None):
        """
        初始化ChatMemory

        Args:
            messages_ref: 引用SmartMemoryManager的messages列表，实现同步
        """
        self.messages_ref = messages_ref or []

    def add_user_message(self, content: str):
        """添加用户消息 - 通过引用同步到SmartMemoryManager"""
        # 直接通过messages_ref修改，不维护独立的messages列表
        self.messages_ref.append(Message(content, "human"))

    def add_ai_message(self, content: str):
        """添加AI消息 - 通过引用同步到SmartMemoryManager"""
        self.messages_ref.append(Message(content, "ai"))

    def clear(self):
        """清空消息"""
        self.messages_ref.clear()


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
    """智能记忆管理器 - LangChain兼容接口 + 数据库持久化"""

    def __init__(
        self,
        user_id: Optional[int] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[int] = None,
        max_messages: int = 20,
        importance_threshold: float = 0.3,
        max_tokens: int = 2000,
    ):
        """
        初始化智能记忆管理器

        Args:
            user_id: 用户ID（用于从DB加载历史）
            agent_id: Agent ID（用于从DB加载历史）
            conversation_id: 对话ID（可选，用于区分不同对话）
            max_messages: 最大消息保留数
            importance_threshold: 重要性阈值（低于此分数的消息可被删除）
            max_tokens: 最大token限制
        """
        self.user_id = user_id
        self.agent_id = agent_id
        self.conversation_id = conversation_id
        self.max_messages = max_messages
        self.importance_threshold = importance_threshold
        self.max_tokens = max_tokens
        self.messages = []  # 统一的消息存储
        self.chat_memory = ChatMemory(messages_ref=self.messages)
        self.memory_key = "chat_history"
        self.return_messages = True

        # 从数据库加载历史（如果提供了user_id和agent_id）
        if self.user_id and self.agent_id:
            self._load_from_db()
            if self.messages:
                logger.info(f"✓ Loaded {len(self.messages)} messages from database")

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
        """根据容量和重要性修剪消息 - 改为使用LLM压缩替代删除"""
        # 1. 如果超过最大消息数，压缩最旧的低重要性消息
        if len(self.messages) > self.max_messages:
            self._trim_by_count()

        # 2. 如果超过token限制，继续压缩低重要性消息
        if self._estimate_tokens() > self.max_tokens:
            self._trim_by_tokens()

    def _trim_by_count(self):
        """按消息数修剪 - 压缩而非删除"""
        # 计算每条消息的总分 = 内容重要性 * 新鲜度
        now = datetime.now()
        for msg in self.messages:
            recency_score = MemoryImportance.score_by_recency(msg["timestamp"], now)
            msg["total_score"] = msg["importance"] * recency_score

        # 排序：最不重要的消息排在前面
        sorted_messages = sorted(self.messages, key=lambda m: m["total_score"])

        # 压缩最不重要的消息直到达到限制
        target_count = max(self.max_messages - 2, 5)  # 至少保留5条
        to_compress = len(sorted_messages) - target_count

        if to_compress > 0:
            # 分离要压缩的消息和要保留的消息
            messages_to_compress = sorted_messages[:to_compress]
            messages_to_keep = sorted_messages[to_compress:]

            # 压缩消息
            compressed = self._compress_messages(messages_to_compress)

            # 重新组合
            self.messages = messages_to_keep
            if compressed:
                self.messages.append(compressed)

            logger.info(f"按数量修剪：压缩了{to_compress}条消息成1条压缩记录")

    def _trim_by_tokens(self):
        """按token数修剪 - 压缩而非删除"""
        now = datetime.now()
        for msg in self.messages:
            recency_score = MemoryImportance.score_by_recency(msg["timestamp"], now)
            msg["total_score"] = msg["importance"] * recency_score

        # 排序并压缩低分消息直到达到token限制
        sorted_messages = sorted(self.messages, key=lambda m: m["total_score"])

        current_tokens = self._estimate_tokens()
        messages_to_compress = []
        removed = 0

        for i, msg in enumerate(sorted_messages):
            if current_tokens <= self.max_tokens * 0.8:  # 保持在80%以下
                break
            current_tokens -= self._estimate_message_tokens(msg["content"])
            messages_to_compress.append(msg)
            removed += 1

        if removed > 0:
            # 分离要压缩的消息和要保留的消息
            remaining = [m for m in self.messages if m not in messages_to_compress]

            # 压缩消息
            compressed = self._compress_messages(messages_to_compress)

            # 重新组合
            self.messages = remaining
            if compressed:
                self.messages.append(compressed)

            logger.info(
                f"按token数修剪：压缩了{removed}条消息，当前token数：{self._estimate_tokens()}"
            )

    def _compress_messages(self, messages: list) -> Optional[dict]:
        """
        使用LLM压缩一组消息（使用阿里通义千问）

        Args:
            messages: 要压缩的消息列表

        Returns:
            压缩后的消息（包含压缩标志和原始消息数）
        """
        if not messages:
            return None

        try:
            # 构建原始对话文本
            conversation_text = "\n".join([
                f"{'用户' if m.get('type') == 'human' else '助手'}: {m.get('content')}"
                for m in messages
            ])

            # 使用项目的LLMService进行压缩
            from qa.services.llm_service import LLMService

            llm_service = LLMService(model_name="qwen-turbo")  # 压缩用快速模型

            compression_prompt = f"""请将以下对话历史压缩成一个简洁的摘要，保留关键信息：
- 用户的主要问题/需求
- 重要的数据查询或结果
- 关键的技术决策
- 任何错误或问题的解决方案

对话内容：
{conversation_text}

请输出一个简洁的摘要（不超过100字）："""

            response = llm_service.generate_response(
                query=compression_prompt,
                context="",  # 压缩不需要外部上下文
                conversation_history=None
            )

            if response.get("error"):
                logger.warning(f"LLM压缩失败: {response.get('answer')}")
                return None

            compressed_content = response.get("answer", "")

            # 获取最早和最晚的时间戳
            timestamps = [m.get("timestamp") for m in messages if m.get("timestamp")]
            earliest_time = min(timestamps) if timestamps else datetime.now()
            latest_time = max(timestamps) if timestamps else datetime.now()

            # 创建压缩记录
            compressed_msg = {
                "content": compressed_content,
                "type": "compressed_summary",  # 特殊类型标记为压缩记录
                "timestamp": latest_time,  # 使用最新的时间戳
                "importance": 0.5,  # 压缩后的消息重要性相对较低
                "original_count": len(messages),
                "compressed_from": earliest_time,
                "compressed_at": datetime.now(),
            }

            logger.info(f"✓ 已压缩{len(messages)}条消息，摘要长度：{len(compressed_content)}")
            return compressed_msg

        except Exception as e:
            logger.error(f"LLM压缩失败: {e}，将降级为删除策略")
            # 降级：压缩失败则删除
            return None


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
        top_k: int = 5,
        max_context_tokens: int = 500
    ) -> str:
        """
        检索相关记忆 - 智能压缩版

        评分策略：
        1. 关键词匹配相似度（基于query中的词）
        2. importance * recency（已有）
        3. 综合得分 = keyword_similarity * 0.5 + (importance * recency) * 0.5
        4. 智能压缩：按分数逐条加入，直到达到token限制

        Args:
            query: 当前查询文本
            top_k: 候选记忆数量
            max_context_tokens: 返回上下文的最大token数（约500tokens=2000字符）

        Returns:
            格式化的历史对话字符串（受token限制的智能压缩版本）
        """
        if not self.messages:
            return ""

        # 计算每条消息的综合分数
        now = datetime.now()
        scored_messages = []

        for msg in self.messages:
            # 跳过已压缩的消息（直接使用原始内容）
            msg_content = msg.get("content", "")

            # 1. 计算recency分数
            recency_score = MemoryImportance.score_by_recency(msg["timestamp"], now)

            # 2. 计算importance * recency
            importance_recency = msg["importance"] * recency_score

            # 3. 计算关键词匹配相似度（简单版：检查query中的词是否出现在消息中）
            query_words = set(query.lower().split())
            msg_words = set(msg_content.lower().split())

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

        # 排序并逐条加入，直到达到token限制
        scored_messages.sort(key=lambda x: x["combined_score"], reverse=True)

        # 智能压缩：按分数逐条加入上下文，直到达到token限制
        context_lines = ["【历史相关对话】"]
        total_tokens = self._estimate_message_tokens(context_lines[0])
        included_count = 0

        for msg in scored_messages[:top_k]:
            # 标记压缩消息
            if msg.get("type") == "compressed_summary":
                role = "📦 压缩摘要"
                original_info = f"(原{msg.get('original_count', '?')}条消息)"
            else:
                role = "用户" if msg["type"] == "human" else "助手"
                original_info = ""

            # 计算当前消息的tokens
            content = msg["content"]
            msg_tokens = self._estimate_message_tokens(f"{role}: {content}")

            # 如果加上这条消息会超过限制，进行截断
            if total_tokens + msg_tokens > max_context_tokens and included_count > 0:
                # 尝试截断消息内容
                max_content_len = max(50, int((max_context_tokens - total_tokens) * 4))  # 4字符=1token
                content = content[:max_content_len] + "..." if len(content) > max_content_len else content
                msg_tokens = self._estimate_message_tokens(f"{role}: {content}")

                if total_tokens + msg_tokens <= max_context_tokens:
                    context_lines.append(f"{role}: {content} {original_info}".strip())
                    total_tokens += msg_tokens
                    included_count += 1
                break  # 达到压缩限制
            else:
                # 截断过长的消息（但保留更长内容，直到token限制）
                if len(content) > 300:
                    content = content[:300] + "..."

                context_lines.append(f"{role}: {content} {original_info}".strip())
                total_tokens += msg_tokens
                included_count += 1

        # 如果有更多记忆但被压缩了，添加提示
        if included_count < len(scored_messages):
            context_lines.append(f"... (还有{len(scored_messages) - included_count}条历史记录)")

        if included_count == 0:
            return ""

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

    def _load_from_db(self):
        """从数据库加载历史消息"""
        if not self.user_id or not self.agent_id:
            logger.warning("Cannot load from DB: user_id or agent_id is missing")
            return

        try:
            from agents.models import AgentMemory

            # 查询记忆数据库
            query = AgentMemory.objects.filter(
                user_id=self.user_id,
                agent_id=self.agent_id
            )

            # 如果指定了conversation_id，则过滤
            if self.conversation_id:
                query = query.filter(conversation_id=self.conversation_id)

            # 按创建时间排序（最旧的在前）
            memories = query.order_by("created_at")[:self.max_messages]

            # 转换为消息格式
            for memory in memories:
                try:
                    memory_data = memory.memory_data or {}
                    if isinstance(memory_data, str):
                        memory_data = json.loads(memory_data)

                    # 假设memory_data格式为 {"messages": [{"type": "human", "content": "..."}, ...]}
                    if "messages" in memory_data:
                        for msg in memory_data["messages"]:
                            self.messages.append({
                                "content": msg.get("content", ""),
                                "type": msg.get("type", "human"),
                                "timestamp": datetime.fromisoformat(msg["timestamp"]) if isinstance(msg.get("timestamp"), str) else msg.get("timestamp", datetime.now()),
                                "importance": MemoryImportance.score_message(msg.get("content", ""), msg.get("type", "human")),
                            })
                except Exception as e:
                    logger.warning(f"Failed to parse memory data: {e}")

            logger.info(f"✓ Loaded {len(self.messages)} messages from AgentMemory")

        except Exception as e:
            logger.error(f"Failed to load from database: {e}")

    def save_to_db(self):
        """将当前消息保存到数据库"""
        if not self.user_id or not self.agent_id:
            logger.warning("Cannot save to DB: user_id or agent_id is missing")
            return

        try:
            from agents.models import AgentMemory

            # 将消息转换为可JSON序列化的格式
            messages_data = []
            for msg in self.messages:
                messages_data.append({
                    "type": msg.get("type"),
                    "content": msg.get("content"),
                    "timestamp": msg.get("timestamp").isoformat() if isinstance(msg.get("timestamp"), datetime) else str(msg.get("timestamp")),
                })

            # 保存到数据库
            memory_record, created = AgentMemory.objects.update_or_create(
                user_id=self.user_id,
                agent_id=self.agent_id,
                memory_key="chat_history",
                conversation_id=self.conversation_id,
                defaults={
                    "memory_data": {"messages": messages_data},
                    "expires_at": datetime.now() + timedelta(days=30)  # 30天后过期
                }
            )

            logger.info(f"✓ {'Created' if created else 'Updated'} AgentMemory record with {len(self.messages)} messages")

        except Exception as e:
            logger.error(f"Failed to save to database: {e}")

