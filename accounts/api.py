from ninja import Router, Schema
from typing import List, Optional
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate
from django.db import transaction
import secrets
import string

from .models import UserProfile, ApiKey

# 定义Schema
class UserProfileOut(Schema):
    """用户配置文件输出Schema"""
    language_preference: str
    theme_preference: str
    monthly_quota: int
    used_quota: int
    organization: Optional[str] = None
    department: Optional[str] = None

class UserOut(Schema):
    """用户信息输出Schema"""
    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    profile: UserProfileOut

class UserProfileUpdate(Schema):
    """用户配置文件更新Schema"""
    language_preference: Optional[str] = None
    theme_preference: Optional[str] = None
    organization: Optional[str] = None
    department: Optional[str] = None

class UserUpdate(Schema):
    """用户信息更新Schema"""
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile: Optional[UserProfileUpdate] = None

class ApiKeyOut(Schema):
    """API密钥输出Schema"""
    id: int
    name: str
    key: str  # 注意：通常只在创建时返回完整的key
    is_active: bool
    created_at: str

class ApiKeyIn(Schema):
    """API密钥创建输入Schema"""
    name: str

class RegisterIn(Schema):
    """用户注册输入Schema"""
    username: str
    email: str
    password: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""

class LoginIn(Schema):
    """用户登录输入Schema"""
    username: str
    password: str

class TokenOut(Schema):
    """登录成功后返回的token信息"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

# 创建路由器
router = Router(tags=["accounts"])

# 公开的API端点，不需要认证
public_router = Router(tags=["accounts"])

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

@router.get("/me", response=UserOut)
def get_current_user(request):
    """获取当前登录用户的信息"""
    return request.auth

@router.put("/me", response=UserOut)
def update_current_user(request, data: UserUpdate):
    """更新当前用户信息"""
    user = request.auth
    
    if data.email:
        user.email = data.email
    if data.first_name is not None:
        user.first_name = data.first_name
    if data.last_name is not None:
        user.last_name = data.last_name
    
    user.save()
    
    # 更新用户配置文件
    if data.profile:
        profile = user.profile
        if data.profile.language_preference:
            profile.language_preference = data.profile.language_preference
        if data.profile.theme_preference:
            profile.theme_preference = data.profile.theme_preference
        if data.profile.organization is not None:
            profile.organization = data.profile.organization
        if data.profile.department is not None:
            profile.department = data.profile.department
        profile.save()
    
    return user

@router.get("/api-keys", response=List[ApiKeyOut])
def list_api_keys(request):
    """获取当前用户的所有API密钥"""
    return ApiKey.objects.filter(user=request.auth)

@router.post("/api-keys", response=ApiKeyOut)
def create_api_key(request, data: ApiKeyIn):
    """为当前用户创建新的API密钥"""
    # 生成一个64字符的随机字符串作为API密钥
    alphabet = string.ascii_letters + string.digits
    key = ''.join(secrets.choice(alphabet) for _ in range(64))
    
    api_key = ApiKey.objects.create(
        user=request.auth,
        name=data.name,
        key=key
    )
    
    return api_key

@router.delete("/api-keys/{key_id}")
def delete_api_key(request, key_id: int):
    """删除指定的API密钥"""
    key = get_object_or_404(ApiKey, id=key_id, user=request.auth)
    key.delete()
    return {"success": True}