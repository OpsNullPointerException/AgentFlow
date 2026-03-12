"""
观察结果掩码（Observation Masking）

根据工具类型和输出特征，智能压缩工具输出以降低token消耗
tool_outputs可占87-90%的context，通过结构化压缩可以减少50-70%的输出token
"""

import json
from typing import Any, Dict, Optional
from loguru import logger


class ObservationMasker:
    """观察结果压缩器"""

    # SQL查询结果最大行数
    SQL_MAX_ROWS = 10
    # 文档搜索保留结果数
    DOC_SEARCH_MAX_RESULTS = 3
    # 网络搜索保留结果数
    WEB_SEARCH_MAX_RESULTS = 2

    @staticmethod
    def mask_observation(tool_name: str, output: str, max_length: int = 500) -> str:
        """
        压缩工具输出

        Args:
            tool_name: 工具名称
            output: 原始输出
            max_length: 最大长度

        Returns:
            压缩后的输出
        """
        if not output:
            return output

        # 根据工具类型应用不同的压缩策略
        if tool_name == "sql_query":
            return ObservationMasker._mask_sql_output(output, max_length)
        elif tool_name == "document_search":
            return ObservationMasker._mask_document_output(output, max_length)
        elif tool_name == "web_search":
            return ObservationMasker._mask_web_search_output(output, max_length)
        elif tool_name == "schema_query":
            return ObservationMasker._mask_schema_output(output, max_length)
        else:
            # 默认截断
            return output[:max_length]

    @staticmethod
    def _mask_sql_output(output: str, max_length: int) -> str:
        """
        压缩SQL查询结果
        保留：表头 + 前N行 + 总行数统计
        """
        lines = output.strip().split("\n")

        if len(lines) <= 1:
            return output[:max_length]

        # 提取表头
        header = lines[0]
        result_lines = [header]

        # 计算行数
        data_lines = lines[1:]

        # 提取前N行或找到"共XXX行"的总数
        total_rows = None
        sample_rows = []

        for line in data_lines:
            if "共" in line and "行" in line:
                # 提取总行数
                try:
                    parts = line.split("共")
                    if len(parts) > 1:
                        num_part = parts[1].split("行")[0]
                        total_rows = int(num_part.strip())
                except (ValueError, IndexError):
                    pass
            elif len(sample_rows) < ObservationMasker.SQL_MAX_ROWS:
                sample_rows.append(line)

        # 构建压缩结果
        result_lines.extend(sample_rows)

        if total_rows and total_rows > ObservationMasker.SQL_MAX_ROWS:
            result_lines.append(f"... (共{total_rows}行，已显示前{len(sample_rows)}行)")
        elif len(data_lines) > ObservationMasker.SQL_MAX_ROWS:
            result_lines.append(f"... (共{len(data_lines)}行，已显示前{len(sample_rows)}行)")

        result = "\n".join(result_lines)
        return result[:max_length]

    @staticmethod
    def _mask_document_output(output: str, max_length: int) -> str:
        """
        压缩文档搜索结果
        保留：文档标题 + 摘要 + 相关性分数
        """
        sections = output.split("文档 ")

        result_parts = []
        count = 0

        for section in sections:
            if not section.strip():
                continue

            lines = section.split("\n")
            part = "\n".join(lines[:4])  # 保留文档编号、标题、摘要、相关性

            result_parts.append(f"文档 {part}")
            count += 1

            if count >= ObservationMasker.DOC_SEARCH_MAX_RESULTS:
                result_parts.append(f"... (共{len(sections) - 1}个文档，已显示前{count}个)")
                break

        result = "\n".join(result_parts)
        return result[:max_length]

    @staticmethod
    def _mask_web_search_output(output: str, max_length: int) -> str:
        """
        压缩网络搜索结果
        保留：标题 + 摘要 + 链接
        """
        results = output.split("结果 ")
        result_parts = []
        count = 0

        for result_text in results:
            if not result_text.strip():
                continue

            lines = result_text.split("\n")
            # 只保留编号、标题、摘要、链接
            part_lines = []
            for i, line in enumerate(lines[:4]):
                if i == 0 or "标题:" in line or "摘要:" in line or "链接:" in line:
                    part_lines.append(line)

            result_parts.append("结果 " + "\n".join(part_lines))
            count += 1

            if count >= ObservationMasker.WEB_SEARCH_MAX_RESULTS:
                result_parts.append(f"... (共{len(results) - 1}个结果，已显示前{count}个)")
                break

        result = "\n".join(result_parts)
        return result[:max_length]

    @staticmethod
    def _mask_schema_output(output: str, max_length: int) -> str:
        """
        压缩Schema查询结果
        保留：表名/字段名、类型、是否为NULL
        """
        lines = output.strip().split("\n")

        # 提取表名或字段列表的前N行
        header = lines[0] if lines else ""
        result_lines = [header]

        field_count = 0
        max_fields = 20

        for line in lines[1:]:
            if field_count < max_fields:
                result_lines.append(line)
                if line.startswith("-"):
                    field_count += 1

        if len(lines) > max_fields + 1:
            result_lines.append(f"... (共{len(lines) - 1}个字段，已显示前{field_count}个)")

        result = "\n".join(result_lines)
        return result[:max_length]

    @staticmethod
    def estimate_token_reduction(tool_name: str, original: str, masked: str) -> Dict[str, Any]:
        """
        估算token压缩效果
        粗略估算：平均每4个字符为1个token
        """
        original_tokens = len(original) // 4
        masked_tokens = len(masked) // 4
        reduction = (1 - masked_tokens / max(original_tokens, 1)) * 100

        logger.info(
            f"观察掩码 [{tool_name}]: "
            f"{original_tokens}tokens → {masked_tokens}tokens "
            f"(-{reduction:.1f}%)"
        )

        return {
            "tool": tool_name,
            "original_tokens": original_tokens,
            "masked_tokens": masked_tokens,
            "reduction_percent": reduction,
        }
