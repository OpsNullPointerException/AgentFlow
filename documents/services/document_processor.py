import os
import gc
import PyPDF2
import docx
from typing import List
from loguru import logger

from django.conf import settings
from ..models import Document, DocumentChunk
from .vector_db_service import VectorDBService
from .hierarchical_chunking import TitleExtractor

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
        """分批处理文本分块和保存（一次遍历提取元数据）"""
        # 1. 先删除现有分块
        DocumentChunk.objects.filter(document_id=document.id).delete()

        # 2. 一次性完成：分块 + 提取元数据
        logger.info(f"开始对文档{document.id}进行分块和元数据提取")
        chunks_with_metadata = self._chunk_and_extract_metadata(content)
        logger.info(f"文档{document.id}分块完成，共{len(chunks_with_metadata)}个块")

        # 3. 批量保存分块
        batch_size = 20
        total_chunks = len(chunks_with_metadata)

        for i in range(0, total_chunks, batch_size):
            batch = chunks_with_metadata[i : i + batch_size]
            chunk_objects = []

            for idx, chunk_data in enumerate(batch):
                chunk_index = i + idx

                chunk_objects.append(
                    DocumentChunk(
                        document_id=document.id,
                        content=chunk_data["content"],
                        chunk_index=chunk_index,
                        embedding_model_version=self.embedding_model_version,
                        title=chunk_data.get("title"),
                        section_path=chunk_data.get("section_path"),
                        hierarchy_level=chunk_data.get("hierarchy_level", 0),
                        parent_chunk_index=chunk_index - 1 if chunk_index > 0 else None,
                    )
                )

            # 批量创建
            DocumentChunk.objects.bulk_create(chunk_objects)
            logger.info(f"保存了{len(chunk_objects)}个文档块，进度: {min(i + batch_size, total_chunks)}/{total_chunks}")

            # 释放内存
            del chunk_objects
            gc.collect()

    # 使用LangChain RecursiveCharacterTextSplitter的分块算法
    def _chunk_text(self, text: str, chunk_size: int = 1000, chunk_overlap: int = 100) -> List[str]:
        """
        使用LangChain RecursiveCharacterTextSplitter进行文本分块

        Args:
            text: 要分块的文本
            chunk_size: 目标块大小
            chunk_overlap: 块间重叠字符数

        Returns:
            分块结果列表
        """
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
        except ImportError:
            logger.error("LangChain text splitters未安装，使用备用方案")
            # 备用方案：简单分块
            return self._simple_fallback_chunk(text, chunk_size)

        # 创建分块器，按层级依次尝试在以下位置断开：
        # 1. Markdown标题 (##, ###等)
        # 2. 段落边界 (\n\n)
        # 3. 句子边界 (。？！等)
        # 4. 单词边界 (空格)
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=[
                "\n## ",  # Markdown h2
                "\n### ",  # Markdown h3
                "\n#### ",  # Markdown h4
                "\n\n",  # 段落边界
                "\n",  # 行
                "。",  # 中文句号
                "！",  # 中文感叹号
                "？",  # 中文问号
                "；",  # 中文分号
                " ",  # 空格
                "",  # 字符
            ],
        )

        chunks = splitter.split_text(text)
        logger.info(f"LangChain分块完成，共{len(chunks)}个块")
        return chunks

    def _simple_fallback_chunk(self, text: str, chunk_size: int = 1000) -> List[str]:
        """
        备用分块方案：简单的固定大小分块（当LangChain不可用时）

        Args:
            text: 文本
            chunk_size: 块大小

        Returns:
            分块列表
        """
        logger.warning("使用备用分块方案（LangChain不可用）")
        chunks = []

        if not text:
            return chunks

        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))

            # 寻找句子边界
            if end < len(text):
                # 优先在段落边界断开
                para_pos = text.rfind("\n\n", start + chunk_size // 2, end)
                if para_pos > start:
                    end = para_pos + 2
                else:
                    # 其次在句号断开
                    sentence_boundaries = ["。", "？", "！", "\n"]
                    found = False
                    for boundary in sentence_boundaries:
                        boundary_pos = text.rfind(boundary, start + chunk_size // 2, end)
                        if boundary_pos > start:
                            end = boundary_pos + len(boundary)
                            found = True
                            break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end

        return chunks

    def _chunk_and_extract_metadata(self, text: str) -> list[dict[str, any]]:
        """
        一次遍历：分块 + 提取标题元数据

        关键思想：维护标题栈，为每个chunk记录当前的标题路径

        Args:
            text: 完整文本

        Returns:
            [{content, title, section_path, hierarchy_level}, ...]
        """
        # 1. 先完成分块
        chunks = self._chunk_text(text)
        if not chunks:
            return []

        # 2. 一次性扫描文本，记录所有标题及其位置
        lines = text.split("\n")
        title_positions = []  # [(pos, title, level), ...]
        current_pos = 0

        for line in lines:
            title_info = TitleExtractor.extract_title(line)
            if title_info:
                title, level = title_info
                title_positions.append((current_pos, title, level))
            current_pos += len(line) + 1  # +1 for newline

        # 3. 为每个chunk找到对应的标题路径
        results = []
        for chunk_text in chunks:
            # 在文本中找到chunk的位置
            chunk_pos = text.find(chunk_text)
            if chunk_pos == -1:
                chunk_pos = 0

            # 收集这个chunk之前的所有标题，建立栈
            title_stack = []  # [(title, level), ...]
            for pos, title, level in title_positions:
                if pos >= chunk_pos:
                    break
                # 栈管理：移除所有 level >= 当前level 的元素
                title_stack = [(t, lvl) for t, lvl in title_stack if lvl < level]
                title_stack.append((title, level))

            # 提取元数据
            current_title = title_stack[-1][0] if title_stack else ""
            section_path = " > ".join([t for t, _ in title_stack])
            hierarchy_level = title_stack[-1][1] if title_stack else 0

            results.append({
                "content": chunk_text,
                "title": current_title,
                "section_path": section_path,
                "hierarchy_level": hierarchy_level,
            })

        return results

