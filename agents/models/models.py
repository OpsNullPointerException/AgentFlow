from django.db import models
from django.contrib.postgres.fields import JSONField
import uuid


class Agent(models.Model):
    """智能代理模型 - 基于LangChain Agent"""

    AGENT_TYPES = (
        ("react", "ReAct代理"),
        ("openai_functions", "OpenAI函数代理"),
        ("structured_chat", "结构化聊天代理"),
        ("conversational", "对话代理"),
        ("zero_shot", "零样本代理"),
    )

    STATUS_CHOICES = (
        ("active", "激活"),
        ("inactive", "停用"),
        ("error", "错误"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("代理名称", max_length=255)
    description = models.TextField("代理描述", blank=True)
    agent_type = models.CharField("代理类型", max_length=50, choices=AGENT_TYPES, default="react")

    # Agent配置
    system_prompt = models.TextField("系统提示词", default="你是一个智能助手，可以使用各种工具来帮助用户完成任务。")
    llm_model = models.CharField("LLM模型", max_length=100, default="qwen-turbo")
    temperature = models.FloatField("温度参数", default=0.7)
    max_tokens = models.IntegerField("最大令牌数", default=2000)

    # 工具配置
    available_tools = models.JSONField("可用工具列表", default=list, blank=True)
    tool_config = models.JSONField("工具配置", default=dict, blank=True)

    # 记忆配置
    memory_type = models.CharField("记忆类型", max_length=50, default="buffer_window")
    memory_config = models.JSONField("记忆配置", default=dict, blank=True)

    # 状态和元数据
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default="active")
    user_id = models.IntegerField("创建者ID")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    # 使用统计
    execution_count = models.IntegerField("执行次数", default=0)
    last_executed_at = models.DateTimeField("最后执行时间", null=True, blank=True)

    class Meta:
        verbose_name = "智能代理"
        verbose_name_plural = "智能代理"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.name} ({self.get_agent_type_display()})"


class AgentTool(models.Model):
    """代理工具模型"""

    TOOL_TYPES = (
        ("document_search", "文档搜索"),
        ("web_search", "网络搜索"),
        ("calculator", "计算器"),
        ("python_repl", "Python执行器"),
        ("sql_query", "SQL查询"),
        ("api_call", "API调用"),
        ("custom", "自定义工具"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("工具名称", max_length=255)
    description = models.TextField("工具描述")
    tool_type = models.CharField("工具类型", max_length=50, choices=TOOL_TYPES)

    # 工具实现
    tool_class = models.CharField("工具类名", max_length=255)
    tool_config = models.JSONField("工具配置", default=dict, blank=True)

    # 工具元数据
    is_enabled = models.BooleanField("是否启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "代理工具"
        verbose_name_plural = "代理工具"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_tool_type_display()})"


class AgentExecution(models.Model):
    """代理执行记录"""

    STATUS_CHOICES = (
        ("running", "运行中"),
        ("completed", "已完成"),
        ("failed", "失败"),
        ("cancelled", "已取消"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_id = models.UUIDField("代理ID")
    conversation_id = models.IntegerField("对话ID", null=True, blank=True)
    user_id = models.IntegerField("用户ID")

    # 执行内容
    user_input = models.TextField("用户输入")
    agent_output = models.TextField("代理输出", blank=True)

    # 执行过程
    execution_steps = models.JSONField("执行步骤", default=list, blank=True)
    tools_used = models.JSONField("使用的工具", default=list, blank=True)

    # 执行状态
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default="running")
    error_message = models.TextField("错误信息", blank=True)

    # 性能指标
    execution_time = models.FloatField("执行时间(秒)", null=True, blank=True)
    token_usage = models.JSONField("令牌使用量", default=dict, blank=True)

    # 时间戳
    started_at = models.DateTimeField("开始时间", auto_now_add=True)
    completed_at = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        verbose_name = "代理执行记录"
        verbose_name_plural = "代理执行记录"
        ordering = ["-started_at"]

    def __str__(self):
        return f"执行 {self.agent_id} - {self.status}"


class AgentMemory(models.Model):
    """代理记忆存储"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_id = models.UUIDField("代理ID")
    conversation_id = models.IntegerField("对话ID", null=True, blank=True)
    user_id = models.IntegerField("用户ID")

    # 记忆内容
    memory_key = models.CharField("记忆键", max_length=255)
    memory_data = models.JSONField("记忆数据", default=dict)

    # 元数据
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    expires_at = models.DateTimeField("过期时间", null=True, blank=True)

    class Meta:
        verbose_name = "代理记忆"
        verbose_name_plural = "代理记忆"
        unique_together = [["agent_id", "conversation_id", "memory_key"]]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"记忆 {self.agent_id} - {self.memory_key}"
