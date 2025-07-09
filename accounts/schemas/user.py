from ninja import Schema
from typing import Optional
from pydantic import EmailStr, Field


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