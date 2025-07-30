import os
from celery import Celery

# 设置默认Django settings模块
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartdocs_project.settings')

app = Celery('smartdocs')

# 使用Django的settings配置Celery
app.config_from_object('django.conf:settings', namespace='CELERY')

# 设置Redis作为broker
app.conf.broker_url = f"redis://{os.environ.get('REDIS_HOST', 'localhost')}:{os.environ.get('REDIS_PORT', '6379')}/1"
# 使用DB 1作为消息队列，与Django缓存(DB 0)分开

# 使用solo池模式，避免预分叉带来的内存问题
app.conf.worker_pool = 'solo'

# 内存和任务优化配置
app.conf.update(
    worker_log_format="%(asctime)s [%(levelname)s] [%(processName)s] %(message)s",
    worker_task_log_format="%(asctime)s [%(levelname)s] [%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s",
    # 内存和任务配置
    worker_max_tasks_per_child=10,  # 每个进程最多处理10个任务后重启
    task_time_limit=3600,  # 1小时超时限制
    task_soft_time_limit=3000,  # 50分钟软超时
)

# 自动发现所有app下的tasks.py文件
app.autodiscover_tasks()

# 设置Celery任务状态更新回调
@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')