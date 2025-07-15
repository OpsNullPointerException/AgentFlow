from loguru import logger
import sys

# 配置loguru
logger.configure(handlers=[
    {"sink": sys.stdout, "level": "INFO"},
    {"sink": "logs/app.log", "rotation": "10 MB", "level": "DEBUG"}
])