from ninja import Router

router = Router(tags=["智能代理"])

# 导入所有控制器 - 注意顺序：具体路径优先于变量路径
from . import execution, agent

__all__ = ["router"]