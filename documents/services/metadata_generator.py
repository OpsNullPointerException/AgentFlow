"""
使用LLM生成文档元数据（summary、keywords、intent）
"""

import json
from typing import Any, Dict, List, Optional
from loguru import logger

from qa.services.llm_service import LLMService


class MetadataGenerator:
    """使用LLM生成文档元数据"""

    def __init__(self):
        """初始化元数据生成器"""
        self.llm_service = LLMService(model_name="qwen-turbo")

    def generate_chunk_metadata(
        self,
        chunk_content: str,
        title: Optional[str] = None,
        section_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        为单个文档块生成元数据

        Args:
            chunk_content: 块内容
            title: 块的标题
            section_path: 块的章节路径

        Returns:
            包含 summary、keywords、intent 的字典
        """
        try:
            context = f"标题: {title}\n章节: {section_path}" if title else ""

            prompt = f"""请分析以下文档内容，生成结构化元数据。

{context}

内容：
{chunk_content[:1000]}

请返回JSON格式，包含三个字段：
1. summary: 50-100字的摘要
2. keywords: 5-8个关键词列表
3. intent: 内容意图（说明/指南/警告/示例/概述）

{{
    "summary": "...",
    "keywords": ["关键词1", "关键词2", ...],
    "intent": "说明"
}}

只返回JSON，不要其他内容。"""

            response = self.llm_service.generate_response(
                query=prompt,
                context="",
                conversation_history=None
            )

            if response.get("error"):
                logger.warning(f"元数据生成失败: {response.get('error_message')}")
                return self._fallback_metadata(chunk_content)

            try:
                answer = response["answer"].strip()
                if answer.startswith("```"):
                    answer = answer.split("```")[1]
                    if answer.startswith("json"):
                        answer = answer[4:]
                answer = answer.strip()

                metadata = json.loads(answer)
                # 确保只返回这三个字段
                return {
                    "summary": metadata.get("summary", ""),
                    "keywords": metadata.get("keywords", []),
                    "intent": metadata.get("intent", "")
                }
            except json.JSONDecodeError as e:
                logger.warning(f"解析元数据JSON失败: {e}")
                return self._fallback_metadata(chunk_content)

        except Exception as e:
            logger.error(f"生成元数据失败: {e}")
            return self._fallback_metadata(chunk_content)

    def generate_batch_metadata(
        self,
        chunks: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """批量生成文档块的元数据"""
        results = []

        for i, chunk in enumerate(chunks):
            metadata = self.generate_chunk_metadata(
                chunk_content=chunk.get("content", ""),
                title=chunk.get("title"),
                section_path=chunk.get("section_path")
            )
            results.append(metadata)

            if (i + 1) % 5 == 0:
                logger.info(f"已处理 {i + 1}/{len(chunks)} 个块")

        return results

    @staticmethod
    def _fallback_metadata(content: str) -> Dict[str, Any]:
        """回退元数据（无LLM调用）"""
        words = content.split()[:20]
        return {
            "summary": content[:100],
            "keywords": [w for w in words if len(w) > 3][:8],
            "intent": ""
        }

