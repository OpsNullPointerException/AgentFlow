from django.db import models


class ApiKey(models.Model):
    """API密钥模型，用于API访问认证"""

    # 使用整数字段替代外键
    user_id = models.IntegerField("用户ID")
    key = models.CharField("密钥", max_length=64, unique=True)
    name = models.CharField("名称", max_length=100)
    is_active = models.BooleanField("是否激活", default=True)

    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    last_used_at = models.DateTimeField("最后使用时间", null=True, blank=True)

    class Meta:
        verbose_name = "API密钥"
        verbose_name_plural = "API密钥"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} (用户ID:{self.user_id})"
