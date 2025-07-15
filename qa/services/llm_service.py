from loguru import logger
from typing import List, Dict, Any
from django.conf import settings
import dashscope
from dashscope.aigc.generation import Generation

# loguru不需要getLogger

class LLMService:
    """大语言模型服务，负责与LLM API交互"""
    
    def __init__(self):
        # 设置DashScope API密钥
        self.api_key = settings.DASHSCOPE_API_KEY
        if not self.api_key:
            logger.warning("DASHSCOPE_API_KEY未设置，LLM服务将无法正常工作")
        else:
            # 配置DashScope客户端
            dashscope.api_key = self.api_key
    
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
                model="qwen-max",  # 可以根据需要选择不同模型
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
                    "error": False
                }
            else:
                logger.error(f"LLM API调用失败: {response.code}, {response.message}")
                return {"answer": f"调用LLM API时出错: {response.message}", "error": True}
                
        except Exception as e:
            logger.exception(f"调用LLM API时发生异常: {str(e)}")
            return {"answer": f"系统错误: {str(e)}", "error": True}
            
    @staticmethod
    def generate_response_static(query: str, context: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """静态方法版本，适用于简单调用"""
        service = LLMService()
        result = service.generate_response(query, context, conversation_history)
        return result["answer"]