from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.db import transaction
from typing import Optional
from loguru import logger

from accounts.controllers import public_router
from accounts.schemas.user import RegisterIn, LoginIn, UserOut, TokenOut


def get_user_from_token(token: str) -> Optional[User]:
    """
    从令牌中获取用户（简化版，仅用于演示）

    Args:
        token: 认证令牌

    Returns:
        如果令牌有效，返回User对象；否则返回None
    """
    try:
        # 简化版，仅用于演示
        if token == "mock_access_token":
            return User.objects.first()  # 返回第一个用户作为演示
        return None
    except Exception as e:
        logger.error(f"JWT验证失败: {e}")
        return None


@public_router.post("/register", response={200: UserOut, 400: dict})
def register(request, data: RegisterIn):
    """注册新用户"""
    from accounts.models.user_profile import UserProfile

    # 检查用户名是否已存在
    if User.objects.filter(username=data.username).exists():
        return 400, {"detail": "用户名已存在"}

    # 检查邮箱是否已存在
    if User.objects.filter(email=data.email).exists():
        return 400, {"detail": "邮箱已存在"}

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=data.username,
                email=data.email,
                password=data.password,
                first_name=data.first_name,
                last_name=data.last_name,
            )
            # 创建用户配置文件
            profile = UserProfile.objects.create(
                user_id=user.id, language_preference="zh-cn", theme_preference="light", monthly_quota=100, used_quota=0
            )

        # 构造返回数据，按照UserOut schema格式
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "profile": {
                "language_preference": profile.language_preference,
                "theme_preference": profile.theme_preference,
                "monthly_quota": profile.monthly_quota,
                "used_quota": profile.used_quota,
                "organization": profile.organization,
                "department": profile.department,
            },
        }
    except Exception as e:
        logger.error(f"用户注册失败: {str(e)}")
        return 400, {"detail": "注册失败，请稍后重试"}


@public_router.post("/login", response={200: TokenOut, 401: dict})
def login(request, data: LoginIn):
    """用户登录"""
    user = authenticate(username=data.username, password=data.password)
    if user is None:
        return 401, {"detail": "无效的用户名或密码"}

    # 生成token（实际应用中应该使用JWT库）
    # 这里仅用于示例，实际应用中请使用正确的JWT生成方法
    access_token = "mock_access_token"  # 实际应用中生成真实的JWT
    refresh_token = "mock_refresh_token"

    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}
