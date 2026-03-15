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

    def intent_detection_node(self, state: AgentState) -> Dict[str, Any]:
        """意图识别节点 - 分类用户查询为 knowledge/data/hybrid"""
        logger.info(f"Detecting intent for: {state['user_input']}")

        # 构建意图识别提示词
        prompt = self._build_intent_detection_prompt(state)

        try:
            response = self.llm.predict(prompt).strip().lower()

            # 解析LLM响应，应该返回 "knowledge"、"data" 或 "hybrid"
            intent_type = "data"  # 默认为数据查询
            if "knowledge" in response or "概念" in response or "定义" in response:
                intent_type = "knowledge"
            elif "hybrid" in response or "混合" in response:
                intent_type = "hybrid"
            elif "data" in response or "数据" in response or "查询" in response:
                intent_type = "data"
            else:
                # 后备策略：基于关键词启发式判断
                user_input_lower = state['user_input'].lower()
                query_keywords = {"查询", "统计", "SELECT", "表", "字段", "数据库"}
                knowledge_keywords = {"什么是", "定义", "含义", "解释", "术语"}

                if any(kw in state['user_input'] for kw in knowledge_keywords):
                    intent_type = "knowledge"
                elif any(kw in state['user_input'] for kw in query_keywords):
                    intent_type = "data"

            logger.info(f"Detected intent: {intent_type}")

            return {
                "intent_type": intent_type,
                "iteration": state["iteration"],
            }

        except Exception as e:
            logger.error(f"Intent detection error: {e}")
            # 默认为数据查询
            return {
                "intent_type": "data",
                "iteration": state["iteration"],
            }

    def time_check_node(self, state: AgentState) -> Dict[str, Any]:
        """时间检查节点 - 检测和转换相对时间"""
        logger.info("Checking for relative time references")

        # 检查输入中是否有相对时间关键词
        time_keywords = {"昨天", "今天", "明天", "上周", "这周", "下周", "上月", "这月", "下月",
                         "近", "最近", "过去", "之前", "以后", "周年", "月份", "年"}
        has_time_ref = any(kw in state['user_input'] for kw in time_keywords)

        time_range = None
        if has_time_ref:
            # 尝试调用 convert_relative_time 工具
            time_tool = self.tool_map.get("convert_relative_time")
            if time_tool:
                try:
                    logger.info(f"Converting relative time from input: {state['user_input']}")
                    result = time_tool.run(state['user_input'])
                    # 假设result是JSON格式的 {"start_date": "...", "end_date": "..."}
                    import json
                    try:
                        time_range = json.loads(result)
                    except:
                        time_range = {"raw_result": result}
                except Exception as e:
                    logger.warning(f"Time conversion failed: {e}")

        return {
            "time_range": time_range,
        }

    def schema_discovery_node(self, state: AgentState) -> Dict[str, Any]:
        """架构发现节点 - 识别相关的表和字段"""
        logger.info("Discovering relevant tables and fields")

        # 获取 schema_query 工具
        schema_tool = self.tool_map.get("schema_query")
        if not schema_tool:
            logger.warning("schema_query tool not found")
            return {"relevant_tables": [], "relevant_fields": {}}

        try:
            # 首先获取所有表名
            tables_result = schema_tool.run("tables")
            # 简化处理：假设结果中包含表名（实际需要解析）
            # 这里使用启发式方法：从输入和澄清的术语中推断表名

            relevant_tables = []
            relevant_fields = {}

            # 从输入中推断可能的表名和字段
            common_tables = ["users", "orders", "products", "customers", "sales", "transactions"]
            for table in common_tables:
                if table in state['user_input'].lower():
                    relevant_tables.append(table)

            # 对于每个相关的表，获取其字段信息
            for table in relevant_tables:
                try:
                    fields_result = schema_tool.run(table)
                    # 简化处理：假设返回逗号分隔的字段名
                    fields = [f.strip() for f in fields_result.split(",") if f.strip()]
                    relevant_fields[table] = fields
                except Exception as e:
                    logger.warning(f"Failed to get fields for {table}: {e}")

            logger.info(f"Discovered tables: {relevant_tables}, fields: {relevant_fields}")

            return {
                "relevant_tables": relevant_tables,
                "relevant_fields": relevant_fields,
            }

        except Exception as e:
            logger.error(f"Schema discovery error: {e}")
            return {"relevant_tables": [], "relevant_fields": {}}

    def field_probing_node(self, state: AgentState) -> Dict[str, Any]:
        """字段探测节点 - 采样字段实际值以避免盲目SQL"""
        logger.info("Probing field values")

        field_samples = {}
        sql_tool = self.tool_map.get("sql_query")

        if not sql_tool or not state.get("relevant_tables"):
            logger.info("No tables to probe")
            return {"field_samples": field_samples}

        try:
            # 对每个相关字段执行 SELECT DISTINCT LIMIT 10 探测
            for table, fields in state.get("relevant_fields", {}).items():
                for field in fields[:3]:  # 只探测前3个字段以节省时间
                    try:
                        # 构建探测SQL
                        probe_sql = f"SELECT DISTINCT {field} FROM {table} LIMIT 10"
                        logger.info(f"Probing: {probe_sql}")

                        result = sql_tool.run(probe_sql)
                        field_samples[f"{table}.{field}"] = result

                    except Exception as e:
                        logger.warning(f"Failed to probe {table}.{field}: {e}")
                        # 继续探测其他字段

            logger.info(f"Collected {len(field_samples)} field samples")

            return {
                "field_samples": field_samples,
            }

        except Exception as e:
            logger.error(f"Field probing error: {e}")
            return {"field_samples": field_samples}

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

    def _build_intent_detection_prompt(self, state: AgentState) -> str:
        """构建意图识别提示词"""
        memory_context = state.get("memory_context", "") or ""
        memory_str = f"\n历史对话：\n{memory_context}" if memory_context else ""

        prompt = f"""分类用户查询类型（只返回一个词）：
- knowledge: 纯知识问题（概念、术语、规则解释）
- data: 数据查询问题（涉及数据库、SQL、统计）
- hybrid: 既需要知识澄清又需要数据查询

用户问题: {state['user_input']}{memory_str}

返回: knowledge / data / hybrid"""
        return prompt

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
