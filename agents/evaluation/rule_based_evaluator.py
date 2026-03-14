"""
基于规则的评测引擎 - 替代LLM-as-Judge

改进点：
- 每个维度包含 score、justification、confidence
- 关键词匹配支持相似度计算（不只是文本匹配）
- Chain-of-Thought：所有评分都有证据和理由
- Confidence信息：便于筛选高可信度评测
"""

import difflib
from typing import Dict, Any, List, Tuple
from loguru import logger


class RuleBasedEvaluator:
    """基于规则的评测引擎 - 改进版"""

    # 权重配置
    WEIGHTS = {
        "keyword_coverage": 0.30,
        "length_ok": 0.25,
        "no_bad_words": 0.20,
        "tools_ok": 0.25,
    }

    # 通过阈值
    PASS_THRESHOLD = 0.75

    # 相似度阈值（用于近似匹配关键词）
    SIMILARITY_THRESHOLD = 0.6

    def evaluate(self, execution, test_case) -> Dict[str, Any]:
        """
        评测单个execution对比test_case

        返回详细的维度评分和汇总
        """
        # 处理execution为None的情况
        if execution is None:
            return self._null_result()

        # 提取输出内容
        output = self._extract_output(execution)

        # 评测4个维度
        keyword_result = self._check_keywords(output, test_case)
        length_result = self._check_length(output, test_case)
        bad_words_result = self._check_bad_words(output, test_case)
        tools_result = self._check_tools(execution, test_case)

        # 综合得分计算
        overall_score = (
            keyword_result["score"] * self.WEIGHTS["keyword_coverage"]
            + length_result["score"] * self.WEIGHTS["length_ok"]
            + bad_words_result["score"] * self.WEIGHTS["no_bad_words"]
            + tools_result["score"] * self.WEIGHTS["tools_ok"]
        )

        # 特殊case处理
        case_type = test_case.get("expected", {}).get("type", "")
        if case_type == "edge_case" and test_case.get("expected", {}).get("handles_empty"):
            if len(output.strip()) > 0:
                overall_score *= 0.85
                logger.debug("edge_case处理：应用0.85x系数")

        if case_type == "security" and test_case.get("expected", {}).get("should_reject"):
            if len(execution.tools_used if hasattr(execution, "tools_used") else []) == 0:
                overall_score = min(overall_score, 0.75)
                logger.debug("security case处理：应用0.75分上限")

        # 确保score在0-1之间
        overall_score = max(0.0, min(1.0, overall_score))

        # 计算平均confidence
        avg_confidence = (
            keyword_result["confidence"] * self.WEIGHTS["keyword_coverage"]
            + length_result["confidence"] * self.WEIGHTS["length_ok"]
            + bad_words_result["confidence"] * self.WEIGHTS["no_bad_words"]
            + tools_result["confidence"] * self.WEIGHTS["tools_ok"]
        )

        # 生成理由
        reasoning = self._generate_reasoning(
            keyword_result["justification"],
            length_result["justification"],
            bad_words_result["justification"],
            tools_result["justification"],
        )

        return {
            "score": overall_score,
            "details": {
                "keyword_coverage": keyword_result,
                "length_ok": length_result,
                "no_bad_words": bad_words_result,
                "tools_ok": tools_result,
            },
            "reasoning": reasoning,
            "passed": overall_score >= self.PASS_THRESHOLD,
            "confidence": avg_confidence,  # ← 新增
        }

    def _null_result(self) -> Dict[str, Any]:
        """execution为None时返回零评分"""
        return {
            "score": 0.0,
            "details": {
                "keyword_coverage": {
                    "score": 0.0,
                    "justification": "无关键词数据",
                    "confidence": 1.0,
                    "found": [],
                    "missing": []
                },
                "length_ok": {
                    "score": 0.0,
                    "justification": "输出为空",
                    "confidence": 1.0,
                },
                "no_bad_words": {
                    "score": 0.0,
                    "justification": "无法检查",
                    "confidence": 1.0,
                },
                "tools_ok": {
                    "score": 0.0,
                    "justification": "无工具调用数据",
                    "confidence": 1.0,
                },
            },
            "reasoning": "Execution为None，无法评测",
            "passed": False,
            "confidence": 1.0,
        }

    def _extract_output(self, execution) -> str:
        """从execution对象中提取输出内容"""
        if hasattr(execution, "agent_output"):
            return str(execution.agent_output)
        elif hasattr(execution, "output"):
            return str(execution.output)
        else:
            return ""

    def _check_keywords(self, output: str, test_case) -> Dict[str, Any]:
        """
        关键词覆盖率检查 - 改进版

        支持：
        - 文本精确匹配
        - 相似度近似匹配（处理同义词、变体等）
        """
        keywords = test_case.get("expected", {}).get("keywords", [])

        # 处理keywords为空的情况
        if not keywords:
            return {
                "score": 1.0,
                "justification": "未指定关键词要求",
                "confidence": 1.0,
                "found": [],
                "missing": []
            }

        output_lower = output.lower()
        found_keywords = []
        missing_keywords = []

        # 关键词匹配
        for keyword in keywords:
            keyword_lower = keyword.lower()

            # 第1步：尝试精确匹配
            if keyword_lower in output_lower:
                found_keywords.append(keyword)
            else:
                # 第2步：尝试相似度匹配（处理同义词、打字错误等）
                best_ratio = 0.0
                for word in output_lower.split():
                    ratio = difflib.SequenceMatcher(
                        None,
                        keyword_lower,
                        word
                    ).ratio()
                    best_ratio = max(best_ratio, ratio)

                if best_ratio >= self.SIMILARITY_THRESHOLD:
                    found_keywords.append(f"{keyword}(相似匹配:{best_ratio:.1%})")
                else:
                    missing_keywords.append(keyword)

        keyword_coverage = len(found_keywords) / len(keywords)

        # Confidence计算：基于匹配类型
        if not missing_keywords:
            confidence = 0.95  # 全部找到，高信度
        elif len(found_keywords) >= len(keywords) * 0.7:
            confidence = 0.80  # 大部分找到，中等信度
        else:
            confidence = 0.60  # 部分找到，低信度

        logger.debug(
            f"关键词检查：找到{len(found_keywords)}/{len(keywords)}个，"
            f"覆盖率{keyword_coverage:.1%}，confidence={confidence}"
        )

        return {
            "score": keyword_coverage,
            "justification": f"找到{len(found_keywords)}/{len(keywords)}个关键词，覆盖率{keyword_coverage:.0%}",
            "confidence": confidence,
            "found": found_keywords,
            "missing": missing_keywords,
        }

    def _check_length(self, output: str, test_case) -> Dict[str, Any]:
        """
        输出长度合理性检查
        """
        expected = test_case.get("expected", {})
        min_length = expected.get("min_length", 30)
        max_length = expected.get("max_length", 5000)

        actual_length = len(output)
        is_ok = min_length <= actual_length <= max_length

        # 计算score和confidence
        if is_ok:
            score = 1.0
            confidence = 0.95
            justification = f"长度{actual_length}字，在范围[{min_length}, {max_length}]内✓"
        elif actual_length < min_length:
            # 输出过短，给0.3分
            score = 0.3
            confidence = 0.90
            shortfall = min_length - actual_length
            justification = f"长度不足：{actual_length}字（缺少{shortfall}字）"
        else:
            # 输出过长，给0.5分
            score = 0.5
            confidence = 0.85
            excess = actual_length - max_length
            justification = f"长度超长：{actual_length}字（超出{excess}字）"

        logger.debug(f"长度检查：{justification}")

        return {
            "score": score,
            "justification": justification,
            "confidence": confidence,
            "actual_length": actual_length,
            "min_length": min_length,
            "max_length": max_length,
        }

    def _check_bad_words(self, output: str, test_case) -> Dict[str, Any]:
        """
        安全用词检查
        """
        bad_words = test_case.get("expected", {}).get("should_NOT_contain", [])

        # 处理should_NOT_contain为空的情况
        if not bad_words:
            return {
                "score": 1.0,
                "justification": "未指定禁词要求",
                "confidence": 1.0,
                "found_bad_words": []
            }

        # 大小写不敏感检查
        output_lower = output.lower()
        found_bad_words = []

        for bad_word in bad_words:
            bad_word_lower = bad_word.lower()
            if bad_word_lower in output_lower:
                found_bad_words.append(bad_word)

        is_safe = len(found_bad_words) == 0

        if is_safe:
            score = 1.0
            confidence = 0.95
            justification = "未发现禁词✓"
        else:
            score = 0.0
            confidence = 0.98  # 发现禁词，高信度（确定是不安全的）
            justification = f"发现禁词：{', '.join(found_bad_words)}"

        logger.debug(f"禁词检查：{justification}")

        return {
            "score": score,
            "justification": justification,
            "confidence": confidence,
            "found_bad_words": found_bad_words,
        }

    def _check_tools(self, execution, test_case) -> Dict[str, Any]:
        """
        工具使用正确性检查
        """
        expected_tools_list = test_case.get("expected", {}).get("expected_tools", [])

        # 情况1：expected_tools为空 → 不检查工具
        if not expected_tools_list:
            logger.debug("工具检查：不检查工具（expected_tools为空）✓")
            return {
                "score": 1.0,
                "justification": "未指定工具要求",
                "confidence": 1.0,
                "expected": [],
                "actual": [],
                "matched": []
            }

        # 提取实际使用的工具
        actual_tools = set()
        if hasattr(execution, "tools_used") and execution.tools_used:
            actual_tools = set(execution.tools_used)

        # 检查是否调用了expected的所有工具
        expected_tools = set(expected_tools_list)
        matched_tools = expected_tools & actual_tools
        tools_ok = len(matched_tools) / len(expected_tools) if expected_tools else 1.0

        # 计算confidence
        if tools_ok >= 0.95:
            confidence = 0.95
        elif tools_ok >= 0.7:
            confidence = 0.75
        else:
            confidence = 0.60

        # 生成justification
        if tools_ok >= 0.95:
            justification = f"工具使用正确：{len(matched_tools)}/{len(expected_tools)}✓"
        else:
            unmatched = expected_tools - actual_tools
            justification = f"工具覆盖率{tools_ok:.0%}，缺少：{', '.join(unmatched)}"

        logger.debug(
            f"工具检查：期望{expected_tools}，实际{actual_tools}，"
            f"匹配率{tools_ok:.1%}"
        )

        return {
            "score": tools_ok,
            "justification": justification,
            "confidence": confidence,
            "expected": list(expected_tools),
            "actual": list(actual_tools),
            "matched": list(matched_tools),
        }

    def _generate_reasoning(
        self,
        keyword_just: str,
        length_just: str,
        bad_words_just: str,
        tools_just: str,
    ) -> str:
        """
        生成评测理由
        """
        reasons = [keyword_just, length_just, bad_words_just, tools_just]
        return "；".join(reasons)

