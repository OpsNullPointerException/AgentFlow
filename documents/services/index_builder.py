"""
倒排索引构建和管理
"""

import re
import json
from typing import List, Dict, Tuple
from loguru import logger

from ..models import InvertedIndex, DocumentChunk


class IndexBuilder:
    """构建和维护倒排索引"""

    @staticmethod
    def tokenize(text: str) -> List[Tuple[str, int]]:
        """
        分词，返回(词, 位置)列表

        Args:
            text: 文本

        Returns:
            [(word, position), ...] 列表
        """
        tokens = []
        text_lower = text.lower()

        # 分词策略：中文按字分，英文按词分
        i = 0
        while i < len(text_lower):
            if '\u4e00' <= text_lower[i] <= '\u9fff':  # 中文字符
                # 过滤掉标点符号
                if not re.match(r'[，。！？；：""''（）【】]', text_lower[i]):
                    tokens.append((text_lower[i], i))
                i += 1
            else:
                # 英文词
                j = i
                while j < len(text_lower) and not ('\u4e00' <= text_lower[j] <= '\u9fff'):
                    j += 1
                word = text_lower[i:j]
                # 提取英文单词（去掉标点等）
                words = re.findall(r'[a-z0-9]+', word)
                for w in words:
                    if len(w) > 1:  # 只保留长度>1的词
                        tokens.append((w, i))
                i = j

        return tokens

    @staticmethod
    def build_index_for_chunk(chunk: DocumentChunk) -> None:
        """
        为单个chunk构建倒排索引

        Args:
            chunk: DocumentChunk对象
        """
        try:
            # 分词
            tokens = IndexBuilder.tokenize(chunk.content)

            if not tokens:
                logger.debug(f"Chunk {chunk.id} 无有效分词")
                return

            # 统计词频和位置
            term_info = {}
            for word, pos in tokens:
                if word not in term_info:
                    term_info[word] = {"frequency": 0, "positions": []}
                term_info[word]["frequency"] += 1
                term_info[word]["positions"].append(pos)

            # 批量插入或更新倒排索引
            for term, info in term_info.items():
                InvertedIndex.objects.update_or_create(
                    term=term,
                    chunk_id=chunk.id,
                    defaults={
                        "frequency": info["frequency"],
                        "positions": json.dumps(info["positions"])
                    }
                )

            logger.debug(f"Chunk {chunk.id} 建立索引成功，包含{len(term_info)}个不同的词")

        except Exception as e:
            logger.error(f"为Chunk {chunk.id} 构建索引失败: {e}")

    @staticmethod
    def build_index_for_document(document_id: int) -> None:
        """
        为整个文档的所有chunk构建倒排索引

        Args:
            document_id: 文档ID
        """
        try:
            chunks = DocumentChunk.objects.filter(document_id=document_id)

            for chunk in chunks:
                IndexBuilder.build_index_for_chunk(chunk)

            logger.info(f"文档{document_id}的倒排索引构建完成，共{chunks.count()}个chunks")

        except Exception as e:
            logger.error(f"为文档{document_id}构建索引失败: {e}")

    @staticmethod
    def delete_index_for_chunk(chunk_id: int) -> None:
        """删除chunk的倒排索引"""
        try:
            deleted_count, _ = InvertedIndex.objects.filter(chunk_id=chunk_id).delete()
            logger.debug(f"删除Chunk {chunk_id} 的倒排索引: {deleted_count}条记录")
        except Exception as e:
            logger.error(f"删除Chunk {chunk_id} 的倒排索引失败: {e}")

    @staticmethod
    def delete_index_for_document(document_id: int) -> None:
        """删除文档的所有倒排索引"""
        try:
            # 获取所有chunk_id
            chunk_ids = DocumentChunk.objects.filter(document_id=document_id).values_list("id", flat=True)

            deleted_count, _ = InvertedIndex.objects.filter(chunk_id__in=chunk_ids).delete()
            logger.info(f"删除文档{document_id}的倒排索引: {deleted_count}条记录")

        except Exception as e:
            logger.error(f"删除文档{document_id}的倒排索引失败: {e}")

    @staticmethod
    def rebuild_all_indexes() -> None:
        """重建所有倒排索引（慎用，耗时操作）"""
        try:
            logger.warning("开始重建所有倒排索引...")

            # 清空现有索引
            InvertedIndex.objects.all().delete()

            # 重建所有chunks的索引
            chunks = DocumentChunk.objects.all()
            total = chunks.count()

            for i, chunk in enumerate(chunks):
                IndexBuilder.build_index_for_chunk(chunk)
                if (i + 1) % 100 == 0:
                    logger.info(f"已处理 {i + 1}/{total} 个chunks")

            logger.info(f"倒排索引重建完成，共{total}个chunks")

        except Exception as e:
            logger.error(f"重建倒排索引失败: {e}")
