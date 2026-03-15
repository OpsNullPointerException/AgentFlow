"""Schema查询工具"""

from typing import Optional, Type
from django.db import connection
from langchain.callbacks.manager import CallbackManagerForToolRun
from langchain.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, Field


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
                    cursor.execute("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = DATABASE()
                    """)
                    tables = [row[0] for row in cursor.fetchall()]
                    return "可用的表:\n" + "\n".join(f"- {t}" for t in tables)
                else:
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
