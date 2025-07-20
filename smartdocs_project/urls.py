"""
URL configuration for smartdocs_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from typing import Optional
from django.contrib import admin
from django.urls import path, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from ninja import NinjaAPI
from ninja.security import HttpBearer
from django.contrib.auth.models import User
import jwt
from datetime import datetime, timedelta
from loguru import logger
from accounts.controllers import router as accounts_router, public_router as accounts_public_router
from documents.api import router as documents_router
from qa.api import router as qa_router


class JWTAuth(HttpBearer):
    def authenticate(self, request, token) -> Optional[User]:
        # 在实际应用中，应该验证JWT并返回用户对象
        # 这里为了演示，我们做一个简化的验证
        try:
            # 实际应用中应使用SECRET_KEY和适当的算法
            # payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            # user_id = payload.get("user_id")
            # return User.objects.get(id=user_id)

            # 简化版，仅用于演示
            if token == "mock_access_token":
                return User.objects.first()  # 返回第一个用户作为演示
            return None
        except Exception as e:
            logger.error(f"JWT验证失败: {e}")
            return None


# 创建API实例
api = NinjaAPI(
    title="SmartDocs API", version="1.0.0", description="智能文档问答平台API", auth=JWTAuth()
)

# 注册需要认证的路由器
api.add_router("/accounts/", accounts_router)
api.add_router("/documents/", documents_router)
api.add_router("/qa/", qa_router)

# 创建不需要认证的公开API
public_api = NinjaAPI(
    title="SmartDocs Public API",
    version="1.0.0",
    description="智能文档问答平台公开API",
    auth=None,
    urls_namespace="public_api",
)

# 注册公开路由器
public_api.add_router("/accounts/", accounts_public_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("public-api/", public_api.urls, name="public_api"),
    # 将前端静态文件的index.html作为默认页面
    # 这个路由必须放在最后，作为通配符路由
    re_path(
        r"^(?!admin/|api/|public-api/|static/|media/).*",
        TemplateView.as_view(template_name="index.html"),
    ),
]

# 添加媒体文件的服务
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
