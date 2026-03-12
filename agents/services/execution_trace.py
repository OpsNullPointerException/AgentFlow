"""
增强的执行追踪模块

记录Agent执行的细粒度过程：思考链、工具决策、执行细节等
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum
from loguru import logger


class StepType(Enum):
    """执行步骤类型"""

    THINKING = "thinking"  # 思考过程
    TOOL_SELECTION = "tool_selection"  # 工具选择决策
    TOOL_START = "tool_start"  # 工具开始执行
    TOOL_END = "tool_end"  # 工具执行完成
    TOOL_ERROR = "tool_error"  # 工具执行错误
    LLM_START = "llm_start"  # LLM开始生成
    LLM_END = "llm_end"  # LLM生成完成
    FINAL_ANSWER = "final_answer"  # 最终答案


@dataclass
class ExecutionStep:
    """单个执行步骤"""

    step_type: StepType
    timestamp: datetime
    content: str

    # 详细信息
    tool_name: Optional[str] = None  # 工具名称（tool_*步骤）
    tool_input: Optional[Dict[str, Any]] = None  # 工具输入
    tool_output: Optional[str] = None  # 工具输出
    duration: Optional[float] = None  # 执行耗时（秒）
    error: Optional[str] = None  # 错误信息
    token_count: Optional[int] = None  # Token数量

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        """转换为字典"""
        data = asdict(self)
        data["step_type"] = self.step_type.value
        data["timestamp"] = self.timestamp.isoformat()
        return data


class ExecutionTrace:
    """完整的执行追踪"""

    def __init__(self, execution_id: str, agent_id: str, user_input: str):
        """
        初始化执行追踪

        Args:
            execution_id: 执行ID
            agent_id: Agent ID
            user_input: 用户输入
        """
        self.execution_id = execution_id
        self.agent_id = agent_id
        self.user_input = user_input
        self.steps: List[ExecutionStep] = []
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None

    def add_thinking_step(self, content: str, metadata: Dict[str, Any] = None):
        """记录思考步骤"""
        step = ExecutionStep(
            step_type=StepType.THINKING,
            timestamp=datetime.now(),
            content=content,
            metadata=metadata or {},
        )
        self.steps.append(step)
        logger.info(f"[思考] {content[:100]}")

    def add_tool_selection_step(
        self,
        candidates: List[str],
        selected: str,
        reasoning: str,
        metadata: Dict[str, Any] = None,
    ):
        """记录工具选择决策"""
        step = ExecutionStep(
            step_type=StepType.TOOL_SELECTION,
            timestamp=datetime.now(),
            content=reasoning,
            tool_name=selected,
            metadata={
                "candidates": candidates,
                "selected": selected,
                **(metadata or {}),
            },
        )
        self.steps.append(step)
        logger.info(f"[工具选择] 选择: {selected}，候选: {candidates}")

    def add_tool_execution_start(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        metadata: Dict[str, Any] = None,
    ):
        """记录工具执行开始"""
        step = ExecutionStep(
            step_type=StepType.TOOL_START,
            timestamp=datetime.now(),
            content=f"开始执行工具: {tool_name}",
            tool_name=tool_name,
            tool_input=tool_input,
            metadata=metadata or {},
        )
        self.steps.append(step)
        logger.info(f"[工具执行] 开始: {tool_name}, 输入: {str(tool_input)[:100]}")

    def add_tool_execution_end(
        self,
        tool_name: str,
        tool_output: str,
        duration: float,
        metadata: Dict[str, Any] = None,
    ):
        """记录工具执行结束"""
        step = ExecutionStep(
            step_type=StepType.TOOL_END,
            timestamp=datetime.now(),
            content=f"工具执行完成: {tool_name}",
            tool_name=tool_name,
            tool_output=tool_output[:500],  # 限制输出长度
            duration=duration,
            metadata=metadata or {},
        )
        self.steps.append(step)
        logger.info(
            f"[工具执行] 完成: {tool_name}, 耗时: {duration:.2f}秒, "
            f"输出长度: {len(tool_output)}"
        )

    def add_tool_error(
        self,
        tool_name: str,
        error: str,
        tool_input: Optional[Dict[str, Any]] = None,
        metadata: Dict[str, Any] = None,
    ):
        """记录工具执行错误"""
        step = ExecutionStep(
            step_type=StepType.TOOL_ERROR,
            timestamp=datetime.now(),
            content=f"工具执行错误: {tool_name}",
            tool_name=tool_name,
            tool_input=tool_input,
            error=error,
            metadata=metadata or {},
        )
        self.steps.append(step)
        logger.warning(f"[工具错误] {tool_name}: {error}")

    def add_llm_generation_start(
        self,
        prompt_length: int,
        metadata: Dict[str, Any] = None,
    ):
        """记录LLM生成开始"""
        step = ExecutionStep(
            step_type=StepType.LLM_START,
            timestamp=datetime.now(),
            content=f"LLM开始生成，提示长度: {prompt_length}",
            token_count=prompt_length,
            metadata=metadata or {},
        )
        self.steps.append(step)
        logger.info(f"[LLM] 开始生成，提示长度: {prompt_length}")

    def add_llm_generation_end(
        self,
        output: str,
        token_count: int,
        duration: float,
        metadata: Dict[str, Any] = None,
    ):
        """记录LLM生成完成"""
        step = ExecutionStep(
            step_type=StepType.LLM_END,
            timestamp=datetime.now(),
            content=output[:500],  # 限制内容长度
            token_count=token_count,
            duration=duration,
            metadata=metadata or {},
        )
        self.steps.append(step)
        logger.info(f"[LLM] 生成完成，输出长度: {len(output)}, Token: {token_count}")

    def add_final_answer(self, answer: str, metadata: Dict[str, Any] = None):
        """记录最终答案"""
        step = ExecutionStep(
            step_type=StepType.FINAL_ANSWER,
            timestamp=datetime.now(),
            content=answer[:1000],  # 限制长度
            metadata=metadata or {},
        )
        self.steps.append(step)
        logger.info(f"[最终答案] 长度: {len(answer)}")

    def finish(self):
        """标记追踪完成"""
        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()
        logger.info(f"执行追踪完成，总耗时: {duration:.2f}秒")

    def get_summary(self) -> Dict[str, Any]:
        """获取追踪摘要"""
        duration = (
            (self.end_time - self.start_time).total_seconds()
            if self.end_time
            else None
        )

        step_types = {}
        for step in self.steps:
            key = step.step_type.value
            step_types[key] = step_types.get(key, 0) + 1

        total_duration = sum(
            step.duration for step in self.steps if step.duration is not None
        )
        total_tokens = sum(
            step.token_count for step in self.steps if step.token_count is not None
        )

        return {
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "total_steps": len(self.steps),
            "step_breakdown": step_types,
            "total_duration": duration,
            "execution_duration": total_duration,
            "total_tokens": total_tokens,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }

    def get_detailed_trace(self) -> List[Dict[str, Any]]:
        """获取完整的详细追踪"""
        return [step.to_dict() for step in self.steps]

    def get_thinking_chain(self) -> List[str]:
        """获取思考链"""
        return [
            step.content
            for step in self.steps
            if step.step_type == StepType.THINKING
        ]

    def get_tool_sequence(self) -> List[Dict[str, Any]]:
        """获取工具调用序列"""
        sequence = []
        for step in self.steps:
            if step.step_type in (
                StepType.TOOL_START,
                StepType.TOOL_END,
                StepType.TOOL_ERROR,
            ):
                sequence.append(
                    {
                        "tool": step.tool_name,
                        "type": step.step_type.value,
                        "duration": step.duration,
                        "error": step.error,
                    }
                )
        return sequence

    def export(self, format: str = "json") -> Dict[str, Any]:
        """
        导出追踪数据

        Args:
            format: 导出格式 ('json', 'summary', 'detailed')

        Returns:
            导出的数据
        """
        if format == "summary":
            return self.get_summary()
        elif format == "detailed":
            return {
                "summary": self.get_summary(),
                "trace": self.get_detailed_trace(),
                "thinking_chain": self.get_thinking_chain(),
                "tool_sequence": self.get_tool_sequence(),
            }
        else:  # json (default)
            return {
                "execution_id": self.execution_id,
                "agent_id": self.agent_id,
                "user_input": self.user_input,
                "summary": self.get_summary(),
                "trace": self.get_detailed_trace(),
            }
