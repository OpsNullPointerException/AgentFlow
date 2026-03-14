"""
基于规则的评测引擎 - 替代LLM-as-Judge

改进点：
- 每个维度包含 score、justification、confidence
- 关键词匹配支持相似度计算（不只是文本匹配）
- Chain-of-Thought：所有评分都有证据和理由
- Confidence信息：便于筛选高可信度评测
"""

import difflib
import re
from typing import Dict, Any, List, Tuple
from loguru import logger
from agents.evaluation.rubrics import get_rubric, RUBRICS


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

        支持：
        - 自动推断任务类型（如果未显式指定）
        - 根据任务类型选择对应Rubric
        - 根据任务类型提取对应的output用于评测
        """
        # 处理execution为None的情况
        if execution is None:
            return self._null_result()

        # 自动推断任务类型（优先级：显式指定 > tools_used推断 > output推断 > 默认）
        task_type = self._infer_task_type(execution, test_case)
        rubric = get_rubric(task_type)

        logger.debug(f"使用Rubric: {task_type}, 标准: {[c.name for c in rubric.criteria]}")

        # 根据任务类型提取合适的output用于评测（关键改进！）
        output = self._extract_evaluation_output(execution, task_type)

        # 根据task_type评测
        if task_type == 'sql_query':
            result = self._evaluate_sql_query(execution, test_case, rubric, output)
        elif task_type == 'analysis':
            result = self._evaluate_analysis(execution, test_case, rubric, output)
        else:  # document_search 或其他
            result = self._evaluate_document_search(execution, test_case, rubric, output)

        # 添加元信息（用户可以验证推断是否正确）
        result['detected_task_type'] = task_type
        result['was_explicitly_set'] = 'task_type' in test_case

        return result

    def _evaluate_document_search(self, execution, test_case, rubric, output) -> Dict[str, Any]:
        """文档搜索类任务评测"""
        # 评测4个维度
        keyword_result = self._check_keywords(output, test_case)
        length_result = self._check_length(output, test_case)
        bad_words_result = self._check_bad_words(output, test_case)
        tools_result = self._check_tools(execution, test_case)

        # 加权综合评分（按rubric的权重）
        weights = {c.name: c.weight for c in rubric.criteria}
        overall_score = (
            keyword_result["score"] * weights.get("keyword_coverage", 0.3) +
            length_result["score"] * weights.get("length_ok", 0.25) +
            bad_words_result["score"] * weights.get("no_bad_words", 0.2) +
            tools_result["score"] * weights.get("tools_ok", 0.25)
        )

        overall_score = max(0.0, min(1.0, overall_score))

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

        # 计算平均confidence
        avg_confidence = (
            keyword_result["confidence"] * weights.get("keyword_coverage", 0.3) +
            length_result["confidence"] * weights.get("length_ok", 0.25) +
            bad_words_result["confidence"] * weights.get("no_bad_words", 0.2) +
            tools_result["confidence"] * weights.get("tools_ok", 0.25)
        )

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
            "passed": overall_score >= rubric.pass_threshold,
            "confidence": avg_confidence,
        }

    def _evaluate_sql_query(self, execution, test_case, rubric, output) -> Dict[str, Any]:
        """SQL查询类任务评测"""
        # 1️⃣ SQL执行成功性
        sql_success = self._check_sql_success(execution, test_case)

        # 2️⃣ 结果行数合理性
        result_count = self._check_result_count(output, test_case)

        # 3️⃣ 结果准确性（如果有reference）
        result_accuracy = self._check_result_accuracy(output, test_case, execution)

        # 4️⃣ 执行效率
        performance = self._check_performance(execution, test_case)

        # 加权综合
        weights = {c.name: c.weight for c in rubric.criteria}
        overall_score = (
            sql_success["score"] * weights.get("sql_success", 0.35) +
            result_count["score"] * weights.get("result_count", 0.25) +
            result_accuracy["score"] * weights.get("result_accuracy", 0.25) +
            performance["score"] * weights.get("performance", 0.15)
        )

        overall_score = max(0.0, min(1.0, overall_score))

        avg_confidence = (
            sql_success["confidence"] * weights.get("sql_success", 0.35) +
            result_count["confidence"] * weights.get("result_count", 0.25) +
            result_accuracy["confidence"] * weights.get("result_accuracy", 0.25) +
            performance["confidence"] * weights.get("performance", 0.15)
        )

        reasoning = f"{sql_success['justification']}；{result_count['justification']}；{result_accuracy['justification']}；{performance['justification']}"

        return {
            "score": overall_score,
            "details": {
                "sql_success": sql_success,
                "result_count": result_count,
                "result_accuracy": result_accuracy,
                "performance": performance,
            },
            "reasoning": reasoning,
            "passed": overall_score >= rubric.pass_threshold,
            "confidence": avg_confidence,
        }

    def _evaluate_analysis(self, execution, test_case, rubric, output) -> Dict[str, Any]:
        """数据分析类任务评测"""
        # 1️⃣ 是否包含期望指标
        metric_presence = self._check_metric_presence(output, test_case)

        # 2️⃣ 数值准确性
        numerical_accuracy = self._check_numerical_accuracy(output, test_case, execution)

        # 3️⃣ 结果格式
        result_format = self._check_result_format(output, test_case)

        # 4️⃣ 禁词检查
        bad_words_result = self._check_bad_words(output, test_case)

        weights = {c.name: c.weight for c in rubric.criteria}
        overall_score = (
            metric_presence["score"] * weights.get("metric_presence", 0.35) +
            numerical_accuracy["score"] * weights.get("numerical_accuracy", 0.35) +
            result_format["score"] * weights.get("result_format", 0.2) +
            bad_words_result["score"] * weights.get("no_bad_words", 0.1)
        )

        overall_score = max(0.0, min(1.0, overall_score))

        avg_confidence = (
            metric_presence["confidence"] * weights.get("metric_presence", 0.35) +
            numerical_accuracy["confidence"] * weights.get("numerical_accuracy", 0.35) +
            result_format["confidence"] * weights.get("result_format", 0.2) +
            bad_words_result["confidence"] * weights.get("no_bad_words", 0.1)
        )


        reasoning = f"{metric_presence['justification']}；{numerical_accuracy['justification']}；{result_format['justification']}"

        return {
            "score": overall_score,
            "details": {
                "metric_presence": metric_presence,
                "numerical_accuracy": numerical_accuracy,
                "result_format": result_format,
                "no_bad_words": bad_words_result,
            },
            "reasoning": reasoning,
            "passed": overall_score >= rubric.pass_threshold,
            "confidence": avg_confidence,
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

    def _extract_tool_output(self, execution, tool_name: str) -> str:
        """
        从execution_steps中提取特定工具的原始输出

        execution_steps是ExecutionStep对象转为dict后的列表，
        每个step包含 tool_name 和 tool_output 字段
        """
        if not hasattr(execution, 'execution_steps'):
            return ""

        execution_steps = getattr(execution, 'execution_steps', [])

        # 遍历execution_steps找对应工具的TOOL_END步骤
        for step in execution_steps:
            if isinstance(step, dict):
                # 查找tool_end类型且工具名匹配的步骤
                if step.get('step_type') == 'tool_end' and step.get('tool_name') == tool_name:
                    tool_output = step.get('tool_output', '')
                    if tool_output:
                        logger.debug(f"提取工具{tool_name}的输出: {len(tool_output)}字符")
                        return tool_output

        logger.debug(f"未找到工具{tool_name}的输出")
        return ""

    def _infer_task_type(self, execution, test_case) -> str:
        """
        自动推断任务类型

        优先级：
        1. 显式指定的task_type
        2. 根据tools_used推断
        3. 根据output内容推断
        4. 默认为document_search
        """
        # 1️⃣ 如果test_case显式指定，优先使用
        if 'task_type' in test_case:
            return test_case['task_type']

        # 2️⃣ 根据tools_used推断
        tools_used = getattr(execution, 'tools_used', [])
        if 'sql_query' in tools_used:
            return 'sql_query'
        if isinstance(tools_used, list) and len(tools_used) == 1:
            tool = tools_used[0]
            if tool == 'document_search':
                return 'document_search'

        # 3️⃣ 根据output内容推断
        output = self._extract_output(execution)

        # 有表格结构（\t或|）+ 数字 → 可能是sql或analysis
        if ('\t' in output or '|' in output) and any(c.isdigit() for c in output):
            # 如果有统计关键词 → analysis
            if any(kw in output for kw in ['共', '总', '合计', '占比', '%']):
                return 'analysis'
            # 否则 → sql_query
            return 'sql_query'

        # 4️⃣ 默认为document_search
        return 'document_search'

    def _extract_evaluation_output(self, execution, task_type: str) -> str:
        """
        根据任务类型，提取用于评测的output

        关键：不同任务类型用不同的output来源
        - sql_query → 提取sql_query工具的原始输出
        - analysis → 提取sql_query或文档搜索的输出
        - document_search → 提取document_search工具的输出
        """
        if task_type == 'sql_query':
            # SQL评测：用sql_query工具的原始输出（最准确）
            tool_output = self._extract_tool_output(execution, 'sql_query')
            if tool_output:
                return tool_output
            # 降级：如果找不到工具输出，用综合output
            return self._extract_output(execution)

        elif task_type == 'analysis':
            # 分析评测：优先用sql_query输出，其次综合output
            sql_output = self._extract_tool_output(execution, 'sql_query')
            if sql_output:
                return sql_output
            return self._extract_output(execution)

        else:  # document_search
            # 文档搜索评测：用document_search工具的输出
            tool_output = self._extract_tool_output(execution, 'document_search')
            if tool_output:
                return tool_output
            # 降级：综合output
            return self._extract_output(execution)

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

    # ============= SQL查询评测维度方法 =============

    def _check_sql_success(self, execution, test_case) -> Dict[str, Any]:
        """SQL是否成功执行"""
        is_success = getattr(execution, 'error_message', '') == ''

        if is_success:
            score = 1.0
            justification = "SQL执行成功✓"
            confidence = 0.99
        else:
            score = 0.0
            error = getattr(execution, 'error_message', '未知错误')
            justification = f"SQL执行失败: {error[:50]}"
            confidence = 0.98

        logger.debug(justification)

        return {
            "score": score,
            "justification": justification,
            "confidence": confidence,
        }

    def _check_result_count(self, output: str, test_case) -> Dict[str, Any]:
        """检查返回的结果行数是否合理"""
        expected = test_case.get("expected", {})
        min_rows = expected.get("expected_min_rows", 1)
        max_rows = expected.get("expected_max_rows", 1000)

        # 粗略计数（去掉表头）
        lines = output.strip().split('\n')
        actual_rows = max(0, len(lines) - 1)

        # 边界情况处理：0行结果可能是正确的
        if actual_rows == 0 and min_rows == 0:
            score = 1.0
            justification = "返回0行（符合查询条件）✓"
            confidence = 0.9
        elif min_rows <= actual_rows <= max_rows:
            score = 1.0
            justification = f"返回{actual_rows}行，在范围[{min_rows}, {max_rows}]内✓"
            confidence = 0.95
        elif actual_rows < min_rows:
            score = 0.3
            justification = f"返回行数不足：{actual_rows}行（期望≥{min_rows}）"
            confidence = 0.85
        else:
            score = 0.5
            justification = f"返回行数过多：{actual_rows}行（期望≤{max_rows}）"
            confidence = 0.85

        logger.debug(f"结果行数检查：{justification}")

        return {
            "score": score,
            "justification": justification,
            "confidence": confidence,
            "actual_rows": actual_rows,
        }

    def _check_result_accuracy(self, output: str, test_case, execution) -> Dict[str, Any]:
        """检查结果准确性（与reference对比）"""
        expected_output = test_case.get("expected", {}).get("expected_output")

        # 如果没有reference，无法检查准确性
        if not expected_output:
            return {
                "score": 1.0,
                "justification": "未指定reference，无法校验准确性",
                "confidence": 0.6,
            }

        # 简单对比：是否包含关键信息
        # 实际实现可以更复杂（如数值对比、结构对比）
        expected_lower = expected_output.lower()
        output_lower = output.lower()

        # 提取expected_output中的关键数字/值
        expected_values = set(re.findall(r'\d+\.?\d*', expected_output))
        actual_values = set(re.findall(r'\d+\.?\d*', output))

        if not expected_values:
            # 无关键数值，无法检查
            return {
                "score": 1.0,
                "justification": "无数值reference，无法校验准确性",
                "confidence": 0.5,
            }

        matched = expected_values & actual_values
        accuracy_ratio = len(matched) / len(expected_values)

        if accuracy_ratio >= 0.9:
            score = 1.0
            confidence = 0.95
            justification = "结果准确性高✓"
        elif accuracy_ratio >= 0.7:
            score = 0.7
            confidence = 0.85
            justification = f"结果准确性一般：{accuracy_ratio:.0%}匹配"
        else:
            score = 0.3
            confidence = 0.9
            justification = f"结果可能有误：仅{accuracy_ratio:.0%}值匹配"

        logger.debug(f"结果准确性检查：{justification}")

        return {
            "score": score,
            "justification": justification,
            "confidence": confidence,
            "expected_values": list(expected_values),
            "actual_values": list(actual_values),
            "matched": list(matched),
        }

    def _check_performance(self, execution, test_case) -> Dict[str, Any]:
        """检查SQL执行效率"""
        execution_time = getattr(execution, 'execution_time', 999)
        target_time = test_case.get("expected", {}).get("expected_time", 3.0)

        if execution_time < target_time * 0.5:
            score = 1.0
            justification = f"执行很快：{execution_time:.2f}秒✓"
            confidence = 0.9
        elif execution_time < target_time:
            score = 0.9
            justification = f"执行正常：{execution_time:.2f}秒"
            confidence = 0.9
        elif execution_time < target_time * 1.5:
            score = 0.7
            justification = f"执行略慢：{execution_time:.2f}秒"
            confidence = 0.85
        else:
            score = 0.4
            justification = f"执行太慢：{execution_time:.2f}秒（超过{target_time}秒）"
            confidence = 0.9

        logger.debug(f"性能检查：{justification}")

        return {
            "score": score,
            "justification": justification,
            "confidence": confidence,
            "execution_time": execution_time,
        }

    # ============= 分析任务评测维度方法 =============

    def _check_metric_presence(self, output: str, test_case) -> Dict[str, Any]:
        """检查是否包含期望的指标"""
        expected_metrics = test_case.get("expected", {}).get("expected_metrics", [])

        if not expected_metrics:
            return {
                "score": 1.0,
                "justification": "未指定期望指标",
                "confidence": 0.7,
            }

        output_lower = output.lower()
        found_metrics = []
        missing_metrics = []

        for metric in expected_metrics:
            if metric.lower() in output_lower:
                found_metrics.append(metric)
            else:
                missing_metrics.append(metric)

        metric_coverage = len(found_metrics) / len(expected_metrics)

        if not missing_metrics:
            score = 1.0
            confidence = 0.95
            justification = f"包含所有期望指标✓"
        elif len(found_metrics) >= len(expected_metrics) * 0.7:
            score = 0.8
            confidence = 0.85
            justification = f"包含{len(found_metrics)}/{len(expected_metrics)}个指标"
        else:
            score = 0.3
            confidence = 0.9
            justification = f"缺少关键指标：{missing_metrics}"

        logger.debug(f"指标检查：{justification}")

        return {
            "score": score,
            "justification": justification,
            "confidence": confidence,
            "found": found_metrics,
            "missing": missing_metrics,
        }

    def _check_numerical_accuracy(self, output: str, test_case, execution) -> Dict[str, Any]:
        """检查数值准确性"""
        expected_values = test_case.get("expected", {}).get("expected_values")

        if not expected_values:
            return {
                "score": 1.0,
                "justification": "未指定数值reference",
                "confidence": 0.5,
            }

        # 提取输出中的所有数字
        actual_values = re.findall(r'\d+\.?\d*', output)

        if not actual_values:
            return {
                "score": 0.0,
                "justification": "未找到数值输出",
                "confidence": 0.95,
            }

        # 允许approximation
        allow_approximation = test_case.get("expected", {}).get("allow_approximation", False)
        tolerance = 0.1 if allow_approximation else 0.0  # 允许±10%误差

        matched_count = 0
        for expected in expected_values:
            expected_val = float(expected)
            for actual in actual_values:
                actual_val = float(actual)
                if abs(actual_val - expected_val) <= expected_val * tolerance:
                    matched_count += 1
                    break

        accuracy = matched_count / len(expected_values)

        if accuracy >= 0.95:
            score = 1.0
            confidence = 0.95
            justification = "数值准确✓"
        elif accuracy >= 0.8:
            score = 0.8
            confidence = 0.9
            justification = f"数值基本准确：{accuracy:.0%}匹配"
        else:
            score = 0.3
            confidence = 0.9
            justification = f"数值可能有误：仅{accuracy:.0%}匹配"

        return {
            "score": score,
            "justification": justification,
            "confidence": confidence,
        }

    def _check_result_format(self, output: str, test_case) -> Dict[str, Any]:
        """检查结果格式是否清晰"""
        expected_format = test_case.get("expected", {}).get("expected_format")

        # 简单启发式检查
        has_structure = '\n' in output or '\t' in output or '，' in output
        has_summary = any(keyword in output for keyword in ['共', '总', '小计', '总计'])

        if expected_format == "table":
            is_ok = '\t' in output or '|' in output
        elif expected_format == "summary":
            is_ok = has_summary
        else:
            is_ok = has_structure

        if is_ok:
            score = 1.0
            justification = "结果格式清晰✓"
            confidence = 0.85
        else:
            score = 0.5
            justification = "结果格式不够清晰"
            confidence = 0.8

        return {
            "score": score,
            "justification": justification,
            "confidence": confidence,
        }
