"""
混合检索服务 - 结合向量相似度和BM25关键词检索（基于倒排索引）
"""

import math
from typing import List, Dict, Optional
from collections import defaultdict
from loguru import logger

from qa.schemas.retrieval import DocumentSearchResultOut
from .vector_db_service import VectorDBService
from .index_builder import IndexBuilder
from ..models import InvertedIndex, DocumentChunk


class HybridSearch:
    """混合检索：向量搜索 + BM25关键词搜索（基于倒排索引）"""

    def __init__(self, embedding_model_version=None):
        """初始化混合搜索"""
        self.vector_service = VectorDBService.get_instance(embedding_model_version)
        self.embedding_model_version = embedding_model_version

    def search(
        self,
        query: str,
        top_k: int = 5,
        vector_weight: float = 0.5,
        bm25_weight: float = 0.5,
        doc_category: Optional[str] = "user"
    ) -> List[DocumentSearchResultOut]:
        """
        混合搜索：结合向量相似度和BM25

        Args:
            query: 查询文本
            top_k: 返回结果数量
            vector_weight: 向量搜索权重（0-1）
            bm25_weight: BM25权重（0-1）
            doc_category: 文档分类过滤

        Returns:
            混合检索结果列表
        """
        # 1. 向量搜索 - 获取更多候选
        search_top_k = max(top_k * 3, 30)
        vector_results = self.vector_service.search(query, search_top_k)

        if not vector_results:
            logger.warning("向量搜索无结果")
            return []

        # 2. BM25搜索（基于倒排索引）
        bm25_results = self._bm25_search(query, vector_results)

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

    def _bm25_search(
        self,
        query: str,
        vector_results: List[DocumentSearchResultOut]
    ) -> List[Dict]:
        """
        BM25搜索（基于倒排索引）

        Args:
            query: 查询文本
            vector_results: 向量搜索结果

        Returns:
            BM25搜索结果列表
        """
        try:
            # 1. 分词
            query_tokens = IndexBuilder.tokenize(query)
            query_terms = list(set(token[0] for token in query_tokens))  # 去重

            if not query_terms:
                return []

            # 2. 获取候选chunk的ID
            candidate_chunk_ids = [result.chunk_index for result in vector_results]

            # 3. 从倒排索引查询
            inverted_records = InvertedIndex.objects.filter(
                term__in=query_terms,
                chunk_id__in=candidate_chunk_ids
            ).values("chunk_id", "term", "frequency")

            if not inverted_records:
                return []

            # 4. 计算BM25分数
            bm25_scores = {}
            total_chunks = DocumentChunk.objects.count()

            for record in inverted_records:
                chunk_id = record["chunk_id"]
                term = record["term"]
                frequency = record["frequency"]

                if chunk_id not in bm25_scores:
                    bm25_scores[chunk_id] = 0.0

                # IDF计算
                term_count = InvertedIndex.objects.filter(
                    term=term
                ).values("chunk_id").distinct().count()
                idf = math.log((total_chunks - term_count + 0.5) / (term_count + 0.5) + 1.0)

                # BM25
                chunk = DocumentChunk.objects.get(id=chunk_id)
                doc_len = len(IndexBuilder.tokenize(chunk.content))
                
                k1, b = 1.5, 0.75
                avg_doc_len = 200.0
                
                numerator = frequency * (k1 + 1)
                denominator = frequency + k1 * (1 - b + b * (doc_len / avg_doc_len))
                bm25_scores[chunk_id] += idf * (numerator / denominator)

            # 5. 构建结果列表
            results = []
            for chunk_id, score in bm25_scores.items():
                for result in vector_results:
                    if result.chunk_index == chunk_id:
                        results.append({"chunk_id": chunk_id, "score": score, "doc": result})
                        break

            return results

        except Exception as e:
            logger.error(f"BM25搜索失败: {e}")
            return []

    def _merge_results(
        self,
        vector_results: List[DocumentSearchResultOut],
        bm25_results: List[Dict],
        vector_weight: float,
        bm25_weight: float,
        top_k: int
    ) -> List[DocumentSearchResultOut]:
        """融合向量搜索和BM25结果"""
        # 规范化分数
        vector_scores = self._normalize_scores([r.score for r in vector_results])
        bm25_scores_list = [r["score"] for r in bm25_results] if bm25_results else []
        bm25_scores_normalized = self._normalize_scores(bm25_scores_list)

        # 创建分数字典
        score_dict = {}

        for i, doc in enumerate(vector_results):
            score_dict[doc.chunk_index] = {"vector": vector_scores[i], "bm25": 0.0, "doc": doc}

        for i, result in enumerate(bm25_results):
            chunk_id = result["chunk_id"]
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
        vector_weight: float = 0.5,
        bm25_weight: float = 0.5,
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
