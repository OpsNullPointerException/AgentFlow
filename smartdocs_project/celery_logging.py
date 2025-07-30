import os
from loguru import logger

# Celery日志路径
CELERY_LOG_FILE = os.path.join("logs", "celery.log")

# 确保日志目录存在
os.makedirs(os.path.dirname(CELERY_LOG_FILE), exist_ok=True)

# 配置Celery标准日志与Loguru集成
class CeleryLoggerAdapter:
    def __call__(self, record):
        # 修改日志记录，添加Celery特定信息
        if hasattr(record["extra"], "task_id"):
            record["extra"]["task_info"] = f"[{record['extra'].get('task_name', 'Unknown')}({record['extra']['task_id']})]"
        else:
            record["extra"]["task_info"] = ""
        return record

# 添加Celery专用日志配置
logger.configure(
    handlers=[
        # 保持现有的控制台输出
        {"sink": os.sys.stdout, "level": "INFO", "format": "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level}</level> | {extra[task_info]} <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"},
        
        # Celery专用日志文件
        {"sink": CELERY_LOG_FILE, "rotation": "10 MB", "level": "INFO", "format": "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {extra[task_info]} {name}:{function}:{line} - {message}"},
    ],
    patcher=CeleryLoggerAdapter()
)

# 获取Celery日志器
celery_logger = logger.bind(task_id=None, task_name=None)