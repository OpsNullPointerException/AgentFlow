"""
LLM-as-Judge评测模块

使用LLM自动评测Agent的执行效果
"""

import json
import re
from typing import Any, Dict, Optional
from loguru import logger


class LLMJudge:
    """使用LLM进行自动评测的Judge"""

    def __init__(self, llm_service):
        """
        初始化LLMJudge

        Args:
            llm_service: LLM服务实例（需要提供call_llm方法）
        """
        self.llm_service = llm_service

    async def judge_dimension(
        self,
        dimension: str,
        agent_output: str,
        user_input: str,
        execution_steps: list,
        ground_truth: Optional[dict] = None,
        rubric_config: Optional[dict] = None,
    ) -> float:
        """
        用LLM评测某个维度

        Args:
            dimension: 评测维度（accuracy, completeness等）
            agent_output: Agent输出
            user_input: 用户输入
            execution_steps: 执行步骤
            ground_truth: 预期结果
            rubric_config: 评测标准配置

        Returns:
            float: 该维度的评分（0-1）
        """
        try:
            # 构造评测提示词
            evaluation_prompt = self._build_evaluation_prompt(
                dimension=dimension,
                user_input=user_input,
                agent_output=agent_output,
                execution_steps=execution_steps,
                ground_truth=ground_truth,
                rubric_config=rubric_config,
            )

            # 调用LLM（使用同步方式或异步方式取决于实现）
            response = await self.llm_service.call_llm(
                prompt=evaluation_prompt,
                temperature=0.1,  # 低温度保证一致性
                response_format="json",
                max_tokens=500,
            )

            # 解析并返回评分
            score = self._parse_score(response)
            logger.info(f"评测{dimension}维度：{score:.2f}")

            return score

        except Exception as e:
            logger.error(f"LLM评测失败: {e}")
            # 降级处理：返回中等评分
            return 0.5

    def _build_evaluation_prompt(
        self,
        dimension: str,
        user_input: str,
        agent_output: str,
        execution_steps: list,
        ground_truth: Optional[dict],
        rubric_config: Optional[dict],
    ) -> str:
        """构造LLM评测提示词"""

        # 格式化执行步骤
        steps_str = json.dumps(execution_steps, ensure_ascii=False, indent=2)

        # 格式化预期结果
        ground_truth_str = (
            json.dumps(ground_truth, ensure_ascii=False, indent=2)
            if ground_truth
            else "无（开放式评测）"
        )

        # 格式化评测标准
        levels_description = ""
        if rubric_config and "levels" in rubric_config:
            for level, (min_val, max_val) in rubric_config["levels"].items():
                levels_description += f"\n- {level}: {min_val}-{max_val}"

        prompt = f"""您是一个AI评估专家，需要评估一个智能Agent的执行效果。

【评测维度】
{dimension}

【维度描述】
{rubric_config.get('description', '无描述') if rubric_config else '无描述'}

【评分等级】{levels_description}

【用户输入】
{user_input}

【Agent输出】
{agent_output}

【执行步骤】
{steps_str}

【预期结果】
{ground_truth_str}

请根据以上标准，评估Agent在"{dimension}"维度的表现，并给出：
1. 评分（0-1之间，详细到小数点后两位）
2. 简短理由（1-2句话）
3. 评分等级（excellent/good/fair/poor）

返回JSON格式（严格遵循以下格式）：
{{
    "score": <0到1之间的数字>,
    "reasoning": "<理由>",
    "level": "<等级>"
}}

只返回JSON，不要其他文字。"""

        return prompt

    def _parse_score(self, response: str) -> float:
        """
        从LLM响应中解析评分

        Args:
            response: LLM的文本响应

        Returns:
            float: 解析出的评分（0-1）
        """
        try:
            # 尝试解析JSON
            response_data = json.loads(response)

            if isinstance(response_data, dict) and "score" in response_data:
                score = float(response_data["score"])
                return max(0.0, min(1.0, score))

        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        # 降级方案1：尝试用正则提取数字
        try:
            numbers = re.findall(r"0\.\d+|\d+\.\d+", response)
            if numbers:
                score = float(numbers[0])
                if 0 <= score <= 1:
                    logger.info(f"从文本中提取得分：{score}")
                    return score
        except (ValueError, IndexError):
            pass

        # 降级方案2：查找关键词
        response_lower = response.lower()
        if "excellent" in response_lower:
            return 0.9
        elif "good" in response_lower:
            return 0.75
        elif "fair" in response_lower:
            return 0.6
        elif "poor" in response_lower:
            return 0.3

        # 默认返回中等评分
        logger.warning("无法解析LLM评分，返回默认值0.5")
        return 0.5


# 同步版本的Judge（用于测试和不支持异步的场景）
class LLMJudgeSync:
    """同步版本的LLM-as-Judge"""

    def __init__(self, llm_service):
        self.llm_service = llm_service

    def judge_dimension(
        self,
        dimension: str,
        agent_output: str,
        user_input: str,
        execution_steps: list,
        ground_truth: Optional[dict] = None,
        rubric_config: Optional[dict] = None,
    ) -> float:
        """同步评测接口"""

        try:
            judge = LLMJudge(self.llm_service)
            evaluation_prompt = judge._build_evaluation_prompt(
                dimension=dimension,
                user_input=user_input,
                agent_output=agent_output,
                execution_steps=execution_steps,
                ground_truth=ground_truth,
                rubric_config=rubric_config,
            )

            # 调用同步LLM服务
            if hasattr(self.llm_service, "call_llm_sync"):
                response = self.llm_service.call_llm_sync(
                    prompt=evaluation_prompt,
                    temperature=0.1,
                    response_format="json",
                    max_tokens=500,
                )
            else:
                # 如果没有同步方法，返回默认值
                logger.warning("LLM服务不支持同步调用")
                return 0.5

            score = judge._parse_score(response)
            return score

        except Exception as e:
            logger.error(f"同步LLM评测失败: {e}")
            return 0.5
