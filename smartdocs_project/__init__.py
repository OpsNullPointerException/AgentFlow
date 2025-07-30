from loguru import logger
import sys

# 配置loguru
logger.configure(handlers=[
    {"sink": sys.stdout, "level": "INFO"},
    {"sink": "logs/app.log", "rotation": "10 MB", "level": "DEBUG"}
])

# 确保在Django启动时Celery app被加载
from .celery import app as celery_app

__all__ = ['celery_app']