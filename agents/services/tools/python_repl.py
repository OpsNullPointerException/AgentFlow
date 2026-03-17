"""Python代码执行工具"""

import sys
from io import StringIO
from typing import Optional, Type
from langchain_core.callbacks.manager import CallbackManagerForToolRun
from langchain_core.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, Field


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

            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()

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

            try:
                import math
                import datetime

                safe_globals["math"] = math
                safe_globals["datetime"] = datetime
            except ImportError:
                pass

            exec(code, safe_globals)

            sys.stdout = old_stdout
            output = captured_output.getvalue()

            return output if output else "代码执行完成，无输出。"

        except Exception as e:
            sys.stdout = old_stdout
            logger.error(f"Python代码执行失败: {e}")
            return f"代码执行失败: {str(e)}"
