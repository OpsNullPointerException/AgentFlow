from loguru import logger
from typing import List, Dict, Any, Generator
from django.conf import settings
import dashscope
from dashscope.aigc.generation import Generation
import requests.exceptions
from common.utils.retry_utils import retry, log_retry, RetryableError

# 定义可重试的错误类型
class LLMAPIError(RetryableError):
    """LLM API调用错误"""
    pass

# loguru不需要getLogger

class LLMService:
    """大语言模型服务，负责与LLM API交互"""
    
    # 可用的模型配置，从慢到快排序
    MODELS = {
        "qwen-max": {"name": "千问MAX", "description": "最高质量，但速度较慢"},
        "qwen-plus": {"name": "千问Plus", "description": "平衡质量和速度"},
        "qwen-turbo": {"name": "千问Turbo", "description": "最快速度，质量稍差"},
    }
    
    def __init__(self, model_name="qwen-turbo"):
        # 设置DashScope API密钥
        self.api_key = settings.DASHSCOPE_API_KEY
        if not self.api_key:
            logger.warning("DASHSCOPE_API_KEY未设置，LLM服务将无法正常工作")
        else:
            # 配置DashScope客户端
            dashscope.api_key = self.api_key
        
        # 设置使用的模型
        self.model_name = model_name
        logger.info(f"使用LLM模型: {self.model_name}")
    
    # 使用重试装饰器包装generate_response方法
    @retry(
        max_tries=3,
        delay=2.0,
        backoff_factor=2.0,
        exceptions=[LLMAPIError, requests.exceptions.RequestException],
        on_retry=log_retry
    )
    def generate_response(self, query: str, context: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        调用千问大模型生成回答
        
        Args:
            query: 用户查询
            context: 相关文档上下文
            conversation_history: 对话历史 [{"role": "user", "content": "..."}]
            
        Returns:
            包含生成回答和元数据的字典
        """
        if not self.api_key:
            logger.error("未配置DASHSCOPE_API_KEY，无法调用LLM API")
            return {"answer": "系统错误：LLM API未配置", "error": True}
            
        try:
            # 构建提示词
            system_prompt = "你是一个智能助手，可以根据提供的文档回答问题。请只根据提供的上下文信息回答问题，如果上下文中没有相关信息，请直接说不知道。"
            
            # 构建消息历史
            messages = [{"role": "system", "content": system_prompt}]
            
            # 添加对话历史（如果有）
            if conversation_history and len(conversation_history) > 0:
                # 只使用最近的5轮对话
                recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
                messages.extend(recent_history)
            
            # 添加上下文和当前查询
            user_prompt = f"以下是相关文档内容：\n\n{context}\n\n我的问题是：{query}"
            messages.append({"role": "user", "content": user_prompt})
            
            # 调用千问API
            response = Generation.call(
                model=self.model_name,  # 使用设置的模型
                messages=messages,
                result_format='message',  # 返回结果格式
                temperature=0.7,  # 控制创造性
                max_tokens=2000,  # 最大生成长度
                top_p=0.8,  # 控制多样性
            )
            
            # 解析响应
            if response.status_code == 200:
                result = response.output.choices[0]['message']['content']
                usage = response.usage
                logger.info(f"LLM API调用成功，使用token: {usage['total_tokens']}")
                
                return {
                    "answer": result,
                    "tokens_used": usage['total_tokens'],
                    "error": False,
                    "model": self.model_name
                }
            else:
                logger.error(f"LLM API调用失败: {response.code}, {response.message}")
                # 抛出可重试的错误，让装饰器捕获并重试
                raise LLMAPIError(f"LLM API调用失败: {response.code}, {response.message}")
                
        except requests.exceptions.RequestException as e:
            # 网络错误直接抛出，由装饰器捕获并重试
            logger.error(f"网络请求错误: {str(e)}")
            raise
        except Exception as e:
            logger.exception(f"调用LLM API时发生异常: {str(e)}")
            return {"answer": f"系统错误: {str(e)}", "error": True}
    
    @retry(
        max_tries=3,
        delay=2.0,
        backoff_factor=2.0,
        exceptions=[LLMAPIError, requests.exceptions.RequestException],
        on_retry=log_retry
    )
    def generate_response_stream(self, query: str, context: str, conversation_history: List[Dict[str, str]] = None, model: str = None) -> Generator:
        """
        流式生成回答，边生成边返回
        
        Args:
            query: 用户查询
            context: 相关文档上下文
            conversation_history: 对话历史 [{"role": "user", "content": "..."}]
            model: 指定要使用的模型名称，如果为None则使用默认模型
            
        Returns:
            生成器，每次生成一小段内容
        """
        if not self.api_key:
            logger.error("未配置DASHSCOPE_API_KEY，无法调用LLM API")
            yield {"answer": "系统错误：LLM API未配置", "error": True, "finished": True}
            return
            
        try:
            # 构建提示词
            system_prompt = "你是一个智能助手，可以根据提供的文档回答问题。请只根据提供的上下文信息回答问题，如果上下文中没有相关信息，请直接说不知道。"
            
            # 构建消息历史
            messages = [{"role": "system", "content": system_prompt}]
            
            # 添加对话历史（如果有）
            if conversation_history and len(conversation_history) > 0:
                # 只使用最近的5轮对话
                recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
                messages.extend(recent_history)
            
            # 添加上下文和当前查询
            user_prompt = f"以下是相关文档内容：\n\n{context}\n\n我的问题是：{query}"
            messages.append({"role": "user", "content": user_prompt})
            
            # 确定使用的模型
            model_to_use = model if model else self.model_name
            
            # 调用千问API - 流式模式
            logger.info(f"开始流式调用LLM API，模型: {model_to_use}")
            response = Generation.call(
                model=model_to_use,
                messages=messages,
                result_format='message',
                temperature=0.7,
                max_tokens=2000,
                top_p=0.8,
                stream=True  # 启用流式输出
            )
            
            # 处理流式响应
            full_content = ""
            chunk_count = 0
            logger.info(f"开始处理流式响应...")
            
            for chunk in response:
                chunk_count += 1
                logger.debug(f"收到API数据块 #{chunk_count}")
                
                if chunk.status_code == 200:
                    if hasattr(chunk.output, 'choices') and len(chunk.output.choices) > 0:
                        choice = chunk.output.choices[0]
                        if 'message' in choice and 'content' in choice['message']:
                            content = choice['message']['content']
                            # 增量内容
                            delta = content[len(full_content):]
                            full_content = content
                            
                            # 记录增量内容
                            delta_preview = delta if len(delta) < 50 else delta[:50] + "..."
                            logger.debug(f"增量内容 #{chunk_count}: {delta_preview}")
                            
                            result = {
                                "answer_delta": delta,
                                "finished": False,
                                "model": model_to_use
                            }
                            logger.debug(f"生成数据: {result}")
                            yield result
                        else:
                            logger.warning(f"响应块#{chunk_count}缺少message.content字段")
                    else:
                        logger.warning(f"响应块#{chunk_count}缺少choices或为空")
                else:
                    logger.error(f"流式调用LLM API失败: {chunk.code}, {chunk.message}")
                    yield {
                        "answer_delta": "\n\n[生成过程中出错]",
                        "error": True,
                        "finished": True,
                        "error_message": f"API错误: {chunk.message}"
                    }
                    return
            
            # 生成结束
            yield {
                "answer_delta": "",
                "finished": True,
                "model": model_to_use
            }
            
        except Exception as e:
            logger.exception(f"流式调用LLM API时发生异常: {str(e)}")
            yield {
                "answer_delta": f"\n\n[系统错误: {str(e)}]",
                "error": True,
                "finished": True,
                "error_message": str(e)
            }
            
    @staticmethod
    def generate_response_static(query: str, context: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """静态方法版本，适用于简单调用"""
        service = LLMService(model_name="qwen-turbo")  # 使用更快的模型
        result = service.generate_response(query, context, conversation_history)
        return result["answer"]