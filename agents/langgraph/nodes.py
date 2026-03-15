"""LangGraph Agent 节点函数"""

import logging
import time
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from langchain_core.language_models import BaseLLM
from langchain_core.tools import BaseTool

from agents.services.smart_memory import SmartMemoryManager

from .state import AgentState, ExecutionStep
from agents.services.observation_masking import ObservationMasker

logger = logging.getLogger(__name__)


class NodeManager:
    """管理所有Agent节点函数"""

    def __init__(self, llm: BaseLLM, tools: List[BaseTool], memory_manager: Optional[object] = None):
        self.llm: BaseLLM = llm
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}
        self.memory_manager:SmartMemoryManager = memory_manager

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

        # 先用启发式方法快速判断（性能优先）
        user_input = state['user_input']

        # 关键词定义
        data_keywords = {"查询", "统计", "SELECT", "表", "字段", "数据库", "数据", "SQL", "昨天", "上周", "销售", "金额"}
        knowledge_keywords = {"什么是", "定义", "含义", "解释", "术语", "代表"}

        # 计算关键词匹配得分
        data_score = sum(1 for kw in data_keywords if kw in user_input)
        knowledge_score = sum(1 for kw in knowledge_keywords if kw in user_input)

        # 启发式判断
        if knowledge_score > 0 and data_score == 0:
            intent_type = "knowledge"
        elif data_score > knowledge_score:
            intent_type = "data"
        elif data_score > 0 and knowledge_score > 0:
            intent_type = "hybrid"
        else:
            # 如果启发式判断不确定，用LLM
            prompt = self._build_intent_detection_prompt(state)
            try:
                response = self.llm.predict(prompt).strip().lower()
                if "knowledge" in response or "概念" in response or "定义" in response:
                    intent_type = "knowledge"
                elif "hybrid" in response or "混合" in response:
                    intent_type = "hybrid"
                else:
                    intent_type = "data"
            except Exception as e:
                logger.error(f"LLM intent detection error: {e}")
                intent_type = "data"  # 默认为数据查询

        logger.info(f"Detected intent: {intent_type} (data_score={data_score}, knowledge_score={knowledge_score})")

        return {
            "intent_type": intent_type,
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

    def terminology_clarification_node(self, state: AgentState) -> Dict[str, Any]:
        """术语澄清节点 - 使用知识库澄清中文术语和行业黑话"""
        logger.info("Clarifying terminology")

        clarified_terms = []
        doc_search_tool = self.tool_map.get("document_search")

        if not doc_search_tool:
            logger.warning("document_search tool not found")
            return {"clarified_terms": clarified_terms}

        # 提取可能需要澄清的术语（简单启发式）
        chinese_patterns = ["A厂商", "B厂商", "供应商", "客户", "订单", "产品"]
        for term in chinese_patterns:
            if term in state['user_input']:
                try:
                    logger.info(f"Searching for term: {term}")
                    result = doc_search_tool.run(term)
                    clarified_terms.append({
                        "term": term,
                        "meaning": result
                    })
                except Exception as e:
                    logger.warning(f"Failed to clarify {term}: {e}")

        logger.info(f"Clarified {len(clarified_terms)} terms")

        return {
            "clarified_terms": clarified_terms,
        }

    def main_query_node(self, state: AgentState) -> Dict[str, Any]:
        """主查询节点 - 基于所有信息生成和执行SQL"""
        logger.info("Executing main query")

        sql_tool = self.tool_map.get("sql_query")
        if not sql_tool:
            logger.warning("sql_query tool not found")
            return {
                "sql_result": None,
                "error_message": "SQL tool not available"
            }

        # 从scratchpad中期望的SQL（这里简化处理）
        # 实际应该由前面的节点收集信息后，由LLM生成SQL
        sql_query = None

        # 尝试从scratchpad中提取SQL查询
        import re
        sql_pattern = r"SELECT.*?(?:;|$)"
        matches = re.finditer(sql_pattern, state["agent_scratchpad"], re.IGNORECASE | re.DOTALL)
        for match in matches:
            potential_sql = match.group(0).strip()
            if potential_sql:
                sql_query = potential_sql
                break

        if not sql_query:
            logger.warning("No SQL query found in scratchpad")
            return {
                "sql_result": "❌ No SQL query generated",
            }

        try:
            logger.info(f"Executing SQL: {sql_query[:100]}...")
            result = sql_tool.run(sql_query)
            return {
                "sql_result": result,
            }
        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            return {
                "sql_result": f"❌ SQL execution failed: {str(e)}",
            }

    def result_explanation_node(self, state: AgentState) -> Dict[str, Any]:
        """结果解释节点 - 用自然语言解释查询结果"""
        logger.info("Explaining result")

        if not state.get("sql_result"):
            explanation = "No result to explain"
        else:
            # 构建解释提示词
            prompt = self._build_explanation_prompt(state)

            try:
                explanation = self.llm.predict(prompt)
            except Exception as e:
                logger.error(f"Explanation generation error: {e}")
                explanation = f"Result: {state.get('sql_result', '')}"

        return {
            "explanation": explanation,
            "final_answer": explanation,  # 设置最终答案
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

            # 脱敏观察结果
            masked_result = ObservationMasker.mask_observation(tool_name, result)

            return {
                "current_tool": tool_name,
                "tools_used": state["tools_used"] + [tool_name],
                "observations": state["observations"] + [result],
                "masked_observations": state["masked_observations"] + [masked_result],
                "execution_steps": state["execution_steps"] + [step],
                "agent_scratchpad": state["agent_scratchpad"] + f"Observation: {masked_result}\n",
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

        try:
            from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

            # 创建模拟的执行记录对象供evaluator使用
            class MockExecution:
                def __init__(self, state):
                    self.user_input = state.get("user_input", "")
                    self.agent_output = state.get("final_answer", "")
                    self.tools_used = state.get("tools_used", [])

            execution = MockExecution(state)

            # 构建测试用例（从user_input提取关键词）
            keywords = self._extract_keywords_from_input(state["user_input"])
            test_case = {
                "expected": {
                    "keywords": keywords,
                    "min_length": 10,
                    "max_length": 5000,
                    "should_NOT_contain": [],
                    "expected_tools": state.get("tools_used", []),
                }
            }

            # 调用RuleBasedEvaluator
            evaluator = RuleBasedEvaluator()
            eval_result = evaluator.evaluate(execution, test_case)

            # 提取评测结果
            eval_passed = eval_result.get("passed", False)
            eval_score = eval_result.get("score", 0.0)

            logger.info(f"Evaluation result: passed={eval_passed}, score={eval_score:.2f}")

            return {
                "evaluation_result": eval_result,
                "eval_passed": eval_passed,
                "eval_score": eval_score,
            }

        except ImportError:
            logger.warning("RuleBasedEvaluator not available, using default evaluation")
            # 如果evaluator不可用，使用简单的默认评测
            final_answer = state.get("final_answer", "")
            is_valid = len(final_answer) > 10 and len(final_answer) < 5000

            return {
                "evaluation_result": {"score": 0.8 if is_valid else 0.3, "passed": is_valid},
                "eval_passed": is_valid,
                "eval_score": 0.8 if is_valid else 0.3,
            }
        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            # 评测失败时设置为不通过
            return {
                "evaluation_result": {"score": 0.0, "passed": False},
                "eval_passed": False,
                "eval_score": 0.0,
            }

    @staticmethod
    def _extract_keywords_from_input(user_input: str) -> list:
        """从用户输入中提取关键词"""
        import re
        # 简单的关键词提取：长度>2的中文词或英文词
        words = re.findall(r'[\u4e00-\u9fff]{2,}|\b[a-z]{3,}\b', user_input.lower())
        return list(set(words))[:5]  # 最多5个唯一关键词

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

    def _build_explanation_prompt(self, state: AgentState) -> str:
        """构建结果解释提示词"""
        prompt = f"""基于以下信息，用自然语言解释查询结果：

用户问题: {state['user_input']}

查询结果: {state.get('sql_result', 'No result')}

时间范围: {state.get('time_range', 'N/A')}

澄清的术语: {state.get('clarified_terms', [])}

请用中文总结：
1. 查询理解 - 用户问题的核心
2. 关键数据 - 最重要的数值或统计
3. 业务解释 - 这些数据的含义

简洁回答，不超过200字："""
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
