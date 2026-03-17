"""
LangGraph 工具调用架构重构 - 代码示例

新架构关键特性：
1. LLM通过bind_tools知道可用工具
2. LLM输出structured AIMessage with tool_calls
3. ToolNode自动执行工具
4. tools_condition智能路由
"""

from typing import Any, Dict, Optional, Annotated
from datetime import datetime
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, add_messages
from langchain_core.language_models import BaseLLM
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
import logging

logger = logging.getLogger(__name__)


# ============ 改进的AgentState ============

class AgentState(TypedDict):
    """使用标准LangGraph消息格式的状态"""

    # 标准消息历史（替代agent_scratchpad）
    messages: Annotated[list[BaseMessage], add_messages]

    # 用户输入
    user_input: str
    user_id: str
    agent_id: str

    # 多路径信息
    intent_type: Optional[str]  # knowledge/data/hybrid
    clarified_terms: list[dict[str, str]]
    time_range: Optional[dict[str, str]]
    relevant_tables: list[str]
    relevant_fields: dict[str, list[str]]
    field_samples: dict[str, list[Any]]

    # 执行追踪
    execution_steps: list
    tools_used: list[str]
    masked_observations: list[str]

    # 评测和重试
    eval_score: Optional[float]
    error_category: Optional[str]
    retry_count: int

    # 最终结果
    final_answer: Optional[str]
    explanation: Optional[str]


# ============ 改进的NodeManager ============

class ImprovedNodeManager:
    """使用LangGraph ToolNode的节点管理器"""

    def __init__(self, llm: BaseLLM, tools: list[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}

        # 关键改进：bind_tools到LLM
        self.model_with_tools = llm.bind_tools(tools)
        logger.info(f"绑定{len(tools)}个工具到LLM")

    # ============ 改进的agent_loop ============

    def agent_loop_node(self, state: AgentState) -> Dict[str, Any]:
        """改进：使用bind_tools和structured output"""

        logger.info(f"Agent循环迭代 (messages={len(state['messages'])})")

        # 构建系统提示
        system_prompt = self._build_system_prompt(state)

        # 构建消息列表（标准格式）
        messages = [HumanMessage(content=system_prompt)] + state["messages"]

        # 调用LLM - 关键：model_with_tools输出AIMessage with tool_calls
        try:
            response = self.model_with_tools.invoke(messages)
            logger.info(f"LLM响应: {len(response.content)}字符, "
                       f"tool_calls={len(response.tool_calls) if hasattr(response, 'tool_calls') else 0}")
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return {
                "messages": state["messages"] + [
                    AIMessage(content=f"发生错误: {str(e)}")
                ],
                "error_category": "permanent_error"
            }

        # 返回新的消息状态
        # 注意：不再需要手动解析Action！
        return {
            "messages": state["messages"] + [response],
            "execution_steps": state["execution_steps"] + [{
                "type": "model_call",
                "timestamp": datetime.now().isoformat(),
                "content_length": len(response.content),
                "tool_calls": len(response.tool_calls) if hasattr(response, 'tool_calls') else 0
            }]
        }

    def _build_system_prompt(self, state: AgentState) -> str:
        """构建系统提示 - 不再需要列出工具（LLM已知）"""
        intent = state.get("intent_type", "unknown")

        if intent == "knowledge":
            return f"""您是一个知识助手。
用户问题：{state['user_input']}

已澄清术语：{state.get('clarified_terms', [])}

请使用可用的工具来查找相关知识。"""

        elif intent == "data":
            return f"""您是一个数据分析助手。
用户问题：{state['user_input']}

可用表：{state.get('relevant_tables', [])}
时间范围：{state.get('time_range')}

请生成SQL查询来获取数据。"""

        else:
            return f"""您是一个通用助手。用户问题：{state['user_input']}"""

    # ============ ToolNode（LangGraph内置）============
    # 不需要实现！LangGraph已提供
    # 工作流程：
    # 1. 接收AIMessage with tool_calls
    # 2. 逐个执行tool_calls
    # 3. 生成ToolMessage with results
    # 4. 添加到messages

    def get_tool_node(self) -> ToolNode:
        """返回配置好的ToolNode"""
        return ToolNode(
            tools=self.tools,
            handle_tool_errors=True,  # 自动错误处理
        )

    # ============ 结果处理节点 ============

    def result_explanation_node(self, state: AgentState) -> Dict[str, Any]:
        """从最后的消息生成解释"""

        logger.info("生成结果解释")

        # 从消息历史提取结果
        last_message = state["messages"][-1]

        if isinstance(last_message, ToolMessage):
            # 工具返回结果
            tool_result = last_message.content
            tool_name = last_message.tool_name
            logger.info(f"从{tool_name}获取结果")
        else:
            # 直接是AI回复
            tool_result = last_message.content
            tool_name = None

        # 生成自然语言解释
        explanation_prompt = f"""
根据以下结果生成简洁的中文解释：
结果：{tool_result}

请用自然语言总结这个结果的含义。"""

        try:
            # 使用不带工具的LLM生成解释（避免嵌套工具调用）
            explanation = self.llm.predict(explanation_prompt)
        except Exception as e:
            explanation = f"无法生成解释: {str(e)}"

        return {
            "explanation": explanation,
            "final_answer": tool_result,
            "current_tool": tool_name,
            "tools_used": state["tools_used"] + [tool_name] if tool_name else state["tools_used"]
        }


# ============ 改进的图构建 ============

class ImprovedAgentGraphBuilder:
    """使用ToolNode的图构建器"""

    def __init__(self, llm: BaseLLM, tools: list[BaseTool]):
        self.node_manager = ImprovedNodeManager(llm, tools)
        self.llm = llm
        self.tools = tools

    def build(self):
        """构建图"""

        graph = StateGraph(AgentState)

        # 添加节点
        graph.add_node("input_processing", self._input_processing_node)
        graph.add_node("agent", self.node_manager.agent_loop_node)
        graph.add_node("tools", self.node_manager.get_tool_node())  # LangGraph ToolNode
        graph.add_node("result_explanation", self.node_manager.result_explanation_node)
        graph.add_node("evaluate", self._evaluate_node)
        graph.add_node("final_answer", self._final_answer_node)

        # 定义边
        graph.add_edge("input_processing", "agent")

        # 关键：tools_condition - 智能路由
        from langgraph.prebuilt import tools_condition
        graph.add_conditional_edges(
            "agent",
            tools_condition,  # 检查是否有tool_calls
            {
                "tools": "tools",      # 有tool_calls -> 执行工具
                "__end__": "result_explanation"  # 无tool_calls -> 结束推理
            }
        )

        # 工具执行后回到agent继续推理
        graph.add_edge("tools", "agent")

        # 结果处理
        graph.add_edge("result_explanation", "evaluate")

        # 评测后决定是否重试
        graph.add_conditional_edges(
            "evaluate",
            self._route_on_evaluation,
            {
                "retry": "agent",
                "success": "final_answer",
                "failed": "final_answer"
            }
        )

        graph.add_edge("final_answer", END)

        # 设置入口点
        graph.set_entry_point("input_processing")

        return graph.compile()

    def _input_processing_node(self, state: AgentState) -> Dict[str, Any]:
        """输入处理"""
        logger.info(f"处理输入: {state['user_input'][:50]}...")
        return {}

    def _evaluate_node(self, state: AgentState) -> Dict[str, Any]:
        """评测结果"""
        # 实现评测逻辑（保持不变）
        return {"eval_score": 0.8, "error_category": None}

    def _route_on_evaluation(self, state: AgentState) -> str:
        """路由决策"""
        score = state.get("eval_score", 0.0)
        return "success" if score > 0.7 else "failed"

    def _final_answer_node(self, state: AgentState) -> Dict[str, Any]:
        """生成最终答案"""
        return {
            "final_answer": state.get("final_answer", "处理完成")
        }


# ============ 使用示例 ============

def demo():
    """演示新架构的用法"""

    from langchain_community.llms import Tongyi
    from agents.services.tools import ToolRegistry

    # 初始化LLM和工具
    llm = Tongyi(model_name="qwen-turbo", temperature=0.1)
    tools = ToolRegistry.get_tools_by_names(['document_search', 'sql_query'])

    # 构建图
    builder = ImprovedAgentGraphBuilder(llm, tools)
    graph = builder.build()

    # 执行
    state = {
        "messages": [HumanMessage(content="什么是A厂商？")],
        "user_input": "什么是A厂商？",
        "user_id": "user1",
        "agent_id": "agent1",
        "intent_type": "knowledge",
        "clarified_terms": [],
        "time_range": None,
        "relevant_tables": [],
        "relevant_fields": {},
        "field_samples": {},
        "execution_steps": [],
        "tools_used": [],
        "masked_observations": [],
        "eval_score": None,
        "error_category": None,
        "retry_count": 0,
        "final_answer": None,
        "explanation": None,
    }

    result = graph.invoke(state)
    print(f"最终答案: {result.get('final_answer')}")


if __name__ == "__main__":
    print("这是新架构示例代码")
    print("关键改进:")
    print("1. LLM通过bind_tools获得工具schema")
    print("2. agent_loop输出AIMessage with tool_calls")
    print("3. ToolNode自动处理tool_calls执行")
    print("4. tools_condition智能路由")
    print("5. 无需手动正则解析Action")
