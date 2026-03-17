"""网络搜索工具"""

from typing import Optional, Type
from ddgs import DDGS
from langchain_core.callbacks.manager import CallbackManagerForToolRun
from langchain_core.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, Field


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

            with DDGS() as ddgs:
                logger.info("🌐 正在连接DuckDuckGo搜索引擎...")
                results = list(ddgs.text(query, max_results=num_results))

                logger.info(f"✅ 搜索完成，找到 {len(results)} 个结果")

                if not results:
                    logger.warning("❌ 没有找到任何搜索结果")
                    return f"未找到关于'{query}'的搜索结果。"

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

                return final_result

        except Exception as e:
            logger.error(f"网络搜索工具执行失败: {e}")
            return f"搜索失败: {str(e)}"
