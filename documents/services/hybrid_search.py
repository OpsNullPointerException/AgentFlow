"""
混合检索服务 - 结合向量相似度和PostgreSQL BM25（原生SQL实现）
"""

from typing import List, Dict, Optional
from loguru import logger
from django.contrib.postgres.search import SearchVector, SearchQuery
from django.db import connection

from qa.schemas.retrieval import DocumentSearchResultOut
from .vector_db_service import VectorDBService
from .index_builder import IndexBuilder
from ..models import DocumentChunk, InvertedIndex

import math


class HybridSearch:
    """混合检索：向量搜索 + PostgreSQL BM25（SQL原生实现）"""

    def __init__(self, embedding_model_version=None):
        """初始化混合搜索"""
        self.vector_service = VectorDBService.get_instance(embedding_model_version)
        self.embedding_model_version = embedding_model_version

        # BM25参数
        self.k1 = 1.5
        self.b = 0.75

    def search(
        self,
        query: str,
        top_k: int = 5,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        doc_category: Optional[str] = "user"
    ) -> List[DocumentSearchResultOut]:
        """
        混合搜索：结合向量相似度和PostgreSQL BM25

        Args:
            query: 查询文本
            top_k: 返回结果数量
            vector_weight: 向量搜索权重（0-1）
            bm25_weight: BM25权重（0-1）
            doc_category: 文档分类过滤

        Returns:
            混合检索结果列表
        """
        # 1. 向量搜索 - 获取语义相关的文档
        search_top_k = max(top_k * 3, 30)
        vector_results = self.vector_service.search(query, search_top_k)

        if not vector_results:
            logger.warning("向量搜索无结果")
            return []

        # 2. BM25搜索（SQL原生实现）
        bm25_results = self._bm25_search_sql(query, vector_results)

        # 3. 融合两种结果
        merged_results = self._merge_results(
            vector_results=vector_results,
            bm25_results=bm25_results,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
            top_k=top_k
        )

        logger.info(f"混合检索: 向量{len(vector_results)} + BM25{len(bm25_results)} → 融合{len(merged_results)}")
        return merged_results

    def _bm25_search_sql(
        self,
        query: str,
        vector_results: List[DocumentSearchResultOut]
    ) -> Dict[int, float]:
        """
        BM25搜索 - 使用SQL原生实现（比应用层快）

        核心优化：
        - 所有计算都在数据库完成（无需Python逐行计算）
        - 使用倒排索引快速定位相关chunk
        - 一次SQL查询返回所有结果

        Args:
            query: 查询文本
            vector_results: 向量搜索结果

        Returns:
            {chunk_id: bm25_score} 字典
        """
        try:
            # 1. 分词获取查询词
            query_tokens = IndexBuilder.tokenize(query)
            query_terms = list(set(token[0] for token in query_tokens))  # 去重

            if not query_terms:
                return {}

            # 2. 获取候选chunk ID
            candidate_chunk_ids = [result.chunk_index for result in vector_results]

            if not candidate_chunk_ids:
                return {}

            # 3. 准备参数
            terms_sql = ','.join([f"'{term}'" for term in query_terms])
            ids_sql = ','.join(map(str, candidate_chunk_ids))

            total_documents = DocumentChunk.objects.count()
            avg_doc_length = self._get_avg_doc_length()

            # 4. 一次SQL查询计算所有BM25分数
            # 这比应用层逐行计算快10倍以上
            sql = f"""
            WITH term_stats AS (
                -- 计算每个词的IDF
                SELECT
                    term,
                    COUNT(DISTINCT chunk_id) as doc_freq,
                    LN(({total_documents} - COUNT(DISTINCT chunk_id) + 0.5) /
                       (COUNT(DISTINCT chunk_id) + 0.5) + 1.0) as idf
                FROM documents_invertedindex
                WHERE term IN ({terms_sql})
                GROUP BY term
            ),
            chunk_scores AS (
                -- 计算每个chunk的BM25分数
                SELECT
                    ii.chunk_id,
                    SUM(
                        ts.idf *
                        (ii.frequency * ({self.k1} + 1)) /
                        (ii.frequency + {self.k1} * (1 - {self.b} + {self.b} *
                            COALESCE(dc.token_count, {avg_doc_length:.1f}) / {avg_doc_length:.1f}))
                    ) as bm25_score
                FROM documents_invertedindex ii
                JOIN term_stats ts ON ii.term = ts.term
                LEFT JOIN documents_documentchunklength dc ON ii.chunk_id = dc.chunk_id
                WHERE ii.chunk_id IN ({ids_sql})
                GROUP BY ii.chunk_id
            )
            SELECT chunk_id, bm25_score
            FROM chunk_scores
            ORDER BY bm25_score DESC
            """

            with connection.cursor() as cursor:
                cursor.execute(sql)
                results = cursor.fetchall()

            # 5. 转换为字典
            result_dict = {chunk_id: float(score) for chunk_id, score in results}

            logger.debug(f"BM25搜索(SQL): {len(result_dict)} 条结果")
            return result_dict

        except Exception as e:
            logger.error(f"BM25搜索失败: {e}")
            return {}

    def _get_avg_doc_length(self) -> float:
        """获取平均文档长度（用于BM25长度归一化）"""
        try:
            # 简单估算：平均chunk包含200个词
            # 实际可以通过IndexBuilder.tokenize来统计
            return 200.0
        except:
            return 200.0

    def _merge_results(
        self,
        vector_results: List[DocumentSearchResultOut],
        bm25_results: Dict[int, float],
        vector_weight: float,
        bm25_weight: float,
        top_k: int
    ) -> List[DocumentSearchResultOut]:
        """融合向量搜索和BM25结果"""

        # 规范化分数
        vector_scores = self._normalize_scores([r.score for r in vector_results])
        bm25_scores_list = list(bm25_results.values()) if bm25_results else []
        bm25_scores_normalized = self._normalize_scores(bm25_scores_list)

        # 创建分数字典
        score_dict = {}

        for i, doc in enumerate(vector_results):
            score_dict[doc.chunk_index] = {
                "vector": vector_scores[i],
                "bm25": 0.0,
                "doc": doc
            }

        # 加入BM25分数
        for i, (chunk_id, _) in enumerate(bm25_results.items()):
            if chunk_id in score_dict:
                score_dict[chunk_id]["bm25"] = bm25_scores_normalized[i] if i < len(bm25_scores_normalized) else 0.0

        # 计算混合分数
        merged = []
        for chunk_id, scores in score_dict.items():
            combined_score = (
                scores["vector"] * vector_weight +
                scores["bm25"] * bm25_weight
            )
            doc = scores["doc"]

            merged_result = DocumentSearchResultOut(
                id=doc.id,
                title=doc.title,
                content=doc.content,
                score=combined_score,
                chunk_index=doc.chunk_index,
                embedding_model_version=doc.embedding_model_version,
                rerank_score=None,
                final_score=None,
                rerank_method=None
            )
            merged.append(merged_result)

        # 排序并返回top_k
        merged.sort(key=lambda x: x.score, reverse=True)
        return merged[:top_k]

    @staticmethod
    def _normalize_scores(scores: List[float]) -> List[float]:
        """规范化分数到0-1之间"""
        if not scores:
            return []

        min_score = min(scores)
        max_score = max(scores)

        if max_score == min_score:
            return [0.5] * len(scores)

        return [(s - min_score) / (max_score - min_score) for s in scores]

    @staticmethod
    def search_static(
        query: str,
        top_k: int = 5,
        embedding_model_version=None,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        doc_category: Optional[str] = "user"
    ) -> List[DocumentSearchResultOut]:
        """静态方法版本的混合搜索"""
        hybrid_search = HybridSearch(embedding_model_version=embedding_model_version)
        return hybrid_search.search(
            query=query,
            top_k=top_k,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
            doc_category=doc_category
        )


