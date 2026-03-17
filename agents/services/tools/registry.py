"""工具注册表 - 统一管理所有工具"""

from typing import Dict, List, Optional, Type
from langchain_core.tools import BaseTool
from loguru import logger

from ..tool_retry import ToolRetryWrapper
from .document_search import DocumentSearchTool
from .calculator import CalculatorTool
from .python_repl import PythonREPLTool
from .web_search import WebSearchTool
from .sql_query import SQLQueryTool
from .schema_query import SchemaQueryTool
from .time_conversion import TimeConversionTool


class ToolRegistry:
    """工具注册表"""

    _tools: Dict[str, Type[BaseTool]] = {
        "document_search": DocumentSearchTool,
        "calculator": CalculatorTool,
        "python_repl": PythonREPLTool,
        "web_search": WebSearchTool,
        "sql_query": SQLQueryTool,
        "schema_query": SchemaQueryTool,
        "convert_relative_time": TimeConversionTool,
    }

    @classmethod
    def get_tool(cls, tool_name: str, **kwargs) -> Optional[BaseTool]:
        """获取工具实例，关键工具自动应用重试机制"""
        tool_class = cls._tools.get(tool_name)
        if tool_class:
            try:
                tool = tool_class(**kwargs)

                # 对关键工具应用重试机制
                if tool_name in ["document_search", "sql_query", "schema_query"]:
                    max_retries = kwargs.get("max_retries", 3)
                    backoff_factor = kwargs.get("backoff_factor", 2.0)
                    base_delay = kwargs.get("base_delay", 0.5)

                    wrapped_tool = ToolRetryWrapper(
                        tool._run,
                        max_retries=max_retries,
                        backoff_factor=backoff_factor,
                        base_delay=base_delay,
                        retryable_exceptions=(ConnectionError, TimeoutError, Exception),
                    )

                    tool._run = wrapped_tool.execute
                    logger.info(f"工具 {tool_name} 已应用重试机制 (max_retries={max_retries})")

                return tool
            except Exception as e:
                logger.error(f"创建工具实例失败 {tool_name}: {e}")
                return None
        return None

    @classmethod
    def get_available_tools(cls) -> List[str]:
        """获取可用工具列表"""
        return list(cls._tools.keys())

    @classmethod
    def register_tool(cls, name: str, tool_class: Type[BaseTool]):
        """注册新工具"""
        cls._tools[name] = tool_class
        logger.info(f"注册工具: {name}")

    @classmethod
    def get_tools_by_names(cls, tool_names: List[str], **kwargs) -> List[BaseTool]:
        """根据名称列表获取工具实例"""
        tools = []
        for name in tool_names:
            tool = cls.get_tool(name, **kwargs)
            if tool:
                tools.append(tool)
            else:
                logger.warning(f"工具不存在或创建失败: {name}")
        return tools
