"""LangGraph Agent 图构建

多路径路由架构：

                    ┌──────────────────────┐
                    │  input_processing    │
                    │  (提取memory context) │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │ intent_detection     │
                    │ (LLM分类query意图)    │
                    └──────────┬───────────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
            ▼                  ▼                  ▼
     ┌──────────────┐ ┌──────────────┐ ┌──────────┐ ┌──────────┐
     │  knowledge   │ │     data     │ │  hybrid  │ │ chitchat │
     │    path      │ │    path      │ │   path   │ │   path   │
     └──────┬───────┘ └──────┬───────┘ └────┬─────┘ └────┬─────┘
            │                │              │             │
terminology │                │              │         chitchat_node
clarification   time_check───┼──────────────┤             │
            │                │              │             │
            │         schema_discovery     │             │
            │                │              │             │
            │          field_probing        │             │
            │                │              │             │
            │            main_query         │             │
            │                │              │             │
            └────────┬───────┴──────┬───────┘             │
                     │              │                     │
          result_explanation ◄──────┘                     │
                     │                                    │
                evaluate                                  │
                     │                                    │
     ┌───────────────┼───────────────┐                    │
     ▼               ▼               ▼                    │
final_answer    final_answer    error_handler ◄───────────┘
     │               │               │
     └───────────────┼───────────────┘
                     │
                    END
"""

from langgraph.graph import StateGraph, END
from typing import List, Optional
from langchain_core.language_models import BaseLLM
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode, tools_condition  # ✅ Phase 5: Import ToolNode
from .state import AgentState
from .nodes import NodeManager, RetryConfig
import logging

logger = logging.getLogger(__name__)


class AgentGraphBuilder:
    """构建LangGraph Agent图"""

    def __init__(self, llm: BaseLLM, tools: List[BaseTool], memory_manager: Optional[object] = None):
        self.llm = llm
        self.tools = tools
        self.memory_manager = memory_manager
        self.node_manager = NodeManager(llm, tools, memory_manager)

    def build(self) -> object:
        """构建并返回编译后的图 - ✅ Phase 5: 使用LangGraph ToolNode"""

        # 创建StateGraph
        graph = StateGraph(AgentState)

        # 添加节点
        graph.add_node("input_processing", self.node_manager.process_input_node)
        graph.add_node("intent_detection", self.node_manager.intent_detection_node)
        graph.add_node("agent_loop", self.node_manager.agent_loop_node)
        graph.add_node("time_check", self.node_manager.time_check_node)
        graph.add_node("schema_discovery", self.node_manager.schema_discovery_node)
        graph.add_node("field_probing", self.node_manager.field_probing_node)
        graph.add_node("terminology_clarification", self.node_manager.terminology_clarification_node)
        graph.add_node("main_query", self.node_manager.main_query_node)
        graph.add_node("result_explanation", self.node_manager.result_explanation_node)
        # ✅ Phase 5: Replace tool_execution_node with LangGraph ToolNode
        graph.add_node("tools", ToolNode(self.tools))
        graph.add_node("evaluate", self.node_manager.evaluate_node)
        graph.add_node("final_answer", self.node_manager.final_answer_node)
        graph.add_node("error_handler", self.node_manager.error_handler_node)
        graph.add_node("chitchat", self.node_manager.chitchat_node)

        # 定义边
        graph.add_edge("input_processing", "intent_detection")

        # 所有路径都先走术语澄清（避免理解错误）
        graph.add_edge("intent_detection", "terminology_clarification")

        # 术语澄清后的条件路由 - 根据意图类型决定是否继续查询
        # Option A: 知识路径直接进行术语澄清→解释（不需要redundant search）
        # 数据路径继续进行SQL查询
        graph.add_conditional_edges(
            "terminology_clarification",
            self._route_after_clarification,
            {
                "knowledge": "result_explanation",     # 知识问题：术语澄清后直接解释结果
                "data": "time_check",                   # 数据问题：术语澄清后继续查询数据
                "hybrid": "time_check",                 # 混合问题：先澄清术语再查询数据
                "chitchat": "chitchat",                 # 闲聊：友好回复并引导回业务
            }
        )

        # 数据路径
        graph.add_edge("time_check", "schema_discovery")
        graph.add_edge("schema_discovery", "field_probing")
        graph.add_edge("field_probing", "main_query")
        graph.add_edge("main_query", "result_explanation")

        # 所有查询路径都进入结果解释和评测
        graph.add_edge("result_explanation", "evaluate")

        # 闲聊路径直接到最终答案（不需要评测）
        graph.add_edge("chitchat", "final_answer")

        # ✅ Phase 5: 新的条件路由 - 使用tools_condition检查tool_calls
        graph.add_conditional_edges(
            "agent_loop",
            tools_condition,  # 自动检查是否有tool_calls
            {
                "tools": "tools",        # 有tool_calls → 执行工具
                "__end__": "evaluate"    # 无tool_calls → 评测结果
            }
        )

        # ✅ Phase 5: 工具执行后回到agent继续推理
        graph.add_edge("tools", "agent_loop")

        # 评测后的条件边
        graph.add_conditional_edges(
            "evaluate",
            self._route_on_evaluation,
            {
                "passed": "final_answer",
                "retry": "error_recovery",
                "failed": "error_handler"
            }
        )

        # 错误恢复节点 - 基于错误诊断决定重试策略
        graph.add_node("error_recovery", self.node_manager.error_recovery_node)
        graph.add_conditional_edges(
            "error_recovery",
            self._route_on_error_recovery,
            {
                "regenerate_sql": "main_query",           # 数据路径：重新生成SQL
                "reprobe_fields": "field_probing",        # 数据路径：重新探测字段+生成SQL
                "rediscover_schema": "schema_discovery",  # 数据路径：重新发现schema+重新生成SQL
                "requery_knowledge": "terminology_clarification", # 知识路径：重新查询知识库
                "give_up": "error_handler"                # 放弃，进入错误处理
            }
        )

        # 最终答案和错误都指向END
        graph.add_edge("final_answer", END)
        graph.add_edge("error_handler", END)

        # 设置入口点
        graph.set_entry_point("input_processing")

        # 编译图（checkpointer目前仅支持MemorySaver）
        try:
            from langgraph.checkpoint.memory import MemorySaver
            checkpointer = MemorySaver()
            compiled_graph = graph.compile(checkpointer=checkpointer)
        except Exception as e:
            logger.warning(f"Checkpointer setup failed: {e}, compiling without checkpointer")
            compiled_graph = graph.compile()

        return compiled_graph

    # ============ 路由函数 ============

    def _route_after_clarification(self, state: AgentState) -> str:
        """术语澄清后的路由 - 决定是否继续查询数据"""
        intent = state.get("intent_type", "data")
        logger.info(f"Routing after clarification: {intent}")

        if intent == "knowledge":
            return "knowledge"
        elif intent == "chitchat":
            return "chitchat"
        else:
            # 数据问题或混合问题：继续查询数据
            return "data"

    def _route_by_intent(self, state: AgentState) -> str:
        """根据意图类型路由到不同的处理路径"""
        intent = state.get("intent_type", "data")
        logger.info(f"Routing by intent: {intent}")

        if intent == "knowledge":
            return "knowledge"
        elif intent == "hybrid":
            return "hybrid"
        else:  # data or default
            return "data"

    def _should_continue_loop(self, state: AgentState) -> str:
        """判断是否继续Agent循环"""

        # 检查是否达到最大迭代次数
        if state["iteration"] >= state["max_iterations"]:
            return "finish"

        # 检查scratchpad中是否有Final Answer
        if "Final Answer:" in state["agent_scratchpad"]:
            return "finish"

        # 继续循环
        return "continue"

    def _handle_tool_execution(self, state: AgentState) -> str:
        """处理工具执行结果"""

        # 如果有错误消息且重试次数过多，放弃
        if state["error_message"] and state["retry_count"] > 2:
            return "error"

        # 如果有错误但还能重试，重新进行推理
        if state["error_message"]:
            return "loop"

        # 成功执行工具，继续Agent循环
        return "loop"

    def _route_on_evaluation(self, state: AgentState) -> str:
        """根据评测结果路由 - 改进的重试决策逻辑

        核心改进：
        - 不再基于单一的eval_passed
        - 而是综合考虑：分数 + 诊断信息 + 意图类型
        - 目标：避免无效重试，节省token
        """

        # 提取信息
        eval_score = state.get("eval_score", 0.0)
        error_category = state.get("error_category")
        error_diagnosis = state.get("error_diagnosis")
        intent_type = state.get("intent_type", "data")
        retry_count = state.get("retry_count", 0)

        # ========== 规则1：永久性错误不重试 ==========
        if error_category == "permanent_error":
            logger.warning(f"Non-retryable error: {error_diagnosis}, giving up")
            return "failed"

        # ========== 规则2：按路径类型的通过阈值 ==========
        # 知识路径要求较低（65%），数据路径要求较高（75%）
        if intent_type == "knowledge":
            pass_threshold = 0.65
        else:
            pass_threshold = 0.75

        # ========== 规则3：分数足够好就接受（不必完美） ==========
        if eval_score >= pass_threshold:
            logger.info(f"Score {eval_score:.2f} >= threshold {pass_threshold}, accepting answer")
            return "passed"

        # ========== 规则4：分数太低但还有重试机会 ==========
        if retry_count < RetryConfig.MAX_RETRIES:
            logger.info(f"Score {eval_score:.2f} < threshold {pass_threshold}, retrying {retry_count + 1}/{RetryConfig.MAX_RETRIES}")
            return "retry"

        # ========== 规则5：重试次数用尽 ==========
        logger.warning(f"Max retries ({RetryConfig.MAX_RETRIES}) reached, score {eval_score:.2f}, giving up")
        return "failed"

    def _route_on_error_recovery(self, state: AgentState) -> str:
        """错误恢复路由 - 基于诊断的重试策略"""
        retry_strategy = state.get("retry_strategy", "give_up")
        error_diagnosis = state.get("error_diagnosis")

        logger.info(f"Error recovery routing: strategy={retry_strategy}, diagnosis={error_diagnosis}")

        # 直接使用error_recovery_node返回的策略
        return retry_strategy


def create_agent_graph(
    llm: BaseLLM,
    tools: List[BaseTool],
    memory_manager: Optional[object] = None
) -> object:
    """便利函数：创建Agent图"""

    builder = AgentGraphBuilder(llm, tools, memory_manager)
    return builder.build()
