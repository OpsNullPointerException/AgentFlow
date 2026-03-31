"""
倒排索引构建和管理
"""

import re
import json
from typing import List, Dict, Tuple
from loguru import logger

import jieba

from ..models import InvertedIndex, DocumentChunk

# 中文停用词集合
CHINESE_STOPWORDS = {
    '的', '一', '是', '在', '了', '和', '人', '这', '中', '大',
    '为', '上', '个', '国', '我', '以', '要', '他', '时', '来',
    '用', '们', '生', '到', '作', '地', '于', '出', '就', '分',
    '对', '成', '会', '可', '主', '发', '年', '动', '同', '工',
    '也', '能', '下', '过', '民', '前', '面', '内', '现', '然',
    '走', '很', '给', '好', '看', '生', '产', '实', '发', '自',
    '所', '还', '把', '也', '向', '造', '进', '又', '想', '及',
    '其', '者', '已', '都', '便', '几', '体', '却', '应', '去',
    '两', '样', '式', '更', '最', '得', '作', '经', '十', '分',
    '别', '她', '那', '会', '我', '时', '有', '个', '就', '说',
    '着', '多', '然', '位', '同', '高', '当', '将', '而', '问',
    '各', '无', '把', '你', '到', '着', '些', '或', '提', '因',
    '应', '所', '如', '如何', '什么', '哪', '怎样', '怎么', '哪些',
    '什么', '为什么', '何', '哪儿', '哪里', '如', '虽然', '但是',
    '则', '否则', '因为', '所以', '即', '而是', '还是', '不是',
    '根本', '本来', '原来', '早就', '已经', '再', '又', '还',
    '才', '都', '一样', '也', '并', '并且', '同时', '但', '然而',
    '与', '及', '或', '或者', '要么', '要不', '宁可', '与其',
    '不如', '不然', '除非', '除了', '若', '除', '若非', '如果',
    '要是', '倘若', '假如', '假设', '设', '设若', '倘', '幸亏',
    '亏得', '幸好', '好在', '算是', '算得', '总算', '终于', '到底',
}


class IndexBuilder:
    """构建和维护倒排索引"""

    @staticmethod
    def tokenize(text: str) -> List[Tuple[str, int]]:
        """
        使用jieba分词，返回(词, 位置)列表

        Args:
            text: 文本

        Returns:
            [(word, position), ...] 列表
        """
        tokens = []
        text_lower = text.lower()
        position = 0

        # 使用jieba分词
        for word in jieba.cut(text_lower):
            # 过滤：
            # 1. 停用词
            # 2. 长度过短的词（<=1）
            # 3. 纯数字和标点
            if (word not in CHINESE_STOPWORDS and
                len(word) > 1 and
                not re.match(r'^[\d\W]+$', word)):
                tokens.append((word, position))

            position += len(word)

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
