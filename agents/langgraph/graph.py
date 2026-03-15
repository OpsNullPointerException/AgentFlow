"""LangGraph Agent 图构建

多路径路由架构：

                    ┌──────────────────────┐
                    │  input_processing    │
                    │  (提取memory context) │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │ intent_detection     │
                    │ (分类query意图)      │
                    └──────────┬───────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
                ▼              ▼              ▼
         ┌──────────────┐ ┌──────────────┐ ┌──────────┐
         │  knowledge   │ │     data     │ │  hybrid  │
         │    path      │ │    path      │ │   path   │
         └──────┬───────┘ └──────┬───────┘ └────┬─────┘
                │                │              │
    terminology │                │              │
    clarification   time_check───┼──────────────┤
                │                │              │
                │         schema_discovery     │
                │                │              │
                │          field_probing        │
                │                │              │
                │            main_query         │
                │                │              │
                └────────┬───────┴──────┬───────┘
                         │              │
              result_explanation ◄──────┘
                         │
                    evaluate
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
    final_answer    final_answer    error_handler
         │               │               │
         └───────────────┼───────────────┘
                         │
                        END
"""

from langgraph.graph import StateGraph, END
from typing import List, Optional
from langchain_core.language_models import BaseLLM
from langchain_core.tools import BaseTool
from .state import AgentState
from .nodes import NodeManager
import logging

logger = logging.getLogger(__name__)


class AgentGraphBuilder:
    """构建LangGraph Agent图"""

    def __init__(self, llm: BaseLLM, tools: List[BaseTool], memory_manager: Optional[object] = None):
        self.llm = llm
        self.tools = tools
        self.memory_manager = memory_manager
        self.node_manager = NodeManager(llm, tools, memory_manager)

    def build(self, checkpointer_path: str = ":memory:") -> object:
        """构建并返回编译后的图"""

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
        graph.add_node("tool_execution", self.node_manager.tool_execution_node)
        graph.add_node("evaluate", self.node_manager.evaluate_node)
        graph.add_node("final_answer", self.node_manager.final_answer_node)
        graph.add_node("error_handler", self.node_manager.error_handler_node)

        # 定义边
        graph.add_edge("input_processing", "intent_detection")

        # 所有路径都先走术语澄清（避免理解错误）
        graph.add_edge("intent_detection", "terminology_clarification")

        # 术语澄清后的条件路由 - 根据意图类型决定是否继续查询
        graph.add_conditional_edges(
            "terminology_clarification",
            self._route_after_clarification,
            {
                "knowledge": "result_explanation",     # 知识问题：澄清后直接解释
                "data": "time_check",                   # 数据问题：澄清后查询数据
                "hybrid": "time_check",                 # 混合问题：澄清后查询数据
            }
        )

        # 数据路径
        graph.add_edge("time_check", "schema_discovery")
        graph.add_edge("schema_discovery", "field_probing")
        graph.add_edge("field_probing", "main_query")
        graph.add_edge("main_query", "result_explanation")

        # 从terminology_clarification对于hybrid路径继续到数据路径
        # 这通过result_explanation节点的后处理或通过额外的条件边实现
        # 当前简化：都通过result_explanation到evaluate

        # 所有查询路径都进入结果解释和评测
        graph.add_edge("result_explanation", "evaluate")

        # 条件边：Agent循环是否继续
        graph.add_conditional_edges(
            "agent_loop",
            self._should_continue_loop,
            {
                "continue": "tool_execution",
                "finish": "evaluate"
            }
        )

        # 工具执行后的条件边
        graph.add_conditional_edges(
            "tool_execution",
            self._handle_tool_execution,
            {
                "loop": "agent_loop",
                "error": "error_handler",
                "finish": "evaluate"
            }
        )

        # 评测后的条件边
        graph.add_conditional_edges(
            "evaluate",
            self._route_on_evaluation,
            {
                "passed": "final_answer",
                "retry": "agent_loop",
                "failed": "error_handler"
            }
        )

        # 最终答案和错误都指向END
        graph.add_edge("final_answer", END)
        graph.add_edge("error_handler", END)

        # 设置入口点
        graph.set_entry_point("input_processing")

        # 创建Checkpointer
        try:
            if checkpointer_path == ":memory:":
                from langgraph.checkpoint.memory import MemorySaver
                checkpointer = MemorySaver()
            else:
                from langgraph.checkpoint.sqlite import SqliteSaver
                checkpointer = SqliteSaver.from_conn_string(checkpointer_path)

            # 编译图，传入checkpointer
            compiled_graph = graph.compile(checkpointer=checkpointer)
        except ImportError as e:
            logger.error(f"Failed to import checkpointer: {e}")
            # Fallback: compile without checkpointer
            compiled_graph = graph.compile()
        except Exception as e:
            logger.error(f"Failed to create checkpointer: {e}")
            # Fallback: compile without checkpointer
            compiled_graph = graph.compile()

        return compiled_graph

    # ============ 路由函数 ============

    def _route_after_clarification(self, state: AgentState) -> str:
        """术语澄清后的路由 - 决定是否继续查询数据"""
        intent = state.get("intent_type", "data")
        logger.info(f"Routing after clarification: {intent}")

        if intent == "knowledge":
            # 知识问题：澄清后直接解释，无需查询
            return "knowledge"
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
        """根据评测结果路由"""

        if state["eval_passed"]:
            return "passed"

        # 如果评测失败但还能重试，重试
        if state["retry_count"] < 2:
            return "retry"

        # 重试次数过多，返回失败
        return "failed"


def create_agent_graph(
    llm: BaseLLM,
    tools: List[BaseTool],
    memory_manager: Optional[object] = None,
    checkpointer_path: str = ":memory:"
) -> object:
    """便利函数：创建Agent图"""

    builder = AgentGraphBuilder(llm, tools, memory_manager)
    return builder.build(checkpointer_path)
