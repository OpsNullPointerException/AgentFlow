from typing import List
from django.http import HttpRequest, StreamingHttpResponse
from django.shortcuts import get_object_or_404

from agents.controllers import router
from agents.schemas.agent import (
    AgentExecutionIn,
    AgentExecutionOut
)
from agents.services.agent_service import AgentService
from agents.models import AgentExecution


agent_service = AgentService()


@router.post("/execute", response=AgentExecutionOut, summary="执行智能代理")
def execute_agent(request: HttpRequest, data: AgentExecutionIn):
    """
    执行智能代理任务
    
    Agent会根据用户输入和可用工具，自动制定执行计划并完成任务。
    支持的工具包括：文档搜索、计算器、Python执行器等。
    """
    # 获取用户ID（在实际应用中从JWT token获取）
    user_id = 1  # 临时硬编码
    
    result = agent_service.execute_agent(
        agent_id=data.agent_id,
        user_input=data.user_input,
        user_id=user_id,
        conversation_id=data.conversation_id
    )
    
    return result


@router.get("/{agent_id}/executions", response=List[AgentExecutionOut], summary="获取执行历史")
def get_execution_history(request: HttpRequest, agent_id: str, limit: int = 50):
    """获取指定Agent的执行历史记录"""
    user_id = 1  # 临时硬编码
    
    executions = agent_service.get_execution_history(agent_id, user_id, limit)
    
    result = []
    for execution in executions:
        result.append(AgentExecutionOut(
            id=str(execution.id),
            agent_id=str(execution.agent_id),
            user_input=execution.user_input,
            agent_output=execution.agent_output,
            execution_steps=execution.execution_steps,
            tools_used=execution.tools_used,
            status=execution.status,
            error_message=execution.error_message,
            execution_time=execution.execution_time,
            token_usage=execution.token_usage,
            started_at=execution.started_at,
            completed_at=execution.completed_at
        ))
    
    return result


@router.get("/executions/{execution_id}", response=AgentExecutionOut, summary="获取执行详情")
def get_execution_detail(request: HttpRequest, execution_id: str):
    """获取指定执行记录的详细信息"""
    user_id = 1  # 临时硬编码
    
    execution = get_object_or_404(
        AgentExecution,
        id=execution_id,
        user_id=user_id
    )
    
    return AgentExecutionOut(
        id=str(execution.id),
        agent_id=str(execution.agent_id),
        user_input=execution.user_input,
        agent_output=execution.agent_output,
        execution_steps=execution.execution_steps,
        tools_used=execution.tools_used,
        status=execution.status,
        error_message=execution.error_message,
        execution_time=execution.execution_time,
        token_usage=execution.token_usage,
        started_at=execution.started_at,
        completed_at=execution.completed_at
    )


@router.get("/{agent_id}/stats", summary="获取代理统计信息")
def get_agent_stats(request: HttpRequest, agent_id: str):
    """获取Agent的统计信息"""
    user_id = 1  # 临时硬编码
    
    # 获取Agent
    agent = agent_service.get_agent(agent_id, user_id)
    
    # 获取执行统计
    executions = AgentExecution.objects.filter(
        agent_id=agent_id,
        user_id=user_id
    )
    
    # 计算统计数据
    total_executions = executions.count()
    successful_executions = executions.filter(status='completed').count()
    failed_executions = executions.filter(status='failed').count()
    
    # 计算平均执行时间
    completed_executions = executions.filter(
        status='completed',
        execution_time__isnull=False
    )
    avg_execution_time = 0
    if completed_executions.exists():
        total_time = sum([e.execution_time for e in completed_executions if e.execution_time])
        avg_execution_time = total_time / completed_executions.count()
    
    # 最常用工具统计
    tool_usage = {}
    for execution in executions:
        for tool in execution.tools_used:
            tool_usage[tool] = tool_usage.get(tool, 0) + 1
    
    most_used_tools = sorted(tool_usage.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        "agent_id": agent_id,
        "agent_name": agent.name,
        "total_executions": total_executions,
        "successful_executions": successful_executions,
        "failed_executions": failed_executions,
        "success_rate": successful_executions / total_executions if total_executions > 0 else 0,
        "avg_execution_time": round(avg_execution_time, 2),
        "most_used_tools": [{"tool": tool, "count": count} for tool, count in most_used_tools],
        "last_executed_at": agent.last_executed_at,
        "created_at": agent.created_at
    }


@router.delete("/executions/{execution_id}", summary="删除执行记录")
def delete_execution(request: HttpRequest, execution_id: str):
    """删除指定的执行记录"""
    user_id = 1  # 临时硬编码
    
    execution = get_object_or_404(
        AgentExecution,
        id=execution_id,
        user_id=user_id
    )
    
    execution.delete()
    
    return {"message": "执行记录删除成功"}


@router.post("/{agent_id}/reset", summary="重置代理状态")
def reset_agent(request: HttpRequest, agent_id: str):
    """重置Agent的状态和统计信息"""
    user_id = 1  # 临时硬编码
    
    # 获取Agent
    agent = agent_service.get_agent(agent_id, user_id)
    
    # 重置统计信息
    agent.execution_count = 0
    agent.last_executed_at = None
    agent.save()
    
    # 可选：删除所有执行历史
    # AgentExecution.objects.filter(agent_id=agent_id, user_id=user_id).delete()
    
    return {"message": "代理状态重置成功"}