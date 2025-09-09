from typing import List
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from agents.controllers import router
from agents.schemas.agent import (
    AgentIn,
    AgentOut,
    AgentUpdateIn,
    AgentListOut,
    AgentToolOut
)
from agents.services.agent_service import AgentService
from agents.services.tools import ToolRegistry
from agents.models import Agent, AgentTool


agent_service = AgentService()


@router.post("/", response=AgentOut, summary="创建智能代理")
def create_agent(request: HttpRequest, data: AgentIn):
    """
    创建新的智能代理
    
    支持多种代理类型：
    - react: ReAct代理，适合复杂推理任务
    - openai_functions: OpenAI函数代理，支持函数调用
    - structured_chat: 结构化聊天代理
    - conversational: 对话代理
    """
    # 获取用户ID（在实际应用中从JWT token获取）
    user_id = 1  # 临时硬编码
    
    agent = agent_service.create_agent(data.model_dump(), user_id)
    
    return AgentOut(
        id=str(agent.id),
        name=agent.name,
        description=agent.description,
        agent_type=agent.agent_type,
        system_prompt=agent.system_prompt,
        llm_model=agent.llm_model,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        available_tools=agent.available_tools,
        tool_config=agent.tool_config,
        memory_type=agent.memory_type,
        memory_config=agent.memory_config,
        status=agent.status,
        user_id=agent.user_id,
        execution_count=agent.execution_count,
        last_executed_at=agent.last_executed_at,
        created_at=agent.created_at,
        updated_at=agent.updated_at
    )


@router.get("/", response=AgentListOut, summary="获取代理列表")
def list_agents(request: HttpRequest):
    """获取用户的智能代理列表"""
    user_id = 1  # 临时硬编码
    
    agents = agent_service.list_agents(user_id)
    
    agent_list = []
    for agent in agents:
        agent_list.append(AgentOut(
            id=str(agent.id),
            name=agent.name,
            description=agent.description,
            agent_type=agent.agent_type,
            system_prompt=agent.system_prompt,
            llm_model=agent.llm_model,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            available_tools=agent.available_tools,
            tool_config=agent.tool_config,
            memory_type=agent.memory_type,
            memory_config=agent.memory_config,
            status=agent.status,
            user_id=agent.user_id,
            execution_count=agent.execution_count,
            last_executed_at=agent.last_executed_at,
            created_at=agent.created_at,
            updated_at=agent.updated_at
        ))
    
    return AgentListOut(
        agents=agent_list,
        total=len(agent_list)
    )


@router.get("/{agent_id}", response=AgentOut, summary="获取代理详情")
def get_agent(request: HttpRequest, agent_id: str):
    """获取指定智能代理的详细信息"""
    user_id = 1  # 临时硬编码
    
    agent = agent_service.get_agent(agent_id, user_id)
    
    return AgentOut(
        id=str(agent.id),
        name=agent.name,
        description=agent.description,
        agent_type=agent.agent_type,
        system_prompt=agent.system_prompt,
        llm_model=agent.llm_model,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        available_tools=agent.available_tools,
        tool_config=agent.tool_config,
        memory_type=agent.memory_type,
        memory_config=agent.memory_config,
        status=agent.status,
        user_id=agent.user_id,
        execution_count=agent.execution_count,
        last_executed_at=agent.last_executed_at,
        created_at=agent.created_at,
        updated_at=agent.updated_at
    )


@router.put("/{agent_id}", response=AgentOut, summary="更新代理")
def update_agent(request: HttpRequest, agent_id: str, data: AgentUpdateIn):
    """更新智能代理配置"""
    user_id = 1  # 临时硬编码
    
    # 过滤掉None值
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    
    agent = agent_service.update_agent(agent_id, update_data, user_id)
    
    return AgentOut(
        id=str(agent.id),
        name=agent.name,
        description=agent.description,
        agent_type=agent.agent_type,
        system_prompt=agent.system_prompt,
        llm_model=agent.llm_model,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        available_tools=agent.available_tools,
        tool_config=agent.tool_config,
        memory_type=agent.memory_type,
        memory_config=agent.memory_config,
        status=agent.status,
        user_id=agent.user_id,
        execution_count=agent.execution_count,
        last_executed_at=agent.last_executed_at,
        created_at=agent.created_at,
        updated_at=agent.updated_at
    )


@router.delete("/{agent_id}", summary="删除代理")
def delete_agent(request: HttpRequest, agent_id: str):
    """删除智能代理"""
    user_id = 1  # 临时硬编码
    
    agent_service.delete_agent(agent_id, user_id)
    
    return {"message": "代理删除成功"}


@router.get("/tools", response=List[AgentToolOut], summary="获取可用工具")
def list_available_tools(request: HttpRequest):
    """获取系统中所有可用的工具"""
    tools = AgentTool.objects.filter(is_enabled=True).order_by('name')
    
    tool_list = []
    for tool in tools:
        tool_list.append(AgentToolOut(
            id=str(tool.id),
            name=tool.name,
            description=tool.description,
            tool_type=tool.tool_type,
            tool_class=tool.tool_class,
            tool_config=tool.tool_config,
            is_enabled=tool.is_enabled,
            created_at=tool.created_at,
            updated_at=tool.updated_at
        ))
    
    return tool_list


@router.get("/tool-registry", summary="获取工具注册表")
def get_tool_registry(request: HttpRequest):
    """获取工具注册表中的所有可用工具"""
    available_tools = ToolRegistry.get_available_tools()
    
    tools_info = []
    for tool_name in available_tools:
        tool_instance = ToolRegistry.get_tool(tool_name)
        if tool_instance:
            tools_info.append({
                "name": tool_instance.name,
                "description": tool_instance.description,
                "tool_type": tool_name
            })
    
    return {
        "tools": tools_info,
        "total": len(tools_info)
    }