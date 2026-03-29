"""
标题识别模块
支持多种标题格式识别：Markdown、数字编号、中文章节
"""

import re
from typing import Optional


class TitleExtractor:
    """标题识别器 - 支持多种标题格式"""

    # 标题识别正则
    PATTERNS = {
        "markdown_h1": re.compile(r"^#{1}\s+(.+)$"),
        "markdown_h2": re.compile(r"^#{2}\s+(.+)$"),
        "markdown_h3": re.compile(r"^#{3}\s+(.+)$"),
        "markdown_h4": re.compile(r"^#{4}\s+(.+)$"),
        "markdown_h5": re.compile(r"^#{5}\s+(.+)$"),
        "markdown_h6": re.compile(r"^#{6}\s+(.+)$"),
        "numbered_1": re.compile(r"^(\d+)\.\s+(.+)$"),  # 1. 标题
        "numbered_2": re.compile(r"^(\d+\.\d+)\s+(.+)$"),  # 1.1 标题
        "numbered_3": re.compile(r"^(\d+\.\d+\.\d+)\s+(.+)$"),  # 1.1.1 标题
        "chinese": re.compile(r"^第([一二三四五六七八九十百千万]+)[章节篇]\s*[:：]?\s*(.+)$"),
        "section": re.compile(r"^([A-Z])[.)]\s+(.+)$"),  # A. 标题
    }

    @staticmethod
    def extract_title(line: str) -> Optional[tuple[str, int]]:
        """
        从一行文本中提取标题

        Args:
            line: 文本行

        Returns:
            (标题文本, 层级) 或 None，层级：0=h1, 1=h2, ...
        """
        line = line.strip()
        if not line:
            return None

        # Markdown标题（最优先）
        for level in range(1, 7):
            pattern = TitleExtractor.PATTERNS[f"markdown_h{level}"]
            match = pattern.match(line)
            if match:
                return match.group(1).strip(), level - 1

        # 数字编号标题
        for pattern_key in ["numbered_3", "numbered_2", "numbered_1"]:
            pattern = TitleExtractor.PATTERNS[pattern_key]
            match = pattern.match(line)
            if match:
                number = match.group(1)
                title = match.group(2)
                level = number.count(".") if "." in number else 0
                return f"{number} {title.strip()}", level

        # 中文章节
        match = TitleExtractor.PATTERNS["chinese"].match(line)
        if match:
            number = match.group(1)
            title = match.group(2).strip()
            return f"第{number}章 {title}", 0

        # A. 形式
        match = TitleExtractor.PATTERNS["section"].match(line)
        if match:
            letter = match.group(1)
            title = match.group(2).strip()
            return f"{letter}. {title}", 1

        return None

    @staticmethod
    def is_title(line: str) -> bool:
        """检查一行是否是标题"""
        return TitleExtractor.extract_title(line) is not None
