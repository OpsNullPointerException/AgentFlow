from ninja import Router

# 创建路由器
router = Router(tags=["accounts"])

# 公开的API端点，不需要认证
public_router = Router(tags=["accounts"])

# 导入控制器
from accounts.controllers.auth import *
from accounts.controllers.user import *
from accounts.controllers.api_key import *

# 导出路由器
__all__ = ['router', 'public_router']