from django.db import models


class UserProfile(models.Model):
    """用户配置文件，扩展Django内置的用户模型"""
    # 使用整数字段替代OneToOneField
    user_id = models.IntegerField('用户ID', unique=True)
    
    # 用户偏好设置
    language_preference = models.CharField('语言偏好', max_length=10, default='zh-cn')
    theme_preference = models.CharField('主题偏好', max_length=10, default='light')
    
    # API使用配额
    monthly_quota = models.IntegerField('月度配额', default=100)  # 每月可使用的问答次数
    used_quota = models.IntegerField('已使用配额', default=0)     # 当前已使用的次数
    
    # 组织信息（可选）
    organization = models.CharField('组织', max_length=100, blank=True, null=True)
    department = models.CharField('部门', max_length=100, blank=True, null=True)
    
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    
    class Meta:
        verbose_name = '用户配置'
        verbose_name_plural = '用户配置'
    
    def __str__(self):
        return f"用户ID:{self.user_id}的配置"

    def reset_monthly_quota(self):
        """重置月度配额"""
        self.used_quota = 0
        self.save()
