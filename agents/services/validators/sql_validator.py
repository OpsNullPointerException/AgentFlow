"""SQL安全验证器"""

from loguru import logger

try:
    from sqlglot import parse
    from sqlglot.expressions import Select, Star
    SQLGLOT_AVAILABLE = True
except ImportError:
    SQLGLOT_AVAILABLE = False
    logger.warning("SQLGlot未安装，某些SQL校验功能将不可用")


class SQLValidator:
    """多层SQL安全验证器"""

    # 禁止的操作关键字
    DANGEROUS_KEYWORDS = ['INSERT', 'DELETE', 'UPDATE', 'DROP', 'ALTER', 'TRUNCATE', 'CREATE', 'REPLACE']

    # 禁止访问的敏感字段
    SENSITIVE_FIELDS = ['password', 'secret', 'token', 'api_key', 'private_key', 'credit_card']

    @classmethod
    def validate(cls, sql: str) -> tuple[bool, str]:
        """
        完整的SQL验证流程
        返回: (是否安全, 错误消息或验证后的SQL)
        """
        try:
            # 第1层：操作类型检查（黑名单）
            result = cls._check_operation_type(sql)
            if not result[0]:
                return result

            # 第2层：AST解析级别的检查
            if SQLGLOT_AVAILABLE:
                result = cls._check_ast_safety(sql)
                if not result[0]:
                    return result

            # 第3层：执行前探测（检查预计返回行数）
            # 这部分在SQLQueryTool中执行，因为需要数据库连接

            return (True, sql)

        except Exception as e:
            logger.error(f"SQL验证异常: {e}")
            return (False, f"验证过程出错: {str(e)}")

    @classmethod
    def _check_operation_type(cls, sql: str) -> tuple[bool, str]:
        """第1层：检查操作类型（禁止修改操作）"""
        sql_upper = sql.upper().strip()

        # 必须是SELECT
        if not sql_upper.startswith('SELECT'):
            return (False, "❌ 必须是SELECT查询语句")

        # 禁止危险操作
        for keyword in cls.DANGEROUS_KEYWORDS:
            # 使用word boundary检查，避免子字符串匹配
            if f' {keyword} ' in f' {sql_upper} ':
                return (False, f"❌ 禁止操作: {keyword}")

        return (True, "")

    @classmethod
    def _check_ast_safety(cls, sql: str) -> tuple[bool, str]:
        """第2层：AST解析级别的安全检查"""
        if not SQLGLOT_AVAILABLE:
            return (True, "")

        try:
            ast = parse(sql)[0]

            # 检查1：禁止SELECT *
            for select in ast.find_all(Select):
                for expr in select.expressions:
                    if isinstance(expr, Star):
                        return (False, "❌ 禁止使用 SELECT *（必须指定具体字段）")

            # 检查2：禁止访问敏感字段
            for sensitive_field in cls.SENSITIVE_FIELDS:
                if f'`{sensitive_field}`' in sql or f"'{sensitive_field}'" in sql:
                    return (False, f"❌ 禁止访问敏感字段: {sensitive_field}")

            # 检查3：检查JOIN数量
            joins = list(ast.find_all(lambda x: 'join' in str(type(x)).lower()))
            if len(joins) > 5:
                return (False, f"❌ JOIN数量过多（{len(joins)}个），可能导致性能问题")

            return (True, "")

        except Exception as e:
            logger.warning(f"AST解析失败: {e}，使用基础检查")
            return (True, "")

    @classmethod
    def check_result_size(cls, sql: str, estimated_rows: int, max_rows: int = 100000) -> tuple[bool, str]:
        """第3层：执行前探测，检查预计返回行数"""
        if estimated_rows > max_rows:
            return (False, f"❌ 查询结果过大（预计{estimated_rows:,}行，限制{max_rows:,}行）。请添加更多过滤条件")

        return (True, "")
