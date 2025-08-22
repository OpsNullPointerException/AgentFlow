from ninja import Router

# 创建路由器
router = Router(tags=["qa"])

# 导入控制器
# 导入顺序决定了路由的注册顺序
from qa.controllers.conversation import *
from qa.controllers.retrieval import *

# 导出路由器
__all__ = ["router"]
