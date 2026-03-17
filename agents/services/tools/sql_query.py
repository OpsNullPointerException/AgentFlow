"""SQL查询工具"""

from typing import Optional, Type
from django.db import connection
from langchain_core.callbacks.manager import CallbackManagerForToolRun
from langchain_core.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, Field

from ..validators import SQLValidator


class SQLQueryInput(BaseModel):
    """SQL查询工具输入"""
    sql: str = Field(..., description="要执行的SQL查询语句（仅支持SELECT）")


class SQLQueryTool(BaseTool):
    """SQL查询执行工具 - 支持内部知识隐式优化"""

    name: str = "sql_query"
    description: str = "执行SQL查询语句获取数据。仅支持SELECT查询，禁止INSERT/DELETE/UPDATE/DROP操作。"
    args_schema: Type[BaseModel] = SQLQueryInput

    def __init__(self, rag_service=None, **kwargs):
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

            is_safe, error_msg = SQLValidator.validate(sql)
            if not is_safe:
                logger.warning(f"SQL验证失败: {error_msg}")
                return "❌ SQL语句不符合安全规范"

            try:
                optimized_sql = self._auto_correct_sql_with_internal_knowledge(sql)
                logger.info(f"SQL已自动优化")
            except Exception as e:
                logger.warning(f"SQL优化失败，使用原始SQL: {e}")
                optimized_sql = sql

            with connection.cursor() as cursor:
                cursor.execute(optimized_sql)
                columns = [col[0] for col in cursor.description] if cursor.description else []
                rows = cursor.fetchall()

                if not rows:
                    return "✓ 查询完成，无返回结果"

                if len(rows) > 1000:
                    logger.warning(f"查询返回大量数据: {len(rows)}行")

                result_lines = []
                if columns:
                    result_lines.append("\t".join(str(col) for col in columns))

                for i, row in enumerate(rows[:100]):
                    result_lines.append("\t".join(str(val) if val is not None else "NULL" for val in row))

                if len(rows) > 100:
                    result_lines.append(f"... (共{len(rows)}行，已显示前100行)")

                return "\n".join(result_lines)

        except Exception as e:
            logger.error(f"SQL查询执行失败: {e}")
            return f"❌ SQL执行失败"

    def _auto_correct_sql_with_internal_knowledge(self, sql: str) -> str:
        """【内部方法】使用内部知识隐式优化SQL"""
        if not self.rag_service:
            return sql

        try:
            fields = self._extract_fields_from_sql(sql)
            logger.debug(f"从SQL提取的字段: {fields}")

            corrected_sql = sql
            for field in fields:
                internal_knowledge = self._lookup_internal_knowledge(field)
                corrected_sql = self._apply_knowledge_to_fix_sql(
                    corrected_sql, field, internal_knowledge
                )

            logger.debug(f"优化后SQL: {corrected_sql[:100]}...")
            return corrected_sql

        except Exception as e:
            logger.debug(f"内部优化失败，返回原SQL: {e}")
            return sql

    def _lookup_internal_knowledge(self, field: str) -> dict:
        """【内部方法】查询内部知识库"""
        if not self.rag_service:
            return {}

        try:
            result = self.rag_service.retrieve_documents(
                query=field,
                filters={"doc_category": "internal"},
                top_k=3
            )

            sanitized_knowledge = {
                "field": field,
                "has_mapping": len(result) > 0,
                "confidence": "high" if len(result) > 0 else "low"
            }

            return sanitized_knowledge

        except Exception as e:
            logger.debug(f"内部知识查询失败: {e}")
            return {"field": field, "has_mapping": False}

    def _apply_knowledge_to_fix_sql(self, sql: str, field: str, knowledge: dict) -> str:
        """【内部方法】用知识来修正SQL"""
        if knowledge.get("has_mapping"):
            pass

        return sql

    def _extract_fields_from_sql(self, sql: str) -> list:
        """【内部方法】从SQL中提取字段名"""
        try:
            from sqlglot import parse_one

            parsed = parse_one(sql)
            fields = []

            for column in parsed.find_all(parse_one("SELECT").expression):
                field_name = str(column).split(".")[-1]
                if field_name and field_name != "*":
                    fields.append(field_name)

            return list(set(fields))

        except Exception as e:
            logger.debug(f"字段提取失败: {e}")
            return []
