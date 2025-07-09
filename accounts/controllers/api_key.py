from typing import List
from django.shortcuts import get_object_or_404
import secrets
import string

from accounts.controllers import router
from accounts.models import ApiKey
from accounts.schemas.api_key import ApiKeyOut, ApiKeyIn


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