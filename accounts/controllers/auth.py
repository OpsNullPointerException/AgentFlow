from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.db import transaction

from accounts.controllers import public_router
from accounts.schemas.user import RegisterIn, LoginIn, UserOut, TokenOut


@public_router.post("/register", response=UserOut)
def register(request, data: RegisterIn):
    """注册新用户"""
    with transaction.atomic():
        user = User.objects.create_user(
            username=data.username,
            email=data.email,
            password=data.password,
            first_name=data.first_name,
            last_name=data.last_name
        )
    return user


@public_router.post("/login", response=TokenOut)
def login(request, data: LoginIn):
    """用户登录"""
    user = authenticate(username=data.username, password=data.password)
    if user is None:
        return {"detail": "无效的用户名或密码"}, 401
    
    # 生成token（实际应用中应该使用JWT库）
    # 这里仅用于示例，实际应用中请使用正确的JWT生成方法
    access_token = "mock_access_token"  # 实际应用中生成真实的JWT
    refresh_token = "mock_refresh_token"
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token
    }