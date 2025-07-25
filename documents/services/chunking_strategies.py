"""
文档分块策略模块
使用策略模式实现不同的分块算法
"""

import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from loguru import logger


import json
import requests
from typing import List, Dict, Any, Optional, Tuple
from django.conf import settings


class ChunkingStrategy(ABC):
    """分块策略的抽象基类"""

    @abstractmethod
    def chunk_text(self, text: str, chunk_size: int, **kwargs) -> List[str]:
        """
        将文本分块

        Args:
            text: 要分块的文本
            chunk_size: 每块的目标大小
            **kwargs: 其他参数

        Returns:
            文本块列表
        """
        pass

    def get_name(self) -> str:
        """获取策略名称"""
        return self.__class__.__name__.replace("ChunkingStrategy", "").lower()


class SimpleChunkingStrategy(ChunkingStrategy):
    """简单分块策略：在句子边界处断开文本"""

    def chunk_text(self, text: str, chunk_size: int, **kwargs) -> List[str]:
        """
        简单的固定大小分块，在句子边界处断开

        Args:
            text: 要分块的文本
            chunk_size: 每块的目标大小
            overlap_ratio: 块间重叠比例(默认10%)
            lookback_ratio: 寻找断点时的最大回溯比例(默认10%)
        """
        overlap_ratio = kwargs.get("overlap_ratio", 0.1)
        lookback_ratio = kwargs.get("lookback_ratio", 0.1)

        overlap = int(chunk_size * overlap_ratio)
        lookback = int(chunk_size * lookback_ratio)
        chunks = []

        if not text:
            return chunks

        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))

            # 寻找句子边界作为断点
            if end < len(text):
                # 优先级：段落 > 句号 > 问号 > 感叹号 > 逗号 > 空格
                sentence_boundaries = [
                    "\n\n",
                    "。",
                    "？",
                    "?",
                    "！",
                    "!",
                    "；",
                    ";",
                    "，",
                    ",",
                    " ",
                ]
                found = False

                for boundary in sentence_boundaries:
                    # 在合理范围内寻找最近的断点
                    boundary_pos = text.rfind(boundary, start + chunk_size // 2, end)
                    if boundary_pos > start:
                        end = boundary_pos + len(boundary)
                        found = True
                        break

                # 如果没找到理想断点，继续回溯寻找
                if not found:
                    for i in range(end - 1, max(start, end - lookback), -1):
                        if i < len(text) and text[i] in [".", "!", "?", "\n"]:
                            end = i + 1
                            found = True
                            break

            # 添加当前块
            current_chunk = text[start:end].strip()
            if current_chunk:  # 跳过空块
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

        return chunks


class ParagraphChunkingStrategy(ChunkingStrategy):
    """段落分块策略：尽量保持段落的完整性"""

    def chunk_text(self, text: str, chunk_size: int, **kwargs) -> List[str]:
        """
        基于段落的分块，尽量保持段落的完整性

        Args:
            text: 要分块的文本
            chunk_size: 每块的目标大小
        """
        chunks = []
        if not text:
            return chunks

        # 分割段落
        paragraphs = self._split_paragraphs(text)
        current_chunk = []
        current_size = 0

        for para in paragraphs:
            para_len = len(para)

            if para_len > chunk_size:
                # 如果段落本身超过最大大小
                if current_chunk:
                    # 先保存当前块
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_size = 0

                # 然后对大段落使用简单分块
                simple_strategy = SimpleChunkingStrategy()
                para_chunks = simple_strategy.chunk_text(para, chunk_size // 2, overlap_ratio=0.05)
                chunks.extend(para_chunks)
            elif current_size + para_len > chunk_size:
                # 当前块已满，保存并开始新块
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_size = para_len
            else:
                # 添加到当前块
                current_chunk.append(para)
                current_size += para_len

        # 处理剩余内容
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def _split_paragraphs(self, text: str) -> List[str]:
        """将文本分割为段落"""
        # 通过多个空行或换行符分割
        paragraphs = re.split(r"\n\s*\n|\r\n\s*\r\n", text)
        return [p.strip() for p in paragraphs if p.strip()]


class SemanticChunkingStrategy(ChunkingStrategy):
    """语义分块策略：保留文档结构"""

    def chunk_text(self, text: str, chunk_size: int, **kwargs) -> List[str]:
        """
        语义感知分块，保留文档结构

        Args:
            text: 要分块的文本
            chunk_size: 每块的目标大小
        """
        chunks = []
        if not text:
            return chunks

        # 提取文档结构（标题、章节等）
        structure = self._extract_document_structure(text)

        # 如果检测到结构
        if structure["sections"]:
            for section in structure["sections"]:
                section_title = section["title"]
                section_content = section["content"]
                section_level = section.get("level", 1)

                # 如果章节内容较小，作为单个块
                if len(section_content) <= chunk_size:
                    prefix = "#" * section_level + " " if section_level else ""
                    chunk = f"{prefix}{section_title}\n\n{section_content}"
                    chunks.append(chunk)
                else:
                    # 章节内容过大，需要分块
                    # 但保留标题信息在每个块中
                    prefix = "#" * section_level + " " if section_level else ""
                    paragraph_strategy = ParagraphChunkingStrategy()
                    content_chunks = paragraph_strategy.chunk_text(
                        section_content, chunk_size - len(prefix) - len(section_title) - 10
                    )

                    for i, content in enumerate(content_chunks):
                        if len(content_chunks) > 1:
                            chunk_title = f"{section_title} (部分 {i + 1}/{len(content_chunks)})"
                        else:
                            chunk_title = section_title

                        chunk = f"{prefix}{chunk_title}\n\n{content}"
                        chunks.append(chunk)
        else:
            # 没有检测到结构，回退到段落分块
            paragraph_strategy = ParagraphChunkingStrategy()
            chunks = paragraph_strategy.chunk_text(text, chunk_size)

        return chunks

    def _extract_document_structure(self, text: str) -> Dict[str, Any]:
        """从文本中提取结构信息（标题、章节等）"""
        structure = {"title": None, "sections": []}

        lines = text.split("\n")
        current_section = None

        # 提取文档标题（第一个非空行）
        for line in lines:
            if line.strip():
                structure["title"] = line.strip()
                break

        # 识别Markdown风格标题
        header_pattern = re.compile(r"^(#{1,6})\s+(.+)$")
        # 识别数字编号标题
        numbered_header_pattern = re.compile(r"^(\d+\.\d*)\s+(.+)$")
        # 识别中文章节
        chinese_header_pattern = re.compile(
            r"^第([一二三四五六七八九十百千万]+)[章节篇]\s*[:：]?\s*(.+)$"
        )

        current_content = []

        for line in lines:
            line_text = line.strip()
            if not line_text:
                if current_section:
                    current_content.append("")  # 保留空行
                continue

            # 检测Markdown标题
            header_match = header_pattern.match(line_text)
            if header_match:
                # 如果找到新标题，保存之前的章节
                if current_section:
                    current_section["content"] = "\n".join(current_content)
                    structure["sections"].append(current_section)
                    current_content = []

                # 创建新章节
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                current_section = {"title": title, "level": level, "content": ""}
                continue

            # 检测数字编号标题
            numbered_match = numbered_header_pattern.match(line_text)
            if numbered_match:
                # 如果找到新标题，保存之前的章节
                if current_section:
                    current_section["content"] = "\n".join(current_content)
                    structure["sections"].append(current_section)
                    current_content = []

                # 创建新章节
                number = numbered_match.group(1)
                title = numbered_match.group(2).strip()
                # 根据编号深度估计级别
                level = number.count(".") + 1
                current_section = {"title": f"{number} {title}", "level": level, "content": ""}
                continue

            # 检测中文章节标题
            chinese_match = chinese_header_pattern.match(line_text)
            if chinese_match:
                # 如果找到新标题，保存之前的章节
                if current_section:
                    current_section["content"] = "\n".join(current_content)
                    structure["sections"].append(current_section)
                    current_content = []

                # 创建新章节
                number = chinese_match.group(1)
                title = chinese_match.group(2).strip()
                current_section = {"title": f"第{number}章 {title}", "level": 1, "content": ""}
                continue

            # 普通内容行，添加到当前章节
            if current_section:
                current_content.append(line_text)

        # 保存最后一个章节
        if current_section:
            current_section["content"] = "\n".join(current_content)
            structure["sections"].append(current_section)

        return structure


class ChunkingStrategyFactory:
    """分块策略工厂，负责创建合适的分块策略"""

    @staticmethod
    def create_strategy(strategy_name: str) -> ChunkingStrategy:
        """
        创建指定的分块策略

        Args:
            strategy_name: 策略名称 ("simple", "paragraph", "semantic", "auto")

        Returns:
            ChunkingStrategy: 分块策略实例
        """
        if strategy_name == "paragraph":
            return ParagraphChunkingStrategy()
        elif strategy_name == "semantic":
            return SemanticChunkingStrategy()
        elif strategy_name == "model":
            return LocalModelChunkingStrategy()
        else:  # "simple" 或默认
            return SimpleChunkingStrategy()

    @staticmethod
    def select_best_strategy(text: str) -> ChunkingStrategy:
        """
        根据文本特征自动选择最佳分块策略

        Args:
            text: 要分析的文本

        Returns:
            ChunkingStrategy: 最适合的分块策略实例
        """
        # 分析文本结构
        has_structure = False
        has_paragraphs = False

        # 检查是否有标题结构
        header_patterns = [
            r"^#{1,6}\s+.+$",  # Markdown 标题
            r"^\d+\.\s+.+$",  # 数字编号
            r"^第[一二三四五六七八九十百千万]+[章节篇]",  # 中文章节标题
            r"^[A-Z][\.\)]\s+.+$",  # A. 或 A) 形式的条目
        ]

        header_count = 0
        lines = text.split("\n")
        for line in lines[:100]:  # 仅检查前100行
            line = line.strip()
            if any(re.match(pattern, line) for pattern in header_patterns):
                header_count += 1

        has_structure = header_count >= 3

        # 检查是否有段落
        paragraphs = re.split(r"\n\s*\n|\r\n\s*\r\n", text[:10000])  # 仅检查前10000个字符
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        has_paragraphs = len(paragraphs) > 5

        # 根据分析结果选择策略
        # 检查是否可以使用本地模型分块
        use_model = False
        try:
            # 尝试导入torch，检查是否可以使用模型
            import torch
            from transformers import AutoTokenizer, AutoModel
            if torch.cuda.is_available() or len(text) < 100000:  # GPU可用或文本不太大时使用模型
                use_model = True
        except ImportError:
            logger.info("未找到PyTorch或Transformers库，不使用模型分块策略")
        except Exception as e:
            logger.warning(f"检查模型可用性时出错: {str(e)}")
            
        # 为复杂文本使用模型策略
        if use_model and ((has_structure and len(text) > 10000) or len(text) > 50000):
            logger.info("检测到复杂文本结构，尝试使用基于模型的分块策略")
            return LocalModelChunkingStrategy()
        # 为结构化文本使用语义分块
        elif has_structure and len(text) > 5000:
            logger.info("检测到文档结构，使用语义分块策略")
            return SemanticChunkingStrategy()
        # 为有明显段落的文本使用段落分块
        elif has_paragraphs:
            logger.info("检测到明显段落，使用段落分块策略")
            return ParagraphChunkingStrategy()
        # 其他情况使用简单分块
        else:
            logger.info("未检测到明显结构，使用简单分块策略")
            return SimpleChunkingStrategy()


class LocalModelChunkingStrategy(ChunkingStrategy):
    """使用本地语言模型进行智能分块的策略"""
    
    def __init__(self):
        """初始化基于本地模型的分块策略"""
        self.model = None
        self.tokenizer = None
        self.device = None
        self.model_loaded = False
        
    def _load_model(self):
        """懒加载本地模型"""
        if self.model_loaded:
            return True
            
        try:
            import torch
            from transformers import AutoTokenizer, AutoModel
            
            # 检查GPU可用性
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"使用设备: {self.device}")
            
            # 加载轻量级中文模型
            model_name = "bert-base-chinese"
            
            logger.info(f"正在加载本地模型: {model_name}")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModel.from_pretrained(model_name).to(self.device)
            
            self.model_loaded = True
            logger.info("本地模型加载成功")
            return True
        except Exception as e:
            logger.error(f"加载本地模型失败: {str(e)}")
            return False
            
    def chunk_text(self, text: str, chunk_size: int, **kwargs) -> List[str]:
        """
        使用本地语言模型进行智能分块
        
        Args:
            text: 要分块的文本
            chunk_size: 每块的目标大小
        """
        if not text:
            return []
            
        # 如果文本较短，直接返回
        if len(text) <= chunk_size:
            return [text]
        
        # 尝试加载模型
        if not self._load_model():
            # 模型加载失败，回退到段落分块
            logger.info("本地模型不可用，回退到段落分块策略")
            paragraph_strategy = ParagraphChunkingStrategy()
            return paragraph_strategy.chunk_text(text, chunk_size)
        
        # 找出所有潜在的分块点
        potential_breakpoints = self._identify_potential_breakpoints(text, chunk_size)
        
        # 使用模型进行智能分块
        chunks = []
        start_idx = 0
        
        try:
            import torch
            
            while start_idx < len(text):
                # 找到当前位置后的最佳分块点
                best_breakpoint = self._find_best_breakpoint(text, start_idx, chunk_size, potential_breakpoints)
                
                # 添加当前分块
                current_chunk = text[start_idx:best_breakpoint].strip()
                if current_chunk:
                    chunks.append(current_chunk)
                
                # 更新起始点
                start_idx = best_breakpoint
                
                # 检查是否到达文本末尾
                if start_idx >= len(text):
                    break
                    
        except Exception as e:
            logger.error(f"模型分块过程中出错: {str(e)}，回退到段落分块")
            # 发生错误时回退到传统分块方法
            paragraph_strategy = ParagraphChunkingStrategy()
            return paragraph_strategy.chunk_text(text, chunk_size)
            
        return chunks
        
    def _identify_potential_breakpoints(self, text: str, chunk_size: int) -> List[int]:
        """识别文本中潜在的分块点，基于句子和段落边界"""
        breakpoints = []
        
        # 寻找段落边界
        pattern = r'\n\s*\n|\r\n\s*\r\n'
        for match in re.finditer(pattern, text):
            breakpoints.append(match.end())
            
        # 寻找中文句子边界
        sentence_patterns = [r'。', r'？', r'\?', r'！', r'!', r'；', r';', r'，', r',']
        for pattern in sentence_patterns:
            for match in re.finditer(pattern, text):
                breakpoints.append(match.end())
                
        # 排序并去重
        breakpoints = sorted(set(breakpoints))
        
        # 筛选合理范围内的分块点
        valid_breakpoints = []
        for bp in breakpoints:
            # 分块点应该至少在chunk_size/2位置之后
            if bp < chunk_size / 2:
                continue
                
            # 添加有效断点
            valid_breakpoints.append(bp)
            
        return valid_breakpoints
        
    def _find_best_breakpoint(self, text: str, start_idx: int, chunk_size: int,
                             potential_breakpoints: List[int]) -> int:
        """使用本地模型找到最佳分块点"""
        target_end = start_idx + chunk_size
        
        # 找出目标范围内的所有潜在断点
        candidate_breakpoints = [bp for bp in potential_breakpoints
                               if bp > start_idx and abs(bp - target_end) < chunk_size / 2]
        
        # 如果没有合适的候选点，返回目标长度位置或文本结束
        if not candidate_breakpoints:
            return min(target_end, len(text))
            
        # 如果只有一个候选点，直接使用
        if len(candidate_breakpoints) == 1:
            return candidate_breakpoints[0]
            
        # 使用模型评估最佳断点
        best_breakpoint = self._evaluate_breakpoints_with_model(text, start_idx, candidate_breakpoints, chunk_size)
        return best_breakpoint
        
    def _evaluate_breakpoints_with_model(self, text: str, start_idx: int,
                                       candidate_breakpoints: List[int], chunk_size: int = None) -> int:
        """使用本地模型评估候选断点的语义完整性"""
        try:
            import torch
            
            # 准备候选文本段落
            segments = []
            for bp in candidate_breakpoints:
                segment = text[start_idx:bp]
                # 如果段落太长，取前后部分
                if len(segment) > 510:  # BERT模型最大输入长度为512，留一些余量
                    first_part = segment[:250]
                    last_part = segment[-250:]
                    segment = first_part + "..." + last_part
                segments.append(segment)
                
            # 使用模型计算每个段落的编码
            segment_embeddings = []
            with torch.no_grad():
                for segment in segments:
                    inputs = self.tokenizer(segment, return_tensors="pt",
                                         truncation=True, max_length=512).to(self.device)
                    outputs = self.model(**inputs)
                    # 使用CLS标记的输出作为段落表示
                    embedding = outputs.last_hidden_state[:, 0, :].cpu().numpy()
                    segment_embeddings.append(embedding)
                    
            # 评估每个段落的语义完整性
            # 这里使用一个启发式方法：检查段落末尾的向量表示是否有明显的"未完成感"
            # 我们计算每个段落最后几个token的向量表示与整个段落的表示之间的相似度
            scores = []
            for i, segment in enumerate(segments):
                # 为简单起见，我们使用CLS向量的范数作为一个简单指标
                # 向量范数越大，通常表示语义信息越丰富
                score = float(torch.norm(torch.tensor(segment_embeddings[i])))
                scores.append(score)
                
            # 选择得分最高的段落作为最佳断点
            if scores:
                best_idx = scores.index(max(scores))
                return candidate_breakpoints[best_idx]
                
        except Exception as e:
            logger.error(f"模型评估断点失败: {str(e)}")
            
        # 如果评估失败，返回最接近目标长度的断点
        # 如果chunk_size为None，则使用候选断点中的最佳位置
        target = start_idx + (chunk_size if chunk_size else len(text) // 2)
        return min(candidate_breakpoints, key=lambda bp: abs(bp - target))
