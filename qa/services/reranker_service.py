import re
from typing import Any, Dict, List, Optional

import numpy as np
from django.conf import settings
from loguru import logger
from qa.schemas.retrieval import DocumentSearchResultOut

try:
    from sentence_transformers import CrossEncoder

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers 未安装，将使用基础重排序方法")


class RerankerService:
    """重排序服务，用于对检索结果进行重新排序以提高相关性"""

    def __init__(self):
        """初始化重排序服务"""
        self.cross_encoder = None
        self.reranker_model_name = getattr(settings, "RERANKER_MODEL_NAME", "ms-marco-MiniLM-L-6-v2")

        # 导入LLM服务用于模型重排序
        from .llm_service import LLMService

        self.llm_service = LLMService(model_name="qwen-turbo")  # 使用快速模型进行重排序

        # 尝试初始化交叉编码器（延迟加载）
        self._cross_encoder_loaded = False
        self._cross_encoder_load_attempted = False

    def _create_reranked_doc(
        self, original_doc: DocumentSearchResultOut, rerank_score: float, final_score: float, rerank_method: str
    ) -> DocumentSearchResultOut:
        """创建一个新的重排序文档对象"""
        return DocumentSearchResultOut(
            id=original_doc.id,
            title=original_doc.title,
            content=original_doc.content,
            score=original_doc.score,
            chunk_index=original_doc.chunk_index,
            embedding_model_version=original_doc.embedding_model_version,
            rerank_score=rerank_score,
            final_score=final_score,
            rerank_method=rerank_method,
        )

    def _load_cross_encoder(self):
        """延迟加载交叉编码器"""
        if self._cross_encoder_load_attempted:
            return self.cross_encoder is not None

        self._cross_encoder_load_attempted = True

        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.info("sentence-transformers 不可用，跳过交叉编码器加载")
            return False

        try:
            # 使用更兼容的加载方式
            import torch

            device = "cpu"  # 强制使用CPU避免设备问题

            self.cross_encoder = CrossEncoder(
                f"cross-encoder/{self.reranker_model_name}", device=device, trust_remote_code=True
            )

            # 验证模型是否正常工作
            test_pairs = [["test query", "test document"]]
            _ = self.cross_encoder.predict(test_pairs)

            self._cross_encoder_loaded = True
            logger.info(f"成功加载交叉编码器重排序模型: {self.reranker_model_name}")
            return True

        except Exception as e:
            logger.warning(f"加载交叉编码器失败: {str(e)}，将使用基础重排序方法")
            self.cross_encoder = None
            self._cross_encoder_loaded = False
            return False

    def rerank_documents(
        self,
        query: str,
        documents: List[DocumentSearchResultOut],
        method: str = "llm_rerank",
        top_k: Optional[int] = None,
    ) -> List[DocumentSearchResultOut]:
        """
        对检索到的文档进行重排序

        Args:
            query: 查询文本
            documents: 检索到的文档列表
            method: 重排序方法 ("llm_rerank", "llm_score", "cross_encoder", "bm25", "hybrid", "keyword_boost")
            top_k: 重排序后返回的文档数量，如果为None则返回所有文档

        Returns:
            重排序后的文档列表
        """
        if not documents:
            return documents

        logger.info(f"使用 {method} 方法对 {len(documents)} 个文档进行重排序")

        try:
            if method == "llm_rerank":
                reranked_docs = self._rerank_with_llm(query, documents)
            elif method == "llm_score":
                reranked_docs = self._score_with_llm(query, documents)
            elif method == "cross_encoder" and self.cross_encoder:
                reranked_docs = self._rerank_with_cross_encoder(query, documents)
            elif method == "bm25":
                reranked_docs = self._rerank_with_bm25(query, documents)
            elif method == "keyword_boost":
                reranked_docs = self._rerank_with_keyword_boost(query, documents)
            elif method == "hybrid":
                reranked_docs = self._rerank_hybrid(query, documents)
            else:
                logger.warning(f"未知的重排序方法: {method}，使用LLM重排序")
                reranked_docs = self._rerank_with_llm(query, documents)

            # 如果指定了top_k，截取前k个结果
            if top_k is not None:
                reranked_docs = reranked_docs[:top_k]

            logger.info(f"重排序完成，返回 {len(reranked_docs)} 个文档")
            return reranked_docs

        except Exception as e:
            logger.error(f"重排序失败: {str(e)}")
            # 重排序失败时返回原始结果
            return documents[:top_k] if top_k else documents

    def _rerank_with_llm(self, query: str, documents: List[DocumentSearchResultOut]) -> List[DocumentSearchResultOut]:
        """使用LLM模型进行重排序"""
        try:
            # 构建用于重排序的提示词
            doc_list = []
            for i, doc in enumerate(documents):
                title = doc.title or "无标题"
                content = doc.content[:300] if doc.content else ""  # 截取前300字符
                doc_list.append(f"文档{i + 1}: {title}\n内容: {content}")

            docs_text = "\n\n".join(doc_list)

            prompt = f"""请根据查询"{query}"对以下文档按相关性从高到低重新排序。

文档列表：
{docs_text}

请返回重排序后的文档编号列表，格式为：[1, 3, 2, ...]
只返回编号列表，不要其他内容。"""

            # 调用LLM进行重排序
            response = self.llm_service.generate_response(query=prompt, context="", conversation_history=None)

            if not response.get("error", False):
                # 解析LLM返回的排序结果
                answer = response["answer"].strip()
                logger.info(f"LLM重排序结果: {answer}")

                # 尝试解析排序结果
                try:
                    # 提取数字列表
                    import json

                    if answer.startswith("[") and answer.endswith("]"):
                        order = json.loads(answer)
                    else:
                        # 尝试从文本中提取数字
                        numbers = re.findall(r"\d+", answer)
                        order = [int(n) for n in numbers]

                    # 过滤有效的索引并去重
                    valid_order = []
                    seen = set()
                    for n in order:
                        if 1 <= n <= len(documents) and n not in seen:
                            valid_order.append(n)
                            seen.add(n)

                    # 补充缺失的索引
                    for i in range(1, len(documents) + 1):
                        if i not in seen:
                            valid_order.append(i)

                    # 使用处理后的排序结果
                    if len(valid_order) == len(documents):
                        # 按照LLM的排序重新排列文档
                        reranked_docs = []
                        for idx in valid_order:
                            original_doc = documents[idx - 1]  # 转换为0-based索引
                            rerank_score = 1.0 - (len(reranked_docs) / len(documents))  # 归一化分数
                            final_score = 0.4 * original_doc.score + 0.6 * rerank_score

                            # 创建新的文档对象，更新重排序字段
                            new_doc = DocumentSearchResultOut(
                                id=original_doc.id,
                                title=original_doc.title,
                                content=original_doc.content,
                                score=original_doc.score,
                                chunk_index=original_doc.chunk_index,
                                embedding_model_version=original_doc.embedding_model_version,
                                rerank_score=rerank_score,
                                final_score=final_score,
                                rerank_method="llm_rerank",
                            )
                            reranked_docs.append(new_doc)

                        logger.info(f"LLM重排序成功，重新排列了 {len(reranked_docs)} 个文档")
                        return reranked_docs
                    else:
                        logger.warning(f"LLM返回的排序结果无效: {order}, 处理后: {valid_order}")

                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"解析LLM排序结果失败: {str(e)}")

            # 如果LLM重排序失败，回退到评分方法
            logger.info("LLM重排序失败，回退到LLM评分方法")
            return self._score_with_llm(query, documents)

        except Exception as e:
            logger.error(f"LLM重排序失败: {str(e)}")
            return documents

    def _score_with_llm(self, query: str, documents: List[DocumentSearchResultOut]) -> List[DocumentSearchResultOut]:
        """使用LLM为每个文档打分"""
        try:
            scored_docs = []

            # 批量处理文档以提高效率
            batch_size = 5
            for i in range(0, len(documents), batch_size):
                batch = documents[i : i + batch_size]

                # 构建批量评分提示
                doc_list = []
                for j, doc in enumerate(batch):
                    title = doc.title or "无标题"
                    content = doc.content[:200] if doc.content else ""  # 截取前200字符
                    doc_list.append(f"文档{j + 1}: {title}\n内容: {content}")

                docs_text = "\n\n".join(doc_list)

                prompt = f"""请根据查询"{query}"为以下文档的相关性打分，分数范围0-10。

文档列表：
{docs_text}

请为每个文档打分，格式为：
文档1: 分数
文档2: 分数
...

只返回分数，不要解释。"""

                response = self.llm_service.generate_response(query=prompt, context="", conversation_history=None)

                if not response.get("error", False):
                    # 解析评分结果
                    answer = response["answer"].strip()
                    lines = answer.split("\n")

                    for j, doc in enumerate(batch):
                        try:
                            # 尝试从对应行中提取分数
                            if j < len(lines):
                                line = lines[j]
                                score_match = re.search(r"(\d+(?:\.\d+)?)", line)
                                if score_match:
                                    llm_score = float(score_match.group(1)) / 10.0  # 归一化到0-1
                                else:
                                    llm_score = 0.5  # 默认分数
                            else:
                                llm_score = 0.5

                            final_score = 0.4 * doc.score + 0.6 * llm_score
                            scored_doc = self._create_reranked_doc(doc, llm_score, final_score, "llm_score")

                        except (ValueError, AttributeError):
                            # 解析失败时使用默认分数
                            scored_doc = self._create_reranked_doc(doc, 0.5, doc.score, "llm_score")

                        scored_docs.append(scored_doc)
                else:
                    # LLM调用失败时，保持原始分数
                    for doc in batch:
                        scored_doc = self._create_reranked_doc(doc, 0.5, doc.score, "llm_score")
                        scored_docs.append(scored_doc)

            # 按最终分数排序
            scored_docs.sort(key=lambda x: x.final_score, reverse=True)
            logger.info(f"LLM评分完成，处理了 {len(scored_docs)} 个文档")
            return scored_docs

        except Exception as e:
            logger.error(f"LLM评分失败: {str(e)}")
            return documents

    def _rerank_with_cross_encoder(
        self, query: str, documents: List[DocumentSearchResultOut]
    ) -> List[DocumentSearchResultOut]:
        """使用交叉编码器进行重排序"""
        # 尝试加载交叉编码器
        if not self._load_cross_encoder():
            logger.warning("交叉编码器不可用，回退到LLM方法")
            return self._score_with_llm(query, documents)

        try:
            # 准备查询-文档对
            query_doc_pairs = []
            for doc in documents:
                content = doc.content or ""
                query_doc_pairs.append([query, content])

            # 计算相关性分数
            scores = self.cross_encoder.predict(query_doc_pairs)

            # 创建重排序后的文档
            reranked_docs = []
            for i, doc in enumerate(documents):
                rerank_score = float(scores[i])
                # 结合原始分数和重排序分数
                final_score = 0.3 * doc.score + 0.7 * rerank_score
                reranked_doc = self._create_reranked_doc(doc, rerank_score, final_score, "cross_encoder")
                reranked_docs.append(reranked_doc)

            # 按重排序分数排序
            return sorted(reranked_docs, key=lambda x: x.final_score, reverse=True)

        except Exception as e:
            logger.error(f"交叉编码器重排序失败: {str(e)}")
            return documents

    def _rerank_with_bm25(self, query: str, documents: List[DocumentSearchResultOut]) -> List[DocumentSearchResultOut]:
        """使用BM25算法进行重排序"""
        try:
            # 简化的BM25实现
            query_terms = self._tokenize(query.lower())

            reranked_docs = []
            for doc in documents:
                content = (doc.content or "").lower()
                doc_terms = self._tokenize(content)

                # 计算BM25分数
                bm25_score = self._calculate_bm25_score(query_terms, doc_terms, len(documents))

                # 结合原始分数和BM25分数
                final_score = 0.5 * doc.score + 0.5 * bm25_score
                reranked_doc = self._create_reranked_doc(doc, bm25_score, final_score, "bm25")
                reranked_docs.append(reranked_doc)

            return sorted(reranked_docs, key=lambda x: x.final_score, reverse=True)

        except Exception as e:
            logger.error(f"BM25重排序失败: {str(e)}")
            return documents

    def _rerank_with_keyword_boost(
        self, query: str, documents: List[DocumentSearchResultOut]
    ) -> List[DocumentSearchResultOut]:
        """基于关键词匹配进行重排序提升"""
        try:
            query_terms = set(self._tokenize(query.lower()))

            reranked_docs = []
            for doc in documents:
                content = (doc.content or "").lower()
                title = (doc.title or "").lower()

                # 计算关键词匹配分数
                content_terms = set(self._tokenize(content))
                title_terms = set(self._tokenize(title))

                # 内容匹配分数
                content_matches = len(query_terms & content_terms) / len(query_terms) if query_terms else 0
                # 标题匹配分数（权重更高）
                title_matches = len(query_terms & title_terms) / len(query_terms) if query_terms else 0

                # 精确短语匹配加分
                phrase_bonus = 1.0 if query.lower() in content else 0.0
                title_phrase_bonus = 2.0 if query.lower() in title else 0.0

                keyword_score = content_matches + 2 * title_matches + phrase_bonus + title_phrase_bonus

                # 结合原始分数和关键词分数
                final_score = 0.6 * doc.score + 0.4 * keyword_score
                reranked_doc = self._create_reranked_doc(doc, keyword_score, final_score, "keyword_boost")
                reranked_docs.append(reranked_doc)

            return sorted(reranked_docs, key=lambda x: x.final_score, reverse=True)

        except Exception as e:
            logger.error(f"关键词重排序失败: {str(e)}")
            return documents

    def _rerank_hybrid(self, query: str, documents: List[DocumentSearchResultOut]) -> List[DocumentSearchResultOut]:
        """混合重排序方法，结合多种策略"""
        try:
            # 首先应用关键词提升
            keyword_boosted = self._rerank_with_keyword_boost(query, documents)

            # 使用LLM进一步优化前10个结果
            if len(keyword_boosted) > 10:
                top_candidates = keyword_boosted[:10]
                llm_reranked = self._score_with_llm(query, top_candidates)

                # 将剩余的文档添加到结果中
                remaining_docs = keyword_boosted[10:]
                return llm_reranked + remaining_docs
            else:
                # 文档数量较少时，全部使用LLM重排序
                return self._score_with_llm(query, keyword_boosted)

        except Exception as e:
            logger.error(f"混合重排序失败: {str(e)}")
            return documents

    def _tokenize(self, text: str) -> List[str]:
        """简单的文本分词"""
        # 使用正则表达式分词，支持中英文
        tokens = re.findall(r"\b\w+\b", text)
        return [token for token in tokens if len(token) > 1]  # 过滤掉单字符

    def _calculate_bm25_score(self, query_terms: List[str], doc_terms: List[str], corpus_size: int) -> float:
        """计算简化的BM25分数"""
        k1, b = 1.5, 0.75  # BM25参数
        doc_len = len(doc_terms)
        avg_doc_len = 100  # 假设平均文档长度

        score = 0.0
        doc_term_counts = {}
        for term in doc_terms:
            doc_term_counts[term] = doc_term_counts.get(term, 0) + 1

        for term in query_terms:
            if term in doc_term_counts:
                tf = doc_term_counts[term]
                # 简化的IDF计算
                idf = np.log((corpus_size + 1) / (1 + 1))  # 假设每个词在1个文档中出现

                # BM25公式
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * (doc_len / avg_doc_len))
                score += idf * (numerator / denominator)

        return score

    @staticmethod
    def is_available() -> bool:
        """检查重排序服务是否可用"""
        return True  # 基础功能总是可用

    def get_available_methods(self) -> List[str]:
        """获取可用的重排序方法"""
        methods = ["llm_rerank", "llm_score", "bm25", "keyword_boost", "hybrid"]

        # 尝试加载交叉编码器来检查是否可用
        if self._load_cross_encoder():
            methods.append("cross_encoder")

        return methods

    @staticmethod
    def get_basic_methods() -> List[str]:
        """获取基础可用的重排序方法（不需要额外依赖）"""
        return ["llm_rerank", "llm_score", "bm25", "keyword_boost", "hybrid"]
