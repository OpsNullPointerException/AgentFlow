from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


class AgentIn(BaseModel):
    """创建Agent的输入Schema"""

    name: str = Field(..., description="代理名称")
    description: Optional[str] = Field("", description="代理描述")
    agent_type: str = Field("react", description="代理类型")
    system_prompt: str = Field("你是一个智能助手，可以使用各种工具来帮助用户完成任务。", description="系统提示词")
    llm_model: str = Field("qwen-turbo", description="LLM模型")
    temperature: float = Field(0.7, description="温度参数", ge=0.0, le=2.0)
    max_tokens: int = Field(2000, description="最大令牌数", gt=0)
    available_tools: List[str] = Field(default_factory=list, description="可用工具列表")
    tool_config: Dict[str, Any] = Field(default_factory=dict, description="工具配置")
    memory_type: str = Field("buffer_window", description="记忆类型")
    memory_config: Dict[str, Any] = Field(default_factory=dict, description="记忆配置")


class AgentUpdateIn(BaseModel):
    """更新Agent的输入Schema"""

    name: Optional[str] = Field(None, description="代理名称")
    description: Optional[str] = Field(None, description="代理描述")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    llm_model: Optional[str] = Field(None, description="LLM模型")
    temperature: Optional[float] = Field(None, description="温度参数", ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, description="最大令牌数", gt=0)
    available_tools: Optional[List[str]] = Field(None, description="可用工具列表")
    tool_config: Optional[Dict[str, Any]] = Field(None, description="工具配置")
    memory_type: Optional[str] = Field(None, description="记忆类型")
    memory_config: Optional[Dict[str, Any]] = Field(None, description="记忆配置")
    status: Optional[str] = Field(None, description="状态")


class AgentOut(BaseModel):
    """Agent输出Schema"""

    id: str = Field(..., description="代理ID")
    name: str = Field(..., description="代理名称")
    description: str = Field(..., description="代理描述")
    agent_type: str = Field(..., description="代理类型")
    system_prompt: str = Field(..., description="系统提示词")
    llm_model: str = Field(..., description="LLM模型")
    temperature: float = Field(..., description="温度参数")
    max_tokens: int = Field(..., description="最大令牌数")
    available_tools: List[str] = Field(..., description="可用工具列表")
    tool_config: Dict[str, Any] = Field(..., description="工具配置")
    memory_type: str = Field(..., description="记忆类型")
    memory_config: Dict[str, Any] = Field(..., description="记忆配置")
    status: str = Field(..., description="状态")
    user_id: int = Field(..., description="创建者ID")
    execution_count: int = Field(..., description="执行次数")
    last_executed_at: Optional[datetime] = Field(None, description="最后执行时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class AgentListOut(BaseModel):
    """Agent列表输出Schema"""

    agents: List[AgentOut] = Field(..., description="代理列表")
    total: int = Field(..., description="总数")


class AgentExecutionIn(BaseModel):
    """Agent执行输入Schema"""

    agent_id: str = Field(..., description="代理ID")
    user_input: str = Field(..., description="用户输入")
    conversation_id: Optional[int] = Field(None, description="对话ID")
    stream: bool = Field(False, description="是否流式输出")


class AgentExecutionOut(BaseModel):
    """Agent执行输出Schema"""

    id: str = Field(..., description="执行ID")
    agent_id: str = Field(..., description="代理ID")
    user_input: str = Field(..., description="用户输入")
    agent_output: str = Field(..., description="代理输出")
    execution_steps: List[Dict[str, Any]] = Field(..., description="执行步骤")
    tools_used: List[str] = Field(..., description="使用的工具")
    status: str = Field(..., description="状态")
    error_message: str = Field(..., description="错误信息")
    execution_time: Optional[float] = Field(None, description="执行时间(秒)")
    token_usage: Dict[str, Any] = Field(..., description="令牌使用量")
    started_at: datetime = Field(..., description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")


class AgentToolOut(BaseModel):
    """Agent工具输出Schema"""

    id: str = Field(..., description="工具ID")
    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    tool_type: str = Field(..., description="工具类型")
    tool_class: str = Field(..., description="工具类名")
    tool_config: Dict[str, Any] = Field(..., description="工具配置")
    is_enabled: bool = Field(..., description="是否启用")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class AgentExecutionStepOut(BaseModel):
    """Agent执行步骤输出Schema"""

    step_type: str = Field(..., description="步骤类型")
    step_name: str = Field(..., description="步骤名称")
    input_data: Dict[str, Any] = Field(..., description="输入数据")
    output_data: Dict[str, Any] = Field(..., description="输出数据")
    timestamp: datetime = Field(..., description="时间戳")
    duration: float = Field(..., description="持续时间(秒)")


class AgentStreamResponse(BaseModel):
    """Agent流式响应Schema"""

    type: str = Field(..., description="响应类型: thinking, action, observation, final")
    content: str = Field(..., description="响应内容")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
