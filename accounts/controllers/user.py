from accounts.controllers import router
from accounts.schemas.user import UserOut, UserUpdate


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