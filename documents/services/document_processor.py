import os
import gc
import PyPDF2
import docx
from typing import List, Generator
import logging

from django.conf import settings
from ..models import Document, DocumentChunk
from .vector_db_service import VectorDBService

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """文档处理器，负责解析不同类型的文档并分块"""
    
    def __init__(self):
        self.vector_db = VectorDBService()
        self.max_content_size = 5 * 1024 * 1024  # 5MB最大处理内容限制
    
    def process_document(self, document_id: int) -> bool:
        """处理文档，解析内容并分块，然后索引"""
        try:
            document = Document.objects.get(id=document_id)
            document.status = 'processing'
            document.save()
            
            # 文件检查
            if not document.file or not os.path.exists(document.file.path):
                document.status = 'failed'
                document.error_message = "文件不存在"
                document.save()
                logger.error(f"文档{document_id}文件不存在")
                return False
            
            # 1. 流式提取文本
            content = self._extract_text_stream(document)
            
            # 2. 限制内容大小
            if len(content) > self.max_content_size:
                logger.warning(f"文档内容过大({len(content)/1024/1024:.2f}MB)，将被截断")
                content = content[:self.max_content_size]
            
            # 3. 分批生成和保存分块
            self._process_chunks(document, content)
            
            # 释放大文本内存
            del content
            gc.collect()
            
            # 4. 创建向量索引
            logger.info(f"开始为文档{document_id}创建向量索引")
            indexing_result = self.vector_db.index_document(document)
            
            if indexing_result:
                document.status = 'processed'
                document.save()
                logger.info(f"文档{document_id}处理完成")
                return True
            else:
                document.status = 'failed'
                document.error_message = "向量索引失败"
                document.save()
                logger.error(f"文档{document_id}向量索引失败")
                return False
                
        except MemoryError:
            logger.error(f"处理文档{document_id}时内存不足")
            try:
                document = Document.objects.get(id=document_id)
                document.status = 'failed'
                document.error_message = "内存不足"
                document.save()
            except:
                pass
            return False
        except Exception as e:
            logger.error(f"处理文档 {document_id} 失败: {str(e)}")
            try:
                document = Document.objects.get(id=document_id)
                document.status = 'failed'
                document.error_message = str(e)
                document.save()
            except:
                pass
            return False
    
    def _extract_text_stream(self, document: Document) -> str:
        """流式提取文本，避免一次性加载大文件"""
        file_path = document.file.path
        file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
        logger.info(f"处理文件{file_path}，大小: {file_size:.2f}MB")
        
        if document.file_type == 'pdf':
            return self._extract_text_from_pdf_stream(file_path)
        elif document.file_type == 'docx':
            return self._extract_text_from_docx_stream(file_path)
        elif document.file_type == 'txt':
            return self._extract_text_from_txt_stream(file_path)
        else:
            raise ValueError(f"不支持的文件类型: {document.file_type}")
    
    def _extract_text_from_pdf_stream(self, file_path: str) -> str:
        """流式处理PDF文件，逐页提取文本"""
        text_chunks = []
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            logger.info(f"PDF有{total_pages}页")
            
            for i in range(total_pages):
                if i % 5 == 0:  # 每处理5页记录一次日志
                    logger.info(f"处理PDF页面 {i+1}/{total_pages}")
                page = pdf_reader.pages[i]
                text_chunks.append(page.extract_text() or '')
                
                # 每处理10页清理一次内存
                if i % 10 == 9:
                    gc.collect()
        
        return '\n'.join(text_chunks)
    
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
                
        return '\n'.join(text_chunks)
    
    def _extract_text_from_txt_stream(self, file_path: str) -> str:
        """流式读取文本文件，按块处理"""
        chunk_size = 1024 * 1024  # 1MB
        text_chunks = []
        
        with open(file_path, 'r', encoding='utf-8', errors='replace') as file:
            while True:
                chunk = file.read(chunk_size)
                if not chunk:
                    break
                text_chunks.append(chunk)
                
                # 每读取5MB清理一次内存
                if len(text_chunks) % 5 == 0:
                    gc.collect()
        
        return ''.join(text_chunks)
    
    def _process_chunks(self, document: Document, content: str):
        """分批处理文本分块和保存"""
        # 1. 先删除现有分块
        DocumentChunk.objects.filter(document_id=document.id).delete()
        
        # 2. 分块处理
        chunk_size = 500  # 减小单块大小
        overlap = 50
        chunks = self._chunk_text(content, chunk_size, overlap)
        
        # 3. 批量保存分块
        batch_size = 20
        total_chunks = len(chunks)
        for i in range(0, total_chunks, batch_size):
            batch = chunks[i:i+batch_size]
            chunk_objects = []
            
            for idx, chunk_content in enumerate(batch):
                chunk_objects.append(
                    DocumentChunk(
                        document_id=document.id,
                        content=chunk_content,
                        chunk_index=i+idx
                    )
                )
            
            # 批量创建
            DocumentChunk.objects.bulk_create(chunk_objects)
            logger.info(f"保存了{len(chunk_objects)}个文档块，进度: {min(i+batch_size, total_chunks)}/{total_chunks}")
            
            # 释放内存
            del chunk_objects
            gc.collect()
    
    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """将文本分块，使用更小的块大小，防止无限循环"""
        chunks = []
        if not text:
            return chunks
        
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            
            # 寻找自然断点
            if end < len(text):
                found_breakpoint = False
                for i in range(end-1, max(start, end-50), -1):
                    if i < len(text) and text[i] in ['.', '!', '?', '\n']:
                        end = i + 1
                        found_breakpoint = True
                        break
                        
            # 添加当前块
            current_chunk = text[start:end]
            chunks.append(current_chunk)
            
            # 确保起始点前进
            new_start = end - overlap
            # 防止无限循环：如果新起点不前进，则强制前进
            if new_start <= start:
                new_start = start + 1
            start = min(new_start, len(text))
            
            # 如果已经处理到文本末尾，退出循环
            if end >= len(text):
                break
                
            # 调试日志
            if len(chunks) % 50 == 0:
                logger.debug(f"已处理{len(chunks)}个块，当前位置: {start}/{len(text)}")
        
        return chunks