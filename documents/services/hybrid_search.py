"""
混合检索服务 - 结合向量相似度和PostgreSQL全文搜索（pg_search）
"""

from typing import List, Dict, Optional
from loguru import logger
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q, F

from qa.schemas.retrieval import DocumentSearchResultOut
from .vector_db_service import VectorDBService
from ..models import DocumentChunk


class HybridSearch:
    """混合检索：向量搜索 + PostgreSQL全文搜索（pg_search）"""

    def __init__(self, embedding_model_version=None):
        """初始化混合搜索"""
        self.vector_service = VectorDBService.get_instance(embedding_model_version)
        self.embedding_model_version = embedding_model_version

    def search(
        self,
        query: str,
        top_k: int = 5,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        doc_category: Optional[str] = "user"
    ) -> List[DocumentSearchResultOut]:
        """
        混合搜索：结合向量相似度和PostgreSQL全文搜索

        Args:
            query: 查询文本
            top_k: 返回结果数量
            vector_weight: 向量搜索权重（0-1）
            bm25_weight: PostgreSQL全文搜索权重（0-1）
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

        # 2. PostgreSQL全文搜索 - 获取关键词匹配的文档
        pg_results = self._pg_fulltext_search(query, vector_results)

        # 3. 融合两种结果
        merged_results = self._merge_results(
            vector_results=vector_results,
            pg_results=pg_results,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
            top_k=top_k
        )

        logger.info(f"混合检索: 向量{len(vector_results)} + 全文搜索{len(pg_results)} → 融合{len(merged_results)}")
        return merged_results

    def _pg_fulltext_search(
        self,
        query: str,
        vector_results: List[DocumentSearchResultOut]
    ) -> Dict[int, float]:
        """
        PostgreSQL全文搜索（pg_search）

        Args:
            query: 查询文本
            vector_results: 向量搜索结果（用于融合，不用于过滤）

        Returns:
            {chunk_id: rank_score} 字典
        """
        try:
            # 使用PostgreSQL全文搜索
            search_query = SearchQuery(query, search_type='websearch')

            # 直接全表扫描（数据量小，无需候选集限制）
            pg_results = DocumentChunk.objects.annotate(
                rank=SearchRank(SearchVector('content', config='chinese'), search_query)
            ).filter(
                content__search=search_query
            ).values('id', 'rank').order_by('-rank')

            # 转换为字典 {chunk_id: rank}
            result_dict = {result['id']: result['rank'] for result in pg_results}

            logger.debug(f"PostgreSQL全文搜索: {len(pg_results)} 条结果")
            return result_dict

        except Exception as e:
            logger.error(f"PostgreSQL全文搜索失败: {e}")
            return {}

    def _merge_results(
        self,
        vector_results: List[DocumentSearchResultOut],
        pg_results: Dict[int, float],
        vector_weight: float,
        bm25_weight: float,
        top_k: int
    ) -> List[DocumentSearchResultOut]:
        """融合向量搜索和PostgreSQL全文搜索结果"""

        # 规范化向量分数
        vector_scores = self._normalize_scores([r.score for r in vector_results])

        # 规范化PostgreSQL全文搜索分数
        pg_scores_list = list(pg_results.values()) if pg_results else []
        pg_scores_normalized = self._normalize_scores(pg_scores_list)

        # 创建分数字典
        score_dict = {}

        # 加入向量搜索结果
        for i, doc in enumerate(vector_results):
            score_dict[doc.chunk_index] = {
                "vector": vector_scores[i],
                "pg_rank": 0.0,
                "doc": doc
            }

        # 加入PostgreSQL全文搜索结果
        for i, (chunk_id, _) in enumerate(pg_results.items()):
            if chunk_id in score_dict:
                score_dict[chunk_id]["pg_rank"] = pg_scores_normalized[i] if i < len(pg_scores_normalized) else 0.0

        # 计算混合分数
        merged = []
        for chunk_id, scores in score_dict.items():
            combined_score = (
                scores["vector"] * vector_weight +
                scores["pg_rank"] * bm25_weight
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

