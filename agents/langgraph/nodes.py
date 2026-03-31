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


# ============ 重试策略配置 ============

class RetryConfig:
    """重试策略配置"""

    # 基础重试次数限制
    MAX_RETRIES = 3  # 改自2，允许更多重试机会

    # 不同错误类型的重试延迟（秒）
    # 用于在重试之前等待，避免频繁重复相同的错误
    RETRY_DELAYS = {
        "syntax_error": 0.0,        # SQL语法错误：无需延迟（通常是逻辑问题）
        "field_not_exists": 0.0,    # 字段不存在：无需延迟（schema已变）
        "no_results": 0.5,          # 无结果：稍微延迟后重试（可能是临时问题）
        "invalid_answer": 0.0,      # 答案无效：无需延迟
        "evaluation_failed": 1.0,   # 评测失败：延迟后重试（可能需要重新思考）
        "timeout": 2.0,             # 超时：延迟较长（但不会重试，因为是permanent_error）
        "permission_error": 0.0,    # 权限错误：不会重试
    }

    @staticmethod
    def get_retry_delay(error_diagnosis: str) -> float:
        """获取错误类型对应的重试延迟时间（秒）"""
        return RetryConfig.RETRY_DELAYS.get(error_diagnosis, 0.5)

    @staticmethod
    def should_retry(retry_count: int, error_category: str) -> bool:
        """判断是否应该重试"""
        # permanent_error不重试
        if error_category == "permanent_error":
            return False

        # retryable_logic_error和temporary_error可以重试
        return retry_count < RetryConfig.MAX_RETRIES


class NodeManager:
    """管理所有Agent节点函数"""

    def __init__(self, llm: BaseLLM, tools: List[BaseTool], memory_manager: Optional[object] = None):
        self.llm: BaseLLM = llm
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}
        self.memory_manager:SmartMemoryManager = memory_manager

        # ✅ Phase 5: bind_tools - LLM now knows about tools and outputs structured tool_calls
        self.model_with_tools = llm.bind_tools(tools)
        logger.info(f"✓ Bound {len(tools)} tools to LLM - using LangGraph ToolNode pattern")

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
        }

    def agent_loop_node(self, state: AgentState) -> Dict[str, Any]:
        """✅ Agent推理 - 使用model_with_tools输出structured tool_calls"""
        logger.info(f"Agent loop (using model_with_tools)")

        # 构建提示
        system_prompt = self._build_system_prompt(state)

        # 构建消息列表（使用BaseMessage格式，兼容LangGraph）
        from langchain_core.messages import HumanMessage
        messages = [
            HumanMessage(content=system_prompt),
        ] + state.get("messages", [])

        # ✅ 关键改动：使用model_with_tools替代llm.predict()
        # model_with_tools输出AIMessage with tool_calls（不是文本）
        try:
            response = self.model_with_tools.invoke(messages)
            logger.info(f"LLM response: {len(response.content) if response.content else 0} chars, "
                       f"tool_calls={len(response.tool_calls) if hasattr(response, 'tool_calls') and response.tool_calls else 0}")
        except Exception as e:
            logger.error(f"LLM prediction error: {e}")
            from langchain_core.messages import AIMessage
            response = AIMessage(content=f"I encountered an error: {str(e)}")

        # 记录执行步骤
        step = ExecutionStep(
            step_type="model_call",
            tool_name=None,
            tool_input=None,
            tool_output=response.content,
            timestamp=datetime.now(),
            duration=0.0
        )

        # ✅ 返回值：添加messages而非更新scratchpad
        # ToolNode会自动处理tool_calls
        return {
            "messages": state.get("messages", []) + [response],
            "execution_steps": state["execution_steps"] + [step],
        }

    def _build_system_prompt(self, state: AgentState) -> str:
        """构建系统提示 - LLM已知道可用工具（通过bind_tools）"""
        intent = state.get("intent_type", "unknown")

        if intent == "knowledge":
            clarified = state.get("clarified_terms", [])
            return f"""You are a knowledge assistant.

User question: {state['user_input']}
Clarified terms: {clarified}

Use the available tools to find relevant knowledge."""

        elif intent == "data":
            tables = state.get("relevant_tables", [])
            time_range = state.get("time_range")
            return f"""You are a data analysis assistant.

User question: {state['user_input']}
Available tables: {tables}
Time range: {time_range}

Use the available tools to query data and generate results."""

        else:
            return f"""You are a helpful assistant.
User question: {state['user_input']}

Use the available tools if needed to help answer the question."""

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
            # 如果启发式判断不确定，用LLM + 历史记忆
            logger.info("Heuristic detection uncertain, using LLM with memory context")
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

            relevant_tables = []
            relevant_fields = {}

            # 解析表名结果（格式：可用的表:\n- table1\n- table2）
            all_tables = []
            if tables_result:
                # 提取 "- " 开头的行
                for line in tables_result.split('\n'):
                    line = line.strip()
                    if line.startswith('- '):
                        table_name = line[2:].strip()
                        if table_name:
                            all_tables.append(table_name)

            logger.info(f"Available tables from schema_query: {all_tables}")

            # 从输入和澄清的术语中匹配相关表
            clarified_terms = state.get('clarified_terms', [])
            keywords = state['user_input'].lower()
            for term_info in clarified_terms:
                keywords += " " + term_info.get('term', '').lower()

            for table in all_tables:
                if table.lower() in keywords:
                    relevant_tables.append(table)

            # 对于每个相关的表，获取其字段信息
            for table in relevant_tables:
                try:
                    fields_result = schema_tool.run(table)
                    # 解析字段结果（格式：表 'table' 的字段信息:\n- col1: type1 (NULL)\n- col2: type2 (NOT NULL)）
                    fields = []
                    for line in fields_result.split('\n'):
                        line = line.strip()
                        if line.startswith('- '):
                            # 提取字段名（在 ':' 前）
                            field_part = line[2:].split(':')[0].strip()
                            if field_part:
                                fields.append(field_part)
                    relevant_fields[table] = fields
                    logger.info(f"Got {len(fields)} fields from table '{table}': {fields}")
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
        """字段探测节点 - 采样字段值，参考历史访问偏好"""
        logger.info("Probing field values with memory context")

        field_samples = {}
        sql_tool = self.tool_map.get("sql_query")

        if not sql_tool or not state.get("relevant_tables"):
            logger.info("No tables to probe")
            return {"field_samples": field_samples}

        try:
            # 获取历史记忆，用于字段优先级排序
            memory_context = state.get("memory_context", "") or ""
            memory_hint = f"用户历史倾向：{memory_context[:200]}" if memory_context else "首次查询"

            logger.info(f"Field probing hint from memory: {memory_hint}")

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
        """术语澄清节点 - 使用RAG + 历史记忆理解用户术语（并发查询）"""
        logger.info("Clarifying terminology with memory context")

        clarified_terms = []
        doc_search_tool = self.tool_map.get("document_search")

        if not doc_search_tool:
            logger.warning("document_search tool not found")
            return {"clarified_terms": clarified_terms}

        # 使用历史记忆增强术语提取
        memory_context = state.get("memory_context", "") or ""
        memory_hint = f"\n\n【用户的历史术语使用】\n{memory_context}" if memory_context else ""

        # 用LLM从用户输入中提取可能需要澄清的关键术语
        extract_prompt = f"""从用户问题中提取所有可能需要澄清的关键术语和业务概念。
这些术语可能是：
- 中文业务术语（如"销售额"、"毛利率"）
- 代码或缩写（如"A厂商"、"SKU"）
- 状态值（如"已完成"、"待审核"）

用户问题: {state['user_input']}{memory_hint}

只返回一个逗号分隔的术语列表，不要解释。如果没有需要澄清的术语，返回空。"""

        try:
            # 调用LLM提取术语
            response = self.llm.predict(extract_prompt).strip()
            if not response:
                logger.info("No terms need clarification")
                return {"clarified_terms": clarified_terms}

            # 解析返回的术语列表
            terms = [t.strip() for t in response.split(',') if t.strip()]
            logger.info(f"Extracted terms for clarification: {terms}")

            # 根据意图类型选择文档分类过滤
            intent_type = state.get("intent_type", "data")
            if intent_type == "knowledge":
                # 知识路径：只查询公开文档
                doc_category = "user"
                logger.info("Using 'user' doc_category for knowledge path")
            else:
                # 数据路径/混合路径：查询内部文档（表结构、字段说明等）
                doc_category = "internal"
                logger.info("Using 'internal' doc_category for data/hybrid path")

            # 并发查询术语（最多5个）
            import concurrent.futures

            def search_term(term):
                """为单个术语查询知识库"""
                try:
                    logger.info(f"Searching knowledge base for term: {term} (category={doc_category})")
                    result = doc_search_tool.run(term, doc_category=doc_category)
                    if result:
                        logger.info(f"Found clarification for '{term}'")
                        return {"term": term, "meaning": result}
                    else:
                        logger.info(f"No RAG result for '{term}'")
                        return None
                except Exception as e:
                    logger.warning(f"Failed to clarify '{term}': {e}")
                    return None

            # 使用线程池并发查询
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(search_term, term) for term in terms[:5]]
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        clarified_terms.append(result)

        except Exception as e:
            logger.error(f"Terminology clarification error: {e}")

        logger.info(f"Clarified {len(clarified_terms)} terms (concurrent)")

        return {
            "clarified_terms": clarified_terms,
        }

    def main_query_node(self, state: AgentState) -> Dict[str, Any]:
        """主查询节点 - 基于所有信息用LLM生成和执行SQL"""
        logger.info(f"Executing main query (retry_count={state.get('retry_count', 0)})")

        sql_tool = self.tool_map.get("sql_query")
        if not sql_tool:
            logger.warning("sql_query tool not found")
            return {
                "sql_result": None,
                "error_message": "SQL tool not available"
            }

        # 构建包含所有上下文的SQL生成提示
        schema_info = "\n".join([
            f"表 '{table}': 字段 {fields}"
            for table, fields in state.get("relevant_fields", {}).items()
        ])

        field_samples_info = "\n".join([
            f"- {field}: {samples}"
            for field, samples in state.get("field_samples", {}).items()
        ])

        clarified_terms_info = "\n".join([
            f"- {term_dict['term']}: {term_dict['meaning']}"
            for term_dict in state.get("clarified_terms", [])
        ])

        # 从历史记忆中提取SQL示例
        memory_context = state.get("memory_context", "") or ""
        memory_hint = f"\n\n【用户历史查询风格】\n{memory_context[:300]}" if memory_context else ""

        # 如果是重试，包含之前的错误信息
        retry_hint = ""
        if state.get("retry_count", 0) > 0 and state.get("error_message"):
            retry_hint = f"\n\n【之前的错误】\n{state['error_message'][:200]}\n请生成不同的SQL来避免这个错误。"

        sql_generation_prompt = f"""基于以下信息生成准确的SQL查询：

用户需求: {state['user_input']}

【澄清的术语】(来自知识库/RAG的定义和映射)
{clarified_terms_info if clarified_terms_info else "无"}

【表结构】
{schema_info if schema_info else "无相关表"}

【字段采样值】(这些是实际存在的数据)
{field_samples_info if field_samples_info else "无采样值"}

【时间范围】
{state.get('time_range', '无时间限制')}{memory_hint}{retry_hint}

SQL生成要求：
✓ 明确指定SELECT的字段，禁止SELECT *
✓ 字符串值必须加引号，时间值用YYYY-MM-DD HH:MM:SS格式
✓ 根据澄清术语中的代号、泛化语义正确指定值
✓ 根据采样值确认值格式（包括后缀、大小写、符号等）
✓ 优先使用澄清术语中确定的字段名和值映射
✓ 字段值必须从采样值或澄清术语中选择，不要造出数据库中不存在的值
✓ 只返回SQL语句，不要其他内容

生成的SQL:"""

        try:
            # 调用LLM生成SQL
            logger.info("Generating SQL with LLM")
            sql_query = self.llm.predict(sql_generation_prompt).strip()

            if not sql_query:
                logger.warning("LLM generated empty SQL")
                return {
                    "sql_result": "❌ LLM未生成SQL",
                    "error_message": "LLM generation failed"
                }

            logger.info(f"Generated SQL: {sql_query[:100]}...")

            # 执行SQL
            logger.info(f"Executing SQL: {sql_query[:100]}...")
            result = sql_tool.run(sql_query)

            return {
                "sql_result": result,
            }
        except Exception as e:
            logger.error(f"SQL generation or execution error: {e}")
            return {
                "sql_result": f"❌ SQL执行失败: {str(e)}",
                "error_message": str(e)
            }

    def result_explanation_node(self, state: AgentState) -> Dict[str, Any]:
        """结果解释节点 - 支持知识路径和数据路径的两种解释模式"""
        logger.info(f"Explaining result (intent={state.get('intent_type')})")

        intent_type = state.get('intent_type', 'data')

        # 知识路径：使用clarified_terms生成知识解释
        if intent_type == "knowledge" or not state.get("sql_result"):
            if state.get("clarified_terms"):
                prompt = self._build_knowledge_explanation_prompt(state)
                logger.info("Using knowledge explanation mode")
            else:
                return {
                    "explanation": "No clarified terms found",
                    "final_answer": "Unable to provide explanation",
                }
        # 数据路径：使用sql_result生成数据解释
        else:
            if state.get("sql_result"):
                prompt = self._build_explanation_prompt(state)
                logger.info("Using data explanation mode")
            else:
                return {
                    "explanation": "No query result found",
                    "final_answer": "Unable to provide explanation",
                }

        try:
            explanation = self.llm.predict(prompt)
        except Exception as e:
            logger.error(f"Explanation generation error: {e}")
            if state.get("sql_result"):
                explanation = f"Result: {state.get('sql_result', '')}"
            elif state.get("clarified_terms"):
                explanation = str(state.get('clarified_terms', []))
            else:
                explanation = "Failed to generate explanation"

        return {
            "explanation": explanation,
            "final_answer": explanation,  # 设置最终答案
        }


    def evaluate_node(self, state: AgentState) -> Dict[str, Any]:
        """评测执行结果 - 按路径类型分别评测，返回诊断信息供重试决策使用"""
        logger.info("Evaluating execution result")

        try:
            from agents.evaluation.rule_based_evaluator import RuleBasedEvaluator

            # 直接使用state作为execution对象（不需要Mock）
            # state中已包含所有必要的字段
            class StateExecution:
                """适配器：将AgentState转换为RuleBasedEvaluator期望的接口"""
                def __init__(self, state):
                    self.user_input = state.get("user_input", "")
                    self.agent_output = state.get("final_answer", "")
                    self.tools_used = state.get("tools_used", [])

            execution = StateExecution(state)

            # 构建测试用例（从user_input提取关键词）
            keywords = self._extract_keywords_from_input(state["user_input"])
            intent_type = state.get("intent_type", "data")

            # ========== 改进：按路径类型分开评测标准 ==========
            # 知识路径 vs 数据路径的通过标准和权重完全不同
            if intent_type == "knowledge":
                # 知识路径：只需查到相关文档，答案可以简洁
                test_case = {
                    "expected": {
                        "keywords": keywords,
                        "min_length": 5,
                        "max_length": 2000,
                        "should_NOT_contain": [],
                        "expected_tools": [],
                    }
                }
                # 知识路径用较低的通过阈值：65%（因为相关度就够了）
                pass_threshold = 0.65
            else:
                # 数据路径（data/hybrid）：需要准确的SQL查询结果
                test_case = {
                    "expected": {
                        "keywords": keywords,
                        "min_length": 10,
                        "max_length": 5000,
                        "should_NOT_contain": [],
                        "expected_tools": state.get("tools_used", []),
                    }
                }
                # 数据路径用标准阈值：75%（因为需要准确性）
                pass_threshold = 0.75

            # 调用RuleBasedEvaluator
            evaluator = RuleBasedEvaluator()
            eval_result = evaluator.evaluate(execution, test_case)

            # 提取评测结果
            eval_score = eval_result.get("score", 0.0)

            # ========== 改进：不再用eval_passed，而是用诊断信息和分数双重判断 ==========
            # eval_passed只表示规则通过，重试决策由_route_on_evaluation负责

            logger.info(f"Evaluation: score={eval_score:.2f}, threshold={pass_threshold}, intent_type={intent_type}")

            # ========== 错误诊断逻辑 ==========
            # 根据分数和诊断信息来判断是否需要诊断
            error_diagnosis = None
            error_category = None  # "retryable_logic_error" / "permanent_error" / "temporary_error"
            error_message = state.get("error_message", "")
            sql_result = state.get("sql_result")
            final_answer = state.get("final_answer", "")

            # 只在分数不够时才进行错误诊断
            if eval_score < pass_threshold:
                # 根据不同的失败症状诊断错误类型
                if error_message:
                    if any(keyword in error_message for keyword in ["语法", "syntax", "SQL", "错误的列"]):
                        error_diagnosis = "syntax_error"
                        error_category = "retryable_logic_error"
                        logger.info("Diagnosed: syntax_error (retryable)")
                    elif any(keyword in error_message for keyword in ["字段", "column", "not exist"]):
                        error_diagnosis = "field_not_exists"
                        error_category = "retryable_logic_error"
                        logger.info("Diagnosed: field_not_exists (retryable)")
                    elif any(keyword in error_message for keyword in ["超时", "timeout", "Time out"]):
                        error_diagnosis = "timeout"
                        error_category = "permanent_error"  # 工具层已重试，不需在node层再重试
                        logger.info("Diagnosed: timeout (permanent - already retried at tool layer)")
                    elif any(keyword in error_message for keyword in ["权限", "permission", "denied", "access"]):
                        error_diagnosis = "permission_error"
                        error_category = "permanent_error"
                        logger.info("Diagnosed: permission_error (permanent)")
                    else:
                        error_diagnosis = "unknown_error"
                        error_category = "permanent_error"
                elif not sql_result or (isinstance(sql_result, str) and not sql_result.strip()):
                    # SQL执行但无结果
                    error_diagnosis = "no_results"
                    error_category = "retryable_logic_error"
                    logger.info("Diagnosed: no_results (retryable)")
                elif not final_answer or len(final_answer.strip()) < 10:
                    # 最终答案太短或为空
                    error_diagnosis = "invalid_answer"
                    error_category = "retryable_logic_error"
                    logger.info("Diagnosed: invalid_answer (retryable)")
                else:
                    error_diagnosis = "evaluation_failed"
                    error_category = "retryable_logic_error"
                    logger.info("Diagnosed: evaluation_failed (retryable)")

            return {
                "evaluation_result": eval_result,
                "eval_score": eval_score,
                "error_diagnosis": error_diagnosis,
                "error_category": error_category,
            }

        except ImportError:
            logger.warning("RuleBasedEvaluator not available, using default evaluation")
            # 如果evaluator不可用，使用简单的默认评测
            final_answer = state.get("final_answer", "")
            is_valid = len(final_answer) > 10 and len(final_answer) < 5000

            return {
                "evaluation_result": {"score": 0.8 if is_valid else 0.3, "passed": is_valid},
                "eval_score": 0.8 if is_valid else 0.3,
                "error_diagnosis": None,
                "error_category": None,
            }
        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            # 评测失败时返回低分
            return {
                "evaluation_result": {"score": 0.0, "passed": False},
                "eval_score": 0.0,
                "error_diagnosis": "evaluation_exception",
                "error_category": "permanent_error",
            }

    @staticmethod
    def _extract_keywords_from_input(user_input: str) -> list:
        """从用户输入中提取关键词"""
        import re
        # 简单的关键词提取：长度>2的中文词或英文词
        words = re.findall(r'[\u4e00-\u9fff]{2,}|\b[a-z]{3,}\b', user_input.lower())
        return list(set(words))[:5]  # 最多5个唯一关键词

    def error_recovery_node(self, state: AgentState) -> Dict[str, Any]:
        """错误恢复节点 - 基于错误诊断决定重试策略和延迟"""
        logger.info("Error recovery in progress")

        retry_count = state.get("retry_count", 0)
        error_diagnosis = state.get("error_diagnosis")
        error_message = state.get("error_message", "")
        intent_type = state.get("intent_type")
        error_category = state.get("error_category")

        logger.info(f"Recovery: attempt {retry_count + 1}, diagnosis={error_diagnosis}, intent={intent_type}, error: {(error_message or '')[:50]}")

        # 最多重试MAX_RETRIES次
        if retry_count >= RetryConfig.MAX_RETRIES:
            logger.warning(f"Max retry attempts ({RetryConfig.MAX_RETRIES}) reached, giving up")
            return {
                "retry_count": retry_count + 1,
                "retry_strategy": "give_up",
            }

        # 根据错误诊断添加重试延迟（在进入重试前等待一段时间）
        retry_delay = RetryConfig.get_retry_delay(error_diagnosis)
        if retry_delay > 0:
            logger.info(f"Waiting {retry_delay}s before retry to avoid repeated failures")
            time.sleep(retry_delay)

        # 根据路径类型和诊断决定重试策略
        strategy = "give_up"  # 默认放弃

        # 知识路径的重试策略
        if intent_type == "knowledge":
            if error_diagnosis == "invalid_answer":
                # 答案无效：重新查询知识库
                strategy = "requery_knowledge"
                logger.info("Strategy: requery knowledge due to invalid answer")
            elif error_diagnosis == "evaluation_failed":
                # 评测失败：重新查询知识库
                strategy = "requery_knowledge"
                logger.info("Strategy: requery knowledge due to evaluation failure")
            elif error_diagnosis == "timeout":
                # 超时：不重试
                strategy = "give_up"
                logger.info("Strategy: give up due to timeout")
            else:
                # 其他错误类型也尝试重新查询
                strategy = "requery_knowledge"
                logger.info(f"Strategy: requery knowledge (default for diagnosis={error_diagnosis})")

        # 数据路径的重试策略
        elif intent_type in ("data", "hybrid"):
            if error_diagnosis == "syntax_error":
                # SQL语法错误：重新生成SQL
                strategy = "regenerate_sql"
                logger.info("Strategy: regenerate SQL due to syntax error")
            elif error_diagnosis == "no_results":
                # 查询无结果：可能字段值采样不准，重新探测
                strategy = "reprobe_fields"
                logger.info("Strategy: reprobe fields due to no results")
            elif error_diagnosis == "field_not_exists":
                # 字段不存在：重新发现schema
                strategy = "rediscover_schema"
                logger.info("Strategy: rediscover schema due to field not exists")
            elif error_diagnosis == "timeout":
                # 超时：放弃重试
                strategy = "give_up"
                logger.info("Strategy: give up due to timeout")
            elif error_diagnosis == "invalid_answer":
                # 最终答案无效：重新生成SQL
                strategy = "regenerate_sql"
                logger.info("Strategy: regenerate SQL due to invalid answer")
            else:
                # 其他诊断：默认尝试重新生成SQL
                strategy = "regenerate_sql"
                logger.info(f"Strategy: regenerate SQL (default for diagnosis={error_diagnosis})")
        else:
            # 意图类型未知：放弃重试
            logger.warning(f"Unknown intent_type: {intent_type}, giving up")
            strategy = "give_up"

        return {
            "retry_count": retry_count + 1,
            "retry_strategy": strategy,
            "error_diagnosis": error_diagnosis,  # 保留诊断信息
        }

    def final_answer_node(self, state: AgentState) -> Dict[str, Any]:
        """生成最终答案，并将会话保存到数据库"""
        logger.info("Generating final answer and saving to memory database")

        # 获取最终答案：从explanation或sql_result
        final_answer = state.get("explanation") or state.get("sql_result") or "No answer generated"

        # 计算总时长
        end_time = datetime.now()
        duration = (end_time - state["start_time"]).total_seconds() if state["start_time"] else 0.0

        # 将本轮对话添加到记忆系统并保存到数据库
        if self.memory_manager:
            try:
                # 添加用户查询
                self.memory_manager.add_message(
                    content=state['user_input'],
                    message_type="human",
                    timestamp=state.get("start_time")
                )
                # 添加AI回答
                self.memory_manager.add_message(
                    content=final_answer,
                    message_type="ai",
                    timestamp=end_time
                )
                # 保存到数据库
                self.memory_manager.save_to_db()
                logger.info("✓ Saved conversation to memory database")
            except Exception as e:
                logger.warning(f"Failed to save to memory database: {e}")

        return {
            "final_answer": final_answer,
            "end_time": end_time,
            "total_duration": duration,
        }

    def error_handler_node(self, state: AgentState) -> Dict[str, Any]:
        """错误处理，记录失败的对话到数据库"""
        logger.error(f"Error in execution: {state.get('error_message')}")

        error_message = f"Error: {state.get('error_message', 'Unknown error')}"

        # 即使出错也记录到数据库（便于后续诊断）
        if self.memory_manager:
            try:
                self.memory_manager.add_message(
                    content=state['user_input'],
                    message_type="human",
                    timestamp=state.get("start_time")
                )
                self.memory_manager.add_message(
                    content=error_message,
                    message_type="ai",
                    timestamp=datetime.now()
                )
                self.memory_manager.save_to_db()
                logger.info("✓ Logged error conversation to memory database")
            except Exception as e:
                logger.warning(f"Failed to log error to memory database: {e}")

        return {
            "final_answer": error_message,
            "error_message": state.get("error_message"),
        }

    # ============ 辅助方法 ============

    def _build_intent_detection_prompt(self, state: AgentState) -> str:
        """构建意图识别提示词 - 使用历史记忆帮助ambiguous查询"""
        memory_context = state.get("memory_context", "") or ""
        memory_str = f"\n\n【历史相似查询】\n{memory_context}" if memory_context else ""

        prompt = f"""根据用户查询和历史对话，分类查询类型（只返回一个词）：

- knowledge: 纯知识问题（概念、术语、规则解释）
- data: 数据查询问题（涉及数据库、SQL、统计）
- hybrid: 既需要知识澄清又需要数据查询{memory_str}

当前问题: {state['user_input']}

返回: knowledge / data / hybrid"""
        return prompt

    def _build_explanation_prompt(self, state: AgentState) -> str:
        """构建结果解释提示词 - 参考历史风格"""
        memory_context = state.get("memory_context", "") or ""
        memory_hint = f"\n\n【用户历史回复风格】\n{memory_context[:250]}" if memory_context else ""

        prompt = f"""基于以下信息，用自然语言解释查询结果：

用户问题: {state['user_input']}

查询结果: {state.get('sql_result', 'No result')}

时间范围: {state.get('time_range', 'N/A')}

澄清的术语: {state.get('clarified_terms', [])}{memory_hint}

请用中文总结：
1. 查询理解 - 用户问题的核心
2. 关键数据 - 最重要的数值或统计
3. 业务解释 - 这些数据的含义

简洁回答，不超过200字："""
        return prompt

    def _build_knowledge_explanation_prompt(self, state: AgentState) -> str:
        """构建知识解释提示词 - 知识路径使用，参考历史风格"""
        clarified_terms_str = "\n".join([
            f"- {term['term']}: {term['meaning']}"
            for term in state.get('clarified_terms', [])
        ])

        memory_context = state.get("memory_context", "") or ""
        memory_hint = f"\n\n【用户历史回复偏好】\n{memory_context[:250]}" if memory_context else ""

        prompt = f"""基于以下澄清的术语和定义，用自然语言回答用户问题：

用户问题: {state['user_input']}

【已澄清的术语定义】
{clarified_terms_str or "无额外定义"}{memory_hint}

请用中文回答，包括：
1. 问题理解 - 澄清用户问题涉及的核心概念
2. 术语解释 - 相关术语的定义和含义
3. 综合答案 - 基于澄清结果的完整回答

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

