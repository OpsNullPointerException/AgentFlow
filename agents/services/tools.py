"""
基于LangChain的Agent工具集成
"""
from typing import Dict, List, Optional, Type

from ddgs import DDGS
from langchain.callbacks.manager import CallbackManagerForToolRun
from langchain.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, Field

from qa.services.rag_service import RAGService


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
                query=query,
                top_k=top_k,
                enable_rerank=enable_rerank
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
            allowed_names = {
                k: v for k, v in __builtins__.items() 
                if k in ["abs", "round", "min", "max", "sum", "pow"]
            }
            allowed_names.update({
                "sin": __import__("math").sin,
                "cos": __import__("math").cos,
                "tan": __import__("math").tan,
                "sqrt": __import__("math").sqrt,
                "log": __import__("math").log,
                "pi": __import__("math").pi,
                "e": __import__("math").e,
            })
            
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
                    title = result.get('title', '无标题')
                    body = result.get('body', '无摘要')
                    url = result.get('href', '无链接')
                    
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


class ToolRegistry:
    """工具注册表"""
    
    _tools: Dict[str, Type[BaseTool]] = {
        "document_search": DocumentSearchTool,
        "calculator": CalculatorTool,
        "python_repl": PythonREPLTool,
        "web_search": WebSearchTool,
    }
    
    @classmethod
    def get_tool(cls, tool_name: str, **kwargs) -> Optional[BaseTool]:
        """获取工具实例"""
        tool_class = cls._tools.get(tool_name)
        if tool_class:
            try:
                return tool_class(**kwargs)
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