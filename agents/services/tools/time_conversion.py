"""
相对时间处理工具

将用户的相对时间表达转换为具体的日期范围
例：昨天、上周、近30天等
"""

from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, Type
import re
from langchain_core.callbacks.manager import CallbackManagerForToolRun
from langchain_core.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, Field


class TimeConversionInput(BaseModel):
    """相对时间转换的输入"""
    relative_time: str = Field(
        ...,
        description="相对时间表达，如'昨天'、'上周'、'近30天'、'本月'、'去年'等"
    )
    reference_date: Optional[str] = Field(
        None,
        description="参考日期，格式YYYY-MM-DD，默认为今天"
    )


class TimeConversionTool(BaseTool):
    """
    相对时间转换工具

    将用户的相对时间表达（如"昨天"、"上周"、"近30天"等）
    转换为具体的日期范围（start_date, end_date）
    """

    name: str = "convert_relative_time"
    description: str = """将相对时间表达转换为具体日期范围。

支持的表达包括：
- 昨天、今天、明天
- 上周、本周、下周
- 上月、本月、下月
- 近7天、近30天、近90天、近365天
- 去年、今年
- 第一季度、第二季度等

返回格式：
{
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "description": "时间范围描述"
}
"""

    args_schema: Type[BaseModel] = TimeConversionInput

    def _parse_relative_time(
        self,
        relative_time: str,
        reference_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        解析相对时间表达式

        Args:
            relative_time: 相对时间字符串
            reference_date: 参考日期（默认今天）

        Returns:
            包含 start_date, end_date, description 的字典
        """
        if reference_date is None:
            reference_date = datetime.now()
        elif isinstance(reference_date, str):
            reference_date = datetime.strptime(reference_date, "%Y-%m-%d")

        reference_date = reference_date.replace(hour=0, minute=0, second=0, microsecond=0)
        today = reference_date.date()

        # 归一化输入
        text = relative_time.lower().strip()

        # 单日期表达
        if text in ["昨天", "昨日"]:
            target = today - timedelta(days=1)
            return {
                "start_date": target.strftime("%Y-%m-%d"),
                "end_date": target.strftime("%Y-%m-%d"),
                "description": "昨天"
            }

        if text in ["今天", "今日"]:
            return {
                "start_date": today.strftime("%Y-%m-%d"),
                "end_date": today.strftime("%Y-%m-%d"),
                "description": "今天"
            }

        if text in ["明天"]:
            target = today + timedelta(days=1)
            return {
                "start_date": target.strftime("%Y-%m-%d"),
                "end_date": target.strftime("%Y-%m-%d"),
                "description": "明天"
            }

        # 周相关
        weekday = today.weekday()  # 0=周一, 6=周日

        if text in ["上周", "上一周", "上周一"]:
            week_start = today - timedelta(days=weekday + 7)
            week_end = week_start + timedelta(days=6)
            return {
                "start_date": week_start.strftime("%Y-%m-%d"),
                "end_date": week_end.strftime("%Y-%m-%d"),
                "description": "上周"
            }

        if text in ["本周", "这周"]:
            week_start = today - timedelta(days=weekday)
            week_end = today
            return {
                "start_date": week_start.strftime("%Y-%m-%d"),
                "end_date": week_end.strftime("%Y-%m-%d"),
                "description": "本周"
            }

        if text in ["下周", "下一周"]:
            week_start = today + timedelta(days=7 - weekday)
            week_end = week_start + timedelta(days=6)
            return {
                "start_date": week_start.strftime("%Y-%m-%d"),
                "end_date": week_end.strftime("%Y-%m-%d"),
                "description": "下周"
            }

        # 月相关
        if text in ["上月", "上一月", "上个月"]:
            first_of_month = today.replace(day=1)
            last_of_prev_month = first_of_month - timedelta(days=1)
            first_of_prev_month = last_of_prev_month.replace(day=1)
            return {
                "start_date": first_of_prev_month.strftime("%Y-%m-%d"),
                "end_date": last_of_prev_month.strftime("%Y-%m-%d"),
                "description": "上个月"
            }

        if text in ["本月", "这个月"]:
            first_of_month = today.replace(day=1)
            return {
                "start_date": first_of_month.strftime("%Y-%m-%d"),
                "end_date": today.strftime("%Y-%m-%d"),
                "description": "本月"
            }

        if text in ["下月", "下一月", "下个月"]:
            if today.month == 12:
                first_of_next_month = today.replace(year=today.year + 1, month=1, day=1)
            else:
                first_of_next_month = today.replace(month=today.month + 1, day=1)

            if first_of_next_month.month == 12:
                last_of_next_month = first_of_next_month.replace(year=first_of_next_month.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                last_of_next_month = first_of_next_month.replace(month=first_of_next_month.month + 1, day=1) - timedelta(days=1)

            return {
                "start_date": first_of_next_month.strftime("%Y-%m-%d"),
                "end_date": last_of_next_month.strftime("%Y-%m-%d"),
                "description": "下个月"
            }

        # 近N天
        match = re.match(r"近(\d+)天", text)
        if match:
            days = int(match.group(1))
            start = today - timedelta(days=days - 1)
            return {
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": today.strftime("%Y-%m-%d"),
                "description": f"最近{days}天"
            }

        # 年相关
        if text in ["去年", "上一年", "上年"]:
            start = today.replace(year=today.year - 1, month=1, day=1)
            end = start.replace(month=12, day=31)
            return {
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": end.strftime("%Y-%m-%d"),
                "description": "去年"
            }

        if text in ["今年", "本年"]:
            start = today.replace(month=1, day=1)
            return {
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": today.strftime("%Y-%m-%d"),
                "description": "今年"
            }

        # 季度
        quarter_map = {
            "第一季度": (1, 1, 3, 31),
            "第二季度": (2, 4, 6, 30),
            "第三季度": (3, 7, 9, 30),
            "第四季度": (4, 10, 12, 31),
            "q1": (1, 1, 3, 31),
            "q2": (2, 4, 6, 30),
            "q3": (3, 7, 9, 30),
            "q4": (4, 10, 12, 31),
        }

        for key, (quarter, start_month, end_month, end_day) in quarter_map.items():
            if key in text:
                start = today.replace(month=start_month, day=1)
                end = today.replace(month=end_month, day=end_day)
                return {
                    "start_date": start.strftime("%Y-%m-%d"),
                    "end_date": end.strftime("%Y-%m-%d"),
                    "description": f"第{quarter}季度"
                }

        return {
            "error": f"无法解析相对时间表达：'{relative_time}'",
            "supported": ["昨天", "今天", "上周", "本周", "上月", "本月", "近7天", "近30天", "去年", "今年", "Q1-Q4"]
        }

    def _run(
        self,
        relative_time: str,
        reference_date: Optional[str] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """执行相对时间转换"""
        try:
            logger.info(f"相对时间转换: {relative_time}")

            result = self._parse_relative_time(relative_time, reference_date)

            if "error" in result:
                return f"错误: {result['error']}\n支持的表达: {', '.join(result.get('supported', []))}"

            import json
            return json.dumps(result, ensure_ascii=False)

        except Exception as e:
            logger.error(f"时间转换失败: {str(e)}")
            return f"时间转换失败: {str(e)}"
