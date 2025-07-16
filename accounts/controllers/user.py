from accounts.controllers import router
from accounts.schemas.user import UserOut, UserUpdate


@router.get("/me", response=UserOut)
def get_current_user(request):
    """获取当前登录用户的信息"""
    user = request.auth
    
    # 确保用户有profile对象
    from accounts.models import UserProfile
    
    # 直接尝试获取或创建profile - 使用user_id而不是user
    profile, created = UserProfile.objects.get_or_create(
        user_id=user.id,
        defaults={
            'language_preference': 'zh-cn',
            'theme_preference': 'light',
            'monthly_quota': 100,
            'used_quota': 0
        }
    )
    
    # 手动构造响应对象，避免序列化问题
    response = {
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
            "department": profile.department
        }
    }
    
    return response


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
    
    # 获取或创建用户配置文件
    from accounts.models import UserProfile
    profile, created = UserProfile.objects.get_or_create(
        user_id=user.id,
        defaults={
            'language_preference': 'zh-cn',
            'theme_preference': 'light',
            'monthly_quota': 100,
            'used_quota': 0
        }
    )
    
    # 更新用户配置文件
    if data.profile:
        if data.profile.language_preference:
            profile.language_preference = data.profile.language_preference
        if data.profile.theme_preference:
            profile.theme_preference = data.profile.theme_preference
        if data.profile.organization is not None:
            profile.organization = data.profile.organization
        if data.profile.department is not None:
            profile.department = data.profile.department
        profile.save()
    
    # 手动构造响应对象，避免序列化问题
    response = {
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
            "department": profile.department
        }
    }
    
    return response