import os
import gc
import PyPDF2
import docx
from typing import List, Generator
from loguru import logger

from django.conf import settings
from ..models import Document, DocumentChunk
from .vector_db_service import VectorDBService

# loguru不需要getLogger


class DocumentProcessor:
    """文档处理器，负责解析不同类型的文档并分块"""

    def __init__(self, embedding_model_version=None):
        """
        初始化文档处理器

        Args:
            embedding_model_version: 嵌入模型版本，如果未指定则使用settings中的配置
        """
        # 记录使用的嵌入模型版本
        self.embedding_model_version = embedding_model_version or settings.EMBEDDING_MODEL_VERSION
        logger.info(f"初始化DocumentProcessor，使用嵌入模型: {self.embedding_model_version}")

        # 初始化向量数据库服务，传递模型版本
        self.vector_db = VectorDBService(embedding_model_version=self.embedding_model_version)
        self.max_content_size = 5 * 1024 * 1024  # 5MB最大处理内容限制

    def process_document(self, document_id: int) -> bool:
        """处理文档，解析内容并分块，然后索引"""
        try:
            document = Document.objects.get(id=document_id)

            # 设置文档处理状态和使用的嵌入模型版本
            document.status = "processing"
            document.embedding_model_version = self.embedding_model_version
            document.save()

            logger.info(f"处理文档{document_id}，使用嵌入模型版本: {self.embedding_model_version}")

            # 文件检查
            if not document.file or not os.path.exists(document.file.path):
                document.status = "failed"
                document.error_message = "文件不存在"
                document.save()
                logger.error(f"文档{document_id}文件不存在")
                return False

            # 1. 流式提取文本
            content = self._extract_text_stream(document)

            # 2. 限制内容大小
            if len(content) > self.max_content_size:
                logger.warning(f"文档内容过大({len(content) / 1024 / 1024:.2f}MB)，将被截断")
                content = content[: self.max_content_size]

            # 3. 分批生成和保存分块
            self._process_chunks(document, content)

            # 释放大文本内存
            del content
            gc.collect()

            # 4. 创建向量索引
            logger.info(f"开始为文档{document_id}创建向量索引")
            indexing_result = self.vector_db.index_document(document)

            if indexing_result:
                document.status = "processed"
                document.save()

                # 清除所有向量搜索缓存，因为新文档可能影响搜索结果
                VectorDBService.clear_search_cache()
                logger.info(f"文档{document_id}处理完成，已清除搜索缓存")
                return True
            else:
                document.status = "failed"
                document.error_message = "向量索引失败"
                document.save()
                logger.error(f"文档{document_id}向量索引失败")
                return False

        except MemoryError:
            logger.error(f"处理文档{document_id}时内存不足")
            try:
                document = Document.objects.get(id=document_id)
                document.status = "failed"
                document.error_message = "内存不足"
                document.save()
            except:
                pass
            return False
        except Exception as e:
            logger.error(f"处理文档 {document_id} 失败: {str(e)}")
            try:
                document = Document.objects.get(id=document_id)
                document.status = "failed"
                document.error_message = str(e)
                document.save()
            except:
                pass
            return False

    def _extract_text_stream(self, document: Document) -> str:
        """流式提取文本，避免一次性加载大文件"""
        file_path = document.file.path
        file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB

        # 获取原始文件名
        original_filename = document.title
        logger.info(f"处理文件{original_filename}，路径: {file_path}，大小: {file_size:.2f}MB")

        # 提取文本内容
        content = ""
        if document.file_type == "pdf":
            content = self._extract_text_from_pdf_stream(file_path)
        elif document.file_type == "docx":
            content = self._extract_text_from_docx_stream(file_path)
        elif document.file_type == "txt":
            content = self._extract_text_from_txt_stream(file_path)
        else:
            raise ValueError(f"不支持的文件类型: {document.file_type}")

        # 在内容前添加文件名信息，以便在索引和搜索中包含文件名
        file_info = f"文件名: {original_filename}\n标题: {document.title}\n\n"
        return file_info + content

    def _extract_text_from_pdf_stream(self, file_path: str) -> str:
        """流式处理PDF文件，逐页提取文本"""
        text_chunks = []
        with open(file_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            logger.info(f"PDF有{total_pages}页")

            for i in range(total_pages):
                if i % 5 == 0:  # 每处理5页记录一次日志
                    logger.info(f"处理PDF页面 {i + 1}/{total_pages}")
                page = pdf_reader.pages[i]
                text_chunks.append(page.extract_text() or "")

                # 每处理10页清理一次内存
                if i % 10 == 9:
                    gc.collect()

        return "\n".join(text_chunks)

    def _extract_text_from_docx_stream(self, file_path: str) -> str:
        """处理DOCX文件，逐段提取文本"""
        doc = docx.Document(file_path)
        text_chunks = []

        for i, para in enumerate(doc.paragraphs):
            if para.text:
                text_chunks.append(para.text)

            # 每处理100段清理一次内存
            if i % 100 == 99:
                gc.collect()

        return "\n".join(text_chunks)

    def _extract_text_from_txt_stream(self, file_path: str) -> str:
        """流式读取文本文件，按块处理"""
        chunk_size = 1024 * 1024  # 1MB
        text_chunks = []

        with open(file_path, "r", encoding="utf-8", errors="replace") as file:
            while True:
                chunk = file.read(chunk_size)
                if not chunk:
                    break
                text_chunks.append(chunk)

                # 每读取5MB清理一次内存
                if len(text_chunks) % 5 == 0:
                    gc.collect()

        return "".join(text_chunks)

    def _process_chunks(self, document: Document, content: str):
        """分批处理文本分块和保存"""
        # 1. 先删除现有分块
        DocumentChunk.objects.filter(document_id=document.id).delete()

        # 2. 根据文档类型和内容选择合适的分块策略和大小
        file_extension = document.file_type.lower() if document.file_type else "txt"

        # 根据文件类型和文档大小选择最佳策略
        if len(content) > 100000:  # 大文档 (100KB+)
            strategy = "auto"  # 自动选择最佳策略
            chunk_size = 800  # 较大块，减少块数量
            logger.info(f"文档{document.id}较大({len(content) / 1024:.1f}KB)，使用自动分块策略")
        elif file_extension in ["pdf", "docx"] and len(content) > 10000:
            strategy = "semantic"  # 结构化文档使用语义分块
            chunk_size = 1000
            logger.info(f"文档{document.id}为结构化文档，使用语义分块")
        elif "\n\n" in content[:5000]:  # 检查是否有明显的段落
            strategy = "paragraph"
            chunk_size = 800
            logger.info(f"文档{document.id}有明显段落结构，使用段落分块")
        else:
            strategy = "simple"  # 短文本或无明显结构
            chunk_size = 500
            logger.info(f"文档{document.id}为简单文本，使用简单分块")

        # 执行分块
        logger.info(f"开始对文档{document.id}进行分块，策略:{strategy}，块大小:{chunk_size}")
        chunks = self._chunk_text(content, chunk_size=chunk_size, strategy=strategy)
        logger.info(f"文档{document.id}分块完成，共{len(chunks)}个块")

        # 3. 批量保存分块
        batch_size = 20
        total_chunks = len(chunks)
        metadata = {"chunking_strategy": strategy, "chunk_size": chunk_size}

        for i in range(0, total_chunks, batch_size):
            batch = chunks[i : i + batch_size]
            chunk_objects = []

            for idx, chunk_content in enumerate(batch):
                chunk_objects.append(
                    DocumentChunk(
                        document_id=document.id,
                        content=chunk_content,
                        chunk_index=i + idx,
                        # 保存使用的嵌入模型版本
                        embedding_model_version=self.embedding_model_version,
                    )
                )

            # 批量创建
            DocumentChunk.objects.bulk_create(chunk_objects)
            logger.info(f"保存了{len(chunk_objects)}个文档块，进度: {min(i + batch_size, total_chunks)}/{total_chunks}")

            # 释放内存
            del chunk_objects
            gc.collect()

    # 使用策略模式的分块算法
    def _chunk_text(
        self,
        text: str,
        chunk_size: int = 500,
        overlap_ratio: float = 0.1,
        lookback_ratio: float = 0.1,
        strategy: str = "auto",
    ) -> List[str]:
        """
        将文本分块，支持多种分块策略

        Args:
            text: 要分块的文本
            chunk_size: 每块的目标大小
            overlap_ratio: 块间重叠比例(默认10%)
            lookback_ratio: 寻找断点时的最大回溯比例(默认10%)
            strategy: 分块策略 ("simple", "paragraph", "semantic", "auto")
        """
        # 导入策略模式相关类
        from .chunking_strategies import ChunkingStrategyFactory

        if not text:
            return []

        # 使用工厂创建合适的策略对象
        if strategy == "auto":
            chunking_strategy = ChunkingStrategyFactory.select_best_strategy(text)
            logger.info(f"自动选择分块策略: {chunking_strategy.get_name()}")
        else:
            chunking_strategy = ChunkingStrategyFactory.create_strategy(strategy)
            logger.info(f"使用指定分块策略: {chunking_strategy.get_name()}")

        # 调用策略对象的分块方法
        return chunking_strategy.chunk_text(
            text, chunk_size, overlap_ratio=overlap_ratio, lookback_ratio=lookback_ratio
        )

    # _select_chunking_strategy 方法已移至 ChunkingStrategyFactory 类

    # _detect_structure 方法已移至 chunking_strategies.py

    # _split_paragraphs 方法已移至 chunking_strategies.py

    # _simple_chunk 方法已移至 SimpleChunkingStrategy 类

    # _paragraph_chunk 方法已移至 ParagraphChunkingStrategy 类

    # _semantic_chunk 方法已移至 SemanticChunkingStrategy 类

    # _extract_document_structure 方法已移至 SemanticChunkingStrategy 类
