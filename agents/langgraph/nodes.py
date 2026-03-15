"""LangGraph Agent 节点函数"""

import logging
import time
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from langchain_core.language_models import BaseLLM
from langchain_core.tools import BaseTool

from .state import AgentState, ExecutionStep

logger = logging.getLogger(__name__)


class NodeManager:
    """管理所有Agent节点函数"""

    def __init__(self, llm: BaseLLM, tools: List[BaseTool], memory_manager: Optional[object] = None):
        self.llm = llm
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}
        self.memory_manager = memory_manager

    def process_input_node(self, state: AgentState) -> Dict[str, Any]:
        """处理用户输入"""
        logger.info(f"Processing input for user {state['user_id']}: {state['user_input']}")

        # 从记忆中检索相关上下文
        memory_context = None
        if self.memory_manager:
            try:
                memory_context = self.memory_manager.retrieve_relevant_memory(
                    query=state['user_input'],
                    top_k=5
                )
                if memory_context:
                    logger.info(f"Retrieved memory context: {memory_context[:100]}...")
            except Exception as e:
                logger.error(f"Failed to retrieve memory: {e}")

        return {
            "memory_context": memory_context,
            "iteration": 0,
        }

    def agent_loop_node(self, state: AgentState) -> Dict[str, Any]:
        """Agent推理步骤"""
        if state["iteration"] > 0:
            logger.info(f"Agent loop iteration {state['iteration']}")

        # 构建Prompt
        prompt = self._build_prompt(state)

        # 调用LLM
        try:
            response = self.llm.predict(prompt)
        except Exception as e:
            logger.error(f"LLM prediction error: {e}")
            response = "I encountered an error while thinking about this problem."

        # 更新scratchpad
        new_scratchpad = state["agent_scratchpad"] + response + "\n"

        # 记录执行步骤
        step = ExecutionStep(
            step_type="thought",
            tool_name=None,
            tool_input=None,
            tool_output=None,
            timestamp=datetime.now(),
            duration=0.0
        )

        return {
            "agent_scratchpad": new_scratchpad,
            "execution_steps": state["execution_steps"] + [step],
            "iteration": state["iteration"] + 1,
        }

    def tool_execution_node(self, state: AgentState) -> Dict[str, Any]:
        """执行工具"""
        # 从scratchpad解析出Action
        action = self._parse_action_from_scratchpad(state["agent_scratchpad"])

        if not action:
            return {"error_message": "Failed to parse action"}

        tool_name = action.tool
        tool_input = action.tool_input

        logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

        try:
            # 获取工具
            tool = self.tool_map.get(tool_name)
            if not tool:
                error = f"Tool {tool_name} not found"
                return {"error_message": error}

            # 执行工具
            start = time.time()
            result = tool.run(tool_input)
            duration = time.time() - start

            # 记录执行步骤
            step = ExecutionStep(
                step_type="tool_call",
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=result,
                timestamp=datetime.now(),
                duration=duration
            )

            return {
                "current_tool": tool_name,
                "tools_used": state["tools_used"] + [tool_name],
                "observations": state["observations"] + [result],
                "masked_observations": state["masked_observations"] + [result],
                "execution_steps": state["execution_steps"] + [step],
                "agent_scratchpad": state["agent_scratchpad"] + f"Observation: {result}\n",
                "retry_count": 0,
            }

        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            error_msg = f"Tool execution error: {str(e)}"
            return {
                "error_message": error_msg,
                "retry_count": state["retry_count"] + 1,
            }

    def evaluate_node(self, state: AgentState) -> Dict[str, Any]:
        """评测执行结果"""
        logger.info("Evaluating execution result")

        # 返回简单的评测结果
        return {
            "evaluation_result": {"score": 0.8, "passed": True},
            "eval_passed": True,
            "eval_score": 0.8,
        }

    def final_answer_node(self, state: AgentState) -> Dict[str, Any]:
        """生成最终答案"""
        logger.info("Generating final answer")

        # 从scratchpad提取最终答案
        final_answer = self._extract_final_answer(state["agent_scratchpad"])

        # 计算总时长
        end_time = datetime.now()
        duration = (end_time - state["start_time"]).total_seconds() if state["start_time"] else 0.0

        return {
            "final_answer": final_answer,
            "end_time": end_time,
            "total_duration": duration,
        }

    def error_handler_node(self, state: AgentState) -> Dict[str, Any]:
        """错误处理"""
        logger.error(f"Error in execution: {state.get('error_message')}")

        return {
            "final_answer": f"Error: {state.get('error_message', 'Unknown error')}",
            "error_message": state.get("error_message"),
        }

    # ============ 辅助方法 ============

    def _build_prompt(self, state: AgentState) -> str:
        """构建Agent提示词"""
        tools_str = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])

        prompt = f"""You are a helpful AI assistant.

User input: {state['user_input']}

Tools available:
{tools_str}

Thought process:
{state['agent_scratchpad']}

Next action:"""
        return prompt

    def _parse_action_from_scratchpad(self, scratchpad: str):
        """从scratchpad解析Action"""
        # 查找 "Action: [tool_name]" 和 "Action Input: [input]"
        action_match = re.search(r'Action:\s*(\w+)', scratchpad)
        input_match = re.search(r'Action Input:\s*(.*?)(?:\n|$)', scratchpad)

        if action_match and input_match:
            tool_name = action_match.group(1)
            tool_input = input_match.group(1).strip()

            class Action:
                def __init__(self, tool, input):
                    self.tool = tool
                    self.tool_input = input

            return Action(tool_name, tool_input)

        return None

    def _extract_final_answer(self, scratchpad: str) -> str:
        """从scratchpad提取最终答案"""
        final_match = re.search(r'Final Answer:\s*(.*?)(?:$|\n\n)', scratchpad, re.DOTALL)
        if final_match:
            return final_match.group(1).strip()

        return scratchpad.split('\n')[-1] if scratchpad else "No answer generated"
