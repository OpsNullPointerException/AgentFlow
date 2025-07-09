import os
import PyPDF2
import docx
from typing import List, Dict, Any
import logging

from .models import Document, DocumentChunk

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """文档处理器，负责解析不同类型的文档并分块"""
    
    @staticmethod
    def process_document(document_id: int) -> bool:
        """处理文档，解析内容并分块"""
        try:
            document = Document.objects.get(id=document_id)
            document.status = 'processing'
            document.save()
            
            # 解析文档内容
            content = DocumentProcessor._extract_text(document)
            
            # 分块
            chunks = DocumentProcessor._chunk_text(content)
            
            # 保存分块
            DocumentProcessor._save_chunks(document, chunks)
            
            # 更新文档状态
            document.status = 'processed'
            document.save()
            
            # 实际应用中，这里应该将文档块向量化并存储到向量数据库
            # 例如：VectorDBService.index_document(document)
            
            return True
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
    
    @staticmethod
    def _extract_text(document: Document) -> str:
        """根据文档类型提取文本内容"""
        file_path = document.file.path
        
        if document.file_type == 'pdf':
            return DocumentProcessor._extract_text_from_pdf(file_path)
        elif document.file_type == 'docx':
            return DocumentProcessor._extract_text_from_docx(file_path)
        elif document.file_type == 'txt':
            return DocumentProcessor._extract_text_from_txt(file_path)
        else:
            raise ValueError(f"不支持的文件类型: {document.file_type}")
    
    @staticmethod
    def _extract_text_from_pdf(file_path: str) -> str:
        """从PDF文件中提取文本"""
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text
    
    @staticmethod
    def _extract_text_from_docx(file_path: str) -> str:
        """从DOCX文件中提取文本"""
        doc = docx.Document(file_path)
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text
    
    @staticmethod
    def _extract_text_from_txt(file_path: str) -> str:
        """从TXT文件中提取文本"""
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    
    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
        """将文本分块，可以设置块大小和重叠区域"""
        chunks = []
        if not text:
            return chunks
        
        # 简单的按字符数分块，实际应用中可能需要更复杂的分块策略
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            
            # 如果不是最后一块，尝试在一个自然的断点处结束（如句号或换行符）
            if end < len(text):
                # 寻找最近的句子结束符
                for i in range(end-1, max(start, end-50), -1):
                    if text[i] in ['.', '!', '?', '\n']:
                        end = i + 1
                        break
            
            chunks.append(text[start:end])
            start = end - overlap  # 重叠区域
        
        return chunks
    
    @staticmethod
    def _save_chunks(document: Document, chunks: List[str]) -> None:
        """将文档块保存到数据库"""
        # 先删除现有的块
        DocumentChunk.objects.filter(document=document).delete()
        
        # 保存新的块
        for i, chunk_content in enumerate(chunks):
            DocumentChunk.objects.create(
                document=document,
                content=chunk_content,
                chunk_index=i
            )


class VectorDBService:
    """向量数据库服务，用于存储和检索文档向量"""
    
    @staticmethod
    def index_document(document: Document) -> bool:
        """将文档索引到向量数据库"""
        # 在实际应用中，这里应该实现向量化和存储逻辑
        # 例如使用FAISS创建向量索引并存储
        # 下面是伪代码示例
        
        try:
            chunks = DocumentChunk.objects.filter(document=document)
            
            # 实际应用中，这里应该使用embedding模型将文本转换为向量
            # vectors = [get_embedding(chunk.content) for chunk in chunks]
            
            # 然后将向量存储到FAISS或其他向量数据库
            # vector_ids = faiss_index.add(vectors)
            
            # 保存向量ID到数据库
            # for i, chunk in enumerate(chunks):
            #     chunk.vector_id = str(vector_ids[i])
            #     chunk.save()
            
            return True
        except Exception as e:
            logger.error(f"索引文档 {document.id} 失败: {str(e)}")
            return False
    
    @staticmethod
    def search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """根据查询文本搜索相关文档块"""
        # 在实际应用中，这里应该实现向量检索逻辑
        # 下面是伪代码示例
        
        # 1. 将查询文本转换为向量
        # query_vector = get_embedding(query)
        
        # 2. 在向量数据库中检索最相似的向量
        # scores, vector_ids = faiss_index.search(query_vector, top_k)
        
        # 3. 根据向量ID获取对应的文档块
        # results = []
        # for i, vector_id in enumerate(vector_ids):
        #     chunk = DocumentChunk.objects.get(vector_id=str(vector_id))
        #     results.append({
        #         'document_id': chunk.document.id,
        #         'document_title': chunk.document.title,
        #         'chunk_index': chunk.chunk_index,
        #         'content': chunk.content,
        #         'score': float(scores[i])
        #     })
        
        # 当前返回空结果，实际应用中应该返回检索结果
        return []