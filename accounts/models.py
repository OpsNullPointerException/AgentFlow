from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    """用户配置文件，扩展Django内置的用户模型"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
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
        return f"{self.user.username}的配置"

    def reset_monthly_quota(self):
        """重置月度配额"""
        self.used_quota = 0
        self.save()

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """当创建新用户时，自动创建对应的用户配置文件"""
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """当保存用户时，同时保存用户配置文件"""
    instance.profile.save()

class ApiKey(models.Model):
    """API密钥模型，用于API访问认证"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_keys')
    key = models.CharField('密钥', max_length=64, unique=True)
    name = models.CharField('名称', max_length=100)
    is_active = models.BooleanField('是否激活', default=True)
    
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    last_used_at = models.DateTimeField('最后使用时间', null=True, blank=True)
    
    class Meta:
        verbose_name = 'API密钥'
        verbose_name_plural = 'API密钥'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.user.username})"
