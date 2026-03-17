"""计算器工具"""

from typing import Optional, Type
from langchain_core.callbacks.manager import CallbackManagerForToolRun
from langchain_core.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, Field


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
