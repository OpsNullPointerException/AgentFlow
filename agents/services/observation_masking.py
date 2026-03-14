"""
观察结果掩码（Observation Masking）

两层防护：
1. 敏感信息脱敏 - 隐藏用户隐私数据、金融数据、系统信息
2. 长度截断 - 减少token消耗（50-70%压缩）

tool_outputs可占87-90%的context，通过结构化脱敏和压缩可以减少50-96%的输出token
"""

import json
import re
from typing import Any, Dict, Optional
from loguru import logger


class ObservationMasker:
    """观察结果脱敏和压缩器"""

    # SQL查询结果最大行数
    SQL_MAX_ROWS = 10
    # 文档搜索保留结果数
    DOC_SEARCH_MAX_RESULTS = 3
    # 网络搜索保留结果数
    WEB_SEARCH_MAX_RESULTS = 2

    # 敏感字段名称映射到脱敏规则
    # 策略：字段名 → 脱敏类型，更精确，减少误判
    SENSITIVE_FIELD_RULES = {
        # 密码/密钥 → 完全隐藏
        r'(password|passwd|pwd|secret)': {
            'type': 'full_mask',
            'mask': '[密码已隐藏]'
        },
        r'(token|access_token|refresh_token|auth_token|bearer)': {
            'type': 'partial_mask',
            'keep_prefix': 4,
            'keep_suffix': 4,
            'separator': '****'
        },
        r'(api_key|apikey|secret_key|private_key)': {
            'type': 'partial_mask',
            'keep_prefix': 4,
            'keep_suffix': 4,
            'separator': '****'
        },

        # 个人隐私信息
        r'(phone|telephone|mobile|tel|cell)': {
            'type': 'phone_mask',
            'mask': '[电话已隐藏]'
        },
        r'(email|mail|e_mail)': {
            'type': 'email_mask',
            'mask': '[邮箱已隐藏]'
        },
        r'(address|addr)': {
            'type': 'full_mask',
            'mask': '[地址已隐藏]'
        },

        # 身份证件
        r'(id_number|id_card|idcard|passport|driver_license)': {
            'type': 'full_mask',
            'mask': '[证件已隐藏]'
        },
        r'(ssn|social_security)': {
            'type': 'full_mask',
            'mask': '[身份号已隐藏]'
        },

        # 金融信息
        r'(credit_card|card_number|card|pan)': {
            'type': 'card_mask',
            'keep_suffix': 4,
            'mask_char': '*'
        },
        r'(bank_account|account_number|account)': {
            'type': 'account_mask',
            'keep_suffix': 4,
            'mask_char': '*'
        },
        r'(salary|income|wage|bonus|payment)': {
            'type': 'number_mask',
            'mask': '[金额已隐藏]'
        },

        # 系统信息（用于SQL/配置）
        r'(internal_ip|private_ip|server_ip)': {
            'type': 'full_mask',
            'mask': '[IP已隐藏]'
        },
    }

    @staticmethod
    def mask_observation(tool_name: str, output: str, max_length: int = 500) -> str:
        """
        脱敏+压缩工具输出

        Args:
            tool_name: 工具名称
            output: 原始输出
            max_length: 最大长度

        Returns:
            脱敏压缩后的输出
        """
        if not output:
            return output

        # 第1步：脱敏敏感信息
        sanitized = ObservationMasker._sanitize_sensitive_data(output, tool_name)

        # 第2步：根据工具类型压缩
        if tool_name == "sql_query":
            compressed = ObservationMasker._mask_sql_output(sanitized, max_length)
        elif tool_name == "document_search":
            compressed = ObservationMasker._mask_document_output(sanitized, max_length)
        elif tool_name == "web_search":
            compressed = ObservationMasker._mask_web_search_output(sanitized, max_length)
        elif tool_name == "schema_query":
            compressed = ObservationMasker._mask_schema_output(sanitized, max_length)
        else:
            compressed = sanitized[:max_length]

        return compressed

    @staticmethod
    def _sanitize_sensitive_data(output: str, tool_name: str) -> str:
        """
        第1层：脱敏敏感信息

        策略：字段名驱动（优先）+ 格式检测（备选）
        原因：
          - 字段名更可靠（减少误判）
          - 格式检测补充漏判
          - 结合上下文信息
        """
        result = output

        if tool_name == "sql_query":
            # SQL结果：按字段名脱敏
            result = ObservationMasker._sanitize_sql_result(result)
        elif tool_name == "document_search":
            # 文档：检查是否包含个人隐私
            result = ObservationMasker._sanitize_general_text(result)
        else:
            # 其他：通用脱敏（保守）
            result = ObservationMasker._sanitize_general_text(result)

        return result

    @staticmethod
    def _sanitize_sql_result(output: str) -> str:
        """
        SQL结果脱敏：基于字段名

        示例输入：
          id  name   phone          email              salary
          1   Alice  13812345678    alice@example.com  50000
          2   Bob    13987654321    bob@example.com    60000

        输出：
          id  name   phone          email              salary
          1   Alice  [电话已隐藏]    [邮箱已隐藏]       [金额已隐藏]
          2   Bob    [电话已隐藏]    [邮箱已隐藏]       [金额已隐藏]
        """
        lines = output.strip().split('\n')
        if len(lines) < 2:
            return output

        # 第1行：表头
        header_line = lines[0]
        columns = header_line.split()

        # 识别敏感列（基于字段名）
        sensitive_cols = {}
        for col_idx, col_name in enumerate(columns):
            for pattern, rule in ObservationMasker.SENSITIVE_FIELD_RULES.items():
                if re.search(pattern, col_name, re.IGNORECASE):
                    sensitive_cols[col_idx] = rule
                    logger.debug(f"识别到敏感字段: {col_name} (类型: {rule['type']})")
                    break

        if not sensitive_cols:
            # 没有识别到敏感字段，直接返回
            return output

        # 脱敏数据行
        result_lines = [header_line]
        for line in lines[1:]:
            if not line.strip():
                continue

            values = line.split('\t') if '\t' in line else line.split()
            if len(values) != len(columns):
                # 格式不匹配，保持原样
                result_lines.append(line)
                continue

            # 脱敏敏感列
            for col_idx, rule in sensitive_cols.items():
                if col_idx < len(values):
                    values[col_idx] = ObservationMasker._apply_mask_rule(
                        values[col_idx],
                        rule
                    )

            result_lines.append('\t'.join(values) if '\t' in line else ' '.join(values))

        return '\n'.join(result_lines)

    @staticmethod
    def _sanitize_general_text(text: str) -> str:
        """
        通用文本脱敏：格式模式检测（保守策略）

        仅脱敏：
        - 完整的中国身份证号（17位+1位）
        - 明确的邮箱
        - 明确的手机号（中国格式）
        """
        result = text

        # 中国身份证号：非常准确，误判概率低
        result = re.sub(
            r'\b\d{6}\d{8}\d{3}[\dXx]\b',
            '[身份证已隐藏]',
            result
        )

        # 邮箱：已被多个系统验证的正则
        result = re.sub(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            '[邮箱已隐藏]',
            result
        )

        # 中国手机号：1[3-9]开头的11位数
        result = re.sub(
            r'\b1[3-9]\d{9}\b',
            '[电话已隐藏]',
            result
        )

        return result

    @staticmethod
    def _apply_mask_rule(value: str, rule: Dict[str, Any]) -> str:
        """应用脱敏规则"""
        mask_type = rule.get('type', 'full_mask')

        if mask_type == 'full_mask':
            # 完全隐藏
            return rule.get('mask', '[已脱敏]')

        elif mask_type == 'partial_mask':
            # 保留前N位和后N位
            keep_prefix = rule.get('keep_prefix', 4)
            keep_suffix = rule.get('keep_suffix', 4)
            separator = rule.get('separator', '****')

            if len(value) <= keep_prefix + keep_suffix:
                return rule.get('mask', '[已脱敏]')

            return (
                value[:keep_prefix] +
                separator +
                value[-keep_suffix:]
            )

        elif mask_type == 'card_mask':
            # 卡号脱敏：保留后4位
            keep_suffix = rule.get('keep_suffix', 4)
            mask_char = rule.get('mask_char', '*')

            if len(value) <= keep_suffix:
                return rule.get('mask', '[已脱敏]')

            return (
                mask_char * (len(value) - keep_suffix) +
                value[-keep_suffix:]
            )

        elif mask_type == 'account_mask':
            # 账号脱敏：同card_mask
            return ObservationMasker._apply_mask_rule(
                value,
                {'type': 'card_mask', **rule}
            )

        elif mask_type == 'phone_mask':
            # 手机脱敏
            return rule.get('mask', '[电话已隐藏]')

        elif mask_type == 'email_mask':
            # 邮箱脱敏
            return rule.get('mask', '[邮箱已隐藏]')

        elif mask_type == 'number_mask':
            # 数字脱敏（用于金额）
            return rule.get('mask', '[已脱敏]')

        else:
            return value

    @staticmethod
    def _mask_sql_output(output: str, max_length: int) -> str:
        """
        第2层：压缩SQL查询结果
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
        第2层：压缩文档搜索结果
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
        第2层：压缩网络搜索结果
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
        第2层：压缩Schema查询结果
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

        包括脱敏效果和截断效果
        """
        original_tokens = len(original) // 4
        masked_tokens = len(masked) // 4
        reduction = (1 - masked_tokens / max(original_tokens, 1)) * 100

        logger.info(
            f"观察掩码 [{tool_name}]: "
            f"{original_tokens}tokens → {masked_tokens}tokens "
            f"(-{reduction:.1f}%) "
            f"[脱敏+截断]"
        )

        return {
            "tool": tool_name,
            "original_tokens": original_tokens,
            "masked_tokens": masked_tokens,
            "reduction_percent": reduction,
        }

    @staticmethod
    def mask_and_analyze(tool_name: str, output: str, max_length: int = 500) -> Dict[str, Any]:
        """
        脱敏+压缩，并返回详细分析

        返回：
            {
                "masked_output": str,
                "reduction": {
                    "original_length": int,
                    "masked_length": int,
                    "token_reduction": float,
                    "sanitization_applied": bool,
                    "truncation_applied": bool,
                }
            }
        """
        masked = ObservationMasker.mask_observation(tool_name, output, max_length)

        # 判断是否进行了脱敏和截断
        sanitization_applied = len(masked) != len(output) and '[' in masked
        truncation_applied = len(masked) < len(output)

        return {
            "masked_output": masked,
            "reduction": {
                "original_length": len(output),
                "masked_length": len(masked),
                "token_reduction": (1 - len(masked) / max(len(output), 1)) * 100,
                "sanitization_applied": sanitization_applied,
                "truncation_applied": truncation_applied,
            }
        }
