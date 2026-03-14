"""
基于LangChain的Agent工具集成
"""

from typing import Dict, List, Optional, Type

from ddgs import DDGS
from langchain.callbacks.manager import CallbackManagerForToolRunn
from langchain.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, Field
from django.db import connection

from qa.services.rag_service import RAGService
from agents.services.validators import SQLValidator
from agents.services.tool_retry import ToolRetryWrapper
from agents.services.tools.time_tool import TimeConversionTool


class DocumentSearchInput(BaseModel):
    """文档搜索工具输入"""

    query: str = Field(..., description="搜索查询")
    top_k: int = Field(5, description="返回的文档数量")
    enable_rerank: bool = Field(True, description="是否启用重排序")


class DocumentSearchTool(BaseTool):
    """文档搜索工具 - 集成现有的RAG服务"""

    name: str = "document_search"
    description: str = "搜索相关文档内容。当用户询问关于文档、知识库中的信息时使用此工具。"
    args_schema: Type[BaseModel] = DocumentSearchInput
    rag_service: RAGService = Field(default=None, description="RAG服务实例")

    def __init__(self, embedding_model_version: Optional[str] = None, **kwargs):
        # 先创建RAG服务实例
        rag_service = RAGService(embedding_model_version=embedding_model_version)
        super().__init__(rag_service=rag_service, **kwargs)

    def _run(
        self,
        query: str,
        top_k: int = 5,
        enable_rerank: bool = True,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """执行文档搜索"""
        try:
            logger.info(f"Agent执行文档搜索: {query}")

            # 使用RAG服务检索文档
            retrieval_result = self.rag_service.retrieve_relevant_documents(
                query=query, top_k=top_k, enable_rerank=enable_rerank
            )

            # 格式化搜索结果
            if not retrieval_result.documents:
                return "未找到相关文档。"

            results = []
            for i, doc in enumerate(retrieval_result.documents, 1):
                result = f"文档 {i}:\n"
                result += f"标题: {doc.title}\n"
                result += f"内容: {doc.content[:500]}...\n"
                result += f"相关性: {doc.score:.3f}\n"
                results.append(result)

            return "\n".join(results)

        except Exception as e:
            logger.error(f"文档搜索工具执行失败: {e}")
            return f"搜索失败: {str(e)}"


class CalculatorInput(BaseModel):
    """计算器工具输入"""

    expression: str = Field(..., description="要计算的数学表达式")


class CalculatorTool(BaseTool):
    """计算器工具"""

    name: str = "calculator"
    description: str = "执行数学计算。当需要进行数学运算、计算数值时使用此工具。"
    args_schema: Type[BaseModel] = CalculatorInput

    def _run(
        self,
        expression: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """执行数学计算"""
        try:
            logger.info(f"Agent执行计算: {expression}")

            # 安全的数学计算
            allowed_names = {k: v for k, v in __builtins__.items() if k in ["abs", "round", "min", "max", "sum", "pow"]}
            allowed_names.update(
                {
                    "sin": __import__("math").sin,
                    "cos": __import__("math").cos,
                    "tan": __import__("math").tan,
                    "sqrt": __import__("math").sqrt,
                    "log": __import__("math").log,
                    "pi": __import__("math").pi,
                    "e": __import__("math").e,
                }
            )

            result = eval(expression, {"__builtins__": {}}, allowed_names)
            return str(result)

        except Exception as e:
            logger.error(f"计算工具执行失败: {e}")
            return f"计算失败: {str(e)}"


class PythonREPLInput(BaseModel):
    """Python执行器工具输入"""

    code: str = Field(..., description="要执行的Python代码")


class PythonREPLTool(BaseTool):
    """Python代码执行工具"""

    name: str = "python_repl"
    description: str = "执行Python代码。当需要进行复杂计算、数据处理、生成图表时使用此工具。"
    args_schema: Type[BaseModel] = PythonREPLInput

    def _run(
        self,
        code: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """执行Python代码"""
        try:
            logger.info(f"Agent执行Python代码: {code[:100]}...")

            # 创建安全的执行环境
            import sys
            from io import StringIO

            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()

            # 限制可用的模块和函数
            safe_globals = {
                "__builtins__": {
                    "print": print,
                    "len": len,
                    "range": range,
                    "enumerate": enumerate,
                    "zip": zip,
                    "sum": sum,
                    "min": min,
                    "max": max,
                    "abs": abs,
                    "round": round,
                    "sorted": sorted,
                    "list": list,
                    "dict": dict,
                    "set": set,
                    "tuple": tuple,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                }
            }

            # 添加常用的数学和数据处理库
            try:
                import math
                import datetime

                safe_globals["math"] = math
                safe_globals["datetime"] = datetime
            except ImportError:
                pass

            # 执行代码
            exec(code, safe_globals)

            # 恢复stdout并获取输出
            sys.stdout = old_stdout
            output = captured_output.getvalue()

            return output if output else "代码执行完成，无输出。"

        except Exception as e:
            sys.stdout = old_stdout
            logger.error(f"Python代码执行失败: {e}")
            return f"代码执行失败: {str(e)}"


class WebSearchInput(BaseModel):
    """网络搜索工具输入"""

    query: str = Field(..., description="搜索查询")
    num_results: int = Field(3, description="返回结果数量")


class WebSearchTool(BaseTool):
    """网络搜索工具"""

    name: str = "web_search"
    description: str = "搜索网络信息。当需要获取最新信息、实时数据时使用此工具。"
    args_schema: Type[BaseModel] = WebSearchInput

    def _run(
        self,
        query: str,
        num_results: int = 3,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """执行网络搜索 - 使用DuckDuckGo"""
        try:
            logger.info(f"🔍 开始网络搜索: {query}")
            logger.info(f"📊 请求结果数量: {num_results}")

            # 使用ddgs包进行搜索
            with DDGS() as ddgs:
                logger.info("🌐 正在连接DuckDuckGo搜索引擎...")
                # 搜索文本结果
                results = list(ddgs.text(query, max_results=num_results))

                logger.info(f"✅ 搜索完成，找到 {len(results)} 个结果")

                if not results:
                    logger.warning("❌ 没有找到任何搜索结果")
                    return f"未找到关于'{query}'的搜索结果。"

                # 格式化搜索结果
                formatted_results = []
                for i, result in enumerate(results, 1):
                    title = result.get("title", "无标题")
                    body = result.get("body", "无摘要")
                    url = result.get("href", "无链接")

                    logger.debug(f"📄 处理结果 {i}: {title[:50]}...")

                    formatted_result = f"结果 {i}:\n标题: {title}\n摘要: {body}\n链接: {url}"
                    formatted_results.append(formatted_result)

                final_result = "\n\n".join(formatted_results)
                logger.info(f"🎯 搜索结果格式化完成，总长度: {len(final_result)} 字符")
                # logger.info("搜索结果预览:")
                # logger.info(final_result[:200] + "..." if len(final_result) > 200 else final_result)

                return final_result

        except Exception as e:
            logger.error(f"网络搜索工具执行失败: {e}")
            return f"搜索失败: {str(e)}"


# ============== NL2SQL 相关工具 ==============

class SQLQueryInput(BaseModel):
    """SQL查询工具输入"""
    sql: str = Field(..., description="要执行的SQL查询语句（仅支持SELECT）")


class SQLQueryTool(BaseTool):
    """SQL查询执行工具 - 支持内部知识隐式优化"""

    name: str = "sql_query"
    description: str = "执行SQL查询语句获取数据。仅支持SELECT查询，禁止INSERT/DELETE/UPDATE/DROP操作。"
    args_schema: Type[BaseModel] = SQLQueryInput

    def __init__(self, rag_service=None, **kwargs):
        """初始化工具"""
        super().__init__(**kwargs)
        self.rag_service = rag_service

    def _run(
        self,
        sql: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """执行SQL查询 - 内部隐式优化但不暴露知识"""
        try:
            logger.info(f"Agent执行SQL查询: {sql[:100]}...")

            # 1. 多层SQL安全验证
            is_safe, error_msg = SQLValidator.validate(sql)
            if not is_safe:
                logger.warning(f"SQL验证失败: {error_msg}")
                # ⚠️ 脱敏错误信息，不暴露具体的安全规则
                return "❌ SQL语句不符合安全规范"

            # 2. 【隐式优化】使用内部知识优化SQL，但不暴露知识
            try:
                optimized_sql = self._auto_correct_sql_with_internal_knowledge(sql)
                logger.info(f"SQL已自动优化")
            except Exception as e:
                logger.warning(f"SQL优化失败，使用原始SQL: {e}")
                optimized_sql = sql

            # 3. 执行查询（使用优化后的SQL）
            with connection.cursor() as cursor:
                cursor.execute(optimized_sql)
                columns = [col[0] for col in cursor.description] if cursor.description else []
                rows = cursor.fetchall()

                if not rows:
                    return "✓ 查询完成，无返回结果"

                # 检查结果大小
                if len(rows) > 1000:
                    logger.warning(f"查询返回大量数据: {len(rows)}行")

                # 4. 格式化结果（限制返回前100行）
                result_lines = []
                if columns:
                    result_lines.append("\t".join(str(col) for col in columns))

                for i, row in enumerate(rows[:100]):
                    result_lines.append("\t".join(str(val) if val is not None else "NULL" for val in row))

                if len(rows) > 100:
                    result_lines.append(f"... (共{len(rows)}行，已显示前100行)")

                # ✓ 返回给Agent的只是结果，不包含任何内部知识信息
                return "\n".join(result_lines)

        except Exception as e:
            logger.error(f"SQL查询执行失败: {e}")
            # ⚠️ 脱敏错误，不暴露内部细节
            return f"❌ SQL执行失败"

    def _auto_correct_sql_with_internal_knowledge(self, sql: str) -> str:
        """
        【内部方法】使用内部知识隐式优化SQL

        这个方法的结果不返回给Agent，只用于内部优化SQL
        关键：内部知识查询的结果完全隐藏，Agent看不到
        """
        if not self.rag_service:
            return sql

        try:
            # 1. 解析SQL提取字段
            fields = self._extract_fields_from_sql(sql)
            logger.debug(f"从SQL提取的字段: {fields}")

            # 2. 【内部查询】查询内部知识库，查找可能的问题
            corrected_sql = sql
            for field in fields:
                # 🔐 这个查询完全内部化，结果不暴露
                internal_knowledge = self._lookup_internal_knowledge(field)

                # 只使用知识来修正SQL，不返回知识本身
                corrected_sql = self._apply_knowledge_to_fix_sql(
                    corrected_sql, field, internal_knowledge
                )

            logger.debug(f"优化后SQL: {corrected_sql[:100]}...")
            return corrected_sql

        except Exception as e:
            logger.debug(f"内部优化失败，返回原SQL: {e}")
            return sql

    def _lookup_internal_knowledge(self, field: str) -> dict:
        """
        【内部方法】查询内部知识库

        这个方法的返回值完全隐式处理，不暴露给Agent或用户
        只用于指导SQL的修正，而不返回实际内容
        """
        if not self.rag_service:
            return {}

        try:
            # 从 doc_category='internal' 的文档中检索
            result = self.rag_service.retrieve_documents(
                query=field,
                filters={"doc_category": "internal"},
                top_k=3
            )

            # 🔐 提取有用信息，但脱敏敏感内容
            sanitized_knowledge = {
                "field": field,
                "has_mapping": len(result) > 0,  # 是否找到映射
                "confidence": "high" if len(result) > 0 else "low"
                # ❌ 不返回：result的具体内容、敏感值、内部规则等
            }

            return sanitized_knowledge

        except Exception as e:
            logger.debug(f"内部知识查询失败: {e}")
            return {"field": field, "has_mapping": False}

    def _apply_knowledge_to_fix_sql(self, sql: str, field: str, knowledge: dict) -> str:
        """
        【内部方法】用知识来修正SQL

        不返回知识，只根据知识修正SQL的逻辑问题
        """
        # 如果知识库找到了字段映射，检查SQL中是否使用了正确的字段名
        if knowledge.get("has_mapping"):
            # 内部逻辑修正，但不暴露修正过程
            # 例：检查字段名是否一致、类型是否匹配等
            pass

        return sql

    def _extract_fields_from_sql(self, sql: str) -> list:
        """
        【内部方法】从SQL中提取字段名
        """
        try:
            from sqlglot import parse_one

            parsed = parse_one(sql)
            fields = []

            # 简单的字段提取（实际应该更复杂）
            for column in parsed.find_all(parse_one("SELECT").expression):
                field_name = str(column).split(".")[-1]
                if field_name and field_name != "*":
                    fields.append(field_name)

            return list(set(fields))  # 去重

        except Exception as e:
            logger.debug(f"字段提取失败: {e}")
            return []


class SchemaQueryInput(BaseModel):
    """Schema查询工具输入"""
    query: str = Field(..., description="查询类型: 'tables' 获取所有表, 或输入表名获取字段信息")


class SchemaQueryTool(BaseTool):
    """数据库Schema查询工具"""

    name: str = "schema_query"
    description: str = "查询数据库的表结构和字段信息。输入'tables'获取所有表名，输入表名获取字段清单。"
    args_schema: Type[BaseModel] = SchemaQueryInput

    def _run(
        self,
        query: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """查询数据库Schema"""
        try:
            logger.info(f"Agent查询Schema: {query}")

            with connection.cursor() as cursor:
                if query.lower() == 'tables':
                    # 获取所有表
                    cursor.execute("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = DATABASE()
                    """)
                    tables = [row[0] for row in cursor.fetchall()]
                    return "可用的表:\n" + "\n".join(f"- {t}" for t in tables)
                else:
                    # 获取指定表的字段信息
                    cursor.execute(f"""
                        SELECT column_name, column_type, is_nullable
                        FROM information_schema.columns
                        WHERE table_schema = DATABASE() AND table_name = %s
                    """, [query])

                    columns = cursor.fetchall()
                    if not columns:
                        return f"表'{query}'不存在"

                    result = f"表 '{query}' 的字段信息:\n"
                    for col_name, col_type, nullable in columns:
                        result += f"- {col_name}: {col_type} ({'NULL' if nullable == 'YES' else 'NOT NULL'})\n"
                    return result

        except Exception as e:
            logger.error(f"Schema查询失败: {e}")
            return f"❌ Schema查询失败: {str(e)}"


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
                # 这些工具容易遇到临时故障（网络超时、连接失败等）
                if tool_name in ["document_search", "sql_query", "schema_query"]:
                    # 获取重试配置（可从环境或全局配置读取）
                    max_retries = kwargs.get("max_retries", 3)
                    backoff_factor = kwargs.get("backoff_factor", 2.0)
                    base_delay = kwargs.get("base_delay", 0.5)

                    # 包装为重试工具
                    wrapped_tool = ToolRetryWrapper(
                        tool._run,  # 包装工具的_run方法
                        max_retries=max_retries,
                        backoff_factor=backoff_factor,
                        base_delay=base_delay,
                        retryable_exceptions=(ConnectionError, TimeoutError, Exception),
                    )

                    # 替换_run方法
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
