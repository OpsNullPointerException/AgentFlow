from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.contrib.auth.models import User

from .models import UserProfile, ApiKey


# 内联显示用户配置
# 不能再使用内联显示，因为没有外键关联
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user_id", "language_preference", "theme_preference", "monthly_quota", "used_quota")
    list_filter = ("language_preference", "theme_preference")
    search_fields = ("user_id",)


# 由于没有外键关系，不再需要扩展用户管理界面
# 直接注册UserProfile
admin.site.register(UserProfile, UserProfileAdmin)


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "user_id", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active",)
    search_fields = ("name", "user_id")
    readonly_fields = ("key",)  # API密钥只读，不可在管理界面修改
