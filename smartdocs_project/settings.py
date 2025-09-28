"""
Django settings for AgentFlow project.

AgentFlow - 智能代理平台
基于LangChain的多功能AI Agent系统

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

from pathlib import Path
from datetime import timedelta
import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量,强制重新加载
load_dotenv(override=True)


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-$m!b2btq33)l7@6lyhw^vc=x^(@6v9wfo=8@o25=o6@e%-2b!@")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 第三方应用
    "corsheaders",
    # 自定义应用
    "accounts",
    "documents",
    "qa",
    "agents",
]

# 禁用URL末尾斜杠自动添加，以兼容前端API请求
# APPEND_SLASH = False

# Django Ninja 设置
NINJA_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # 添加CORS中间件
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# CORS设置
CORS_ALLOW_ALL_ORIGINS = True  # 开发环境设置，生产环境应该指定域名

ROOT_URLCONF = "smartdocs_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "frontend")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "smartdocs_project.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",  # 使用标准PostgreSQL后端
        "NAME": os.environ.get("DB_NAME", "smartdocs"),
        "USER": os.environ.get("DB_USER", "smartdocs"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "smartdocspass"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": 600,  # 连接持久化时间（秒）
    }
}
print("使用PostgreSQL数据库")


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "zh-hans"

TIME_ZONE = "Asia/Shanghai"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "frontend"),
]
# 媒体文件配置
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# 文件上传配置
MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE", 10 * 1024 * 1024))  # 默认10MB

# 千问API配置
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

# 嵌入服务配置
# 选择使用哪种嵌入服务: 'api'(DashScope API) 或 'local'(本地嵌入模型)
EMBEDDING_SERVICE_TYPE = os.environ.get("EMBEDDING_SERVICE_TYPE", "api")

# API嵌入模型配置（当 EMBEDDING_SERVICE_TYPE='api' 时使用）
EMBEDDING_MODEL_VERSION = os.environ.get("EMBEDDING_MODEL_VERSION", "text-embedding-v4")
EMBEDDING_MODEL_DIMENSIONS = 1024

# 本地嵌入模型配置（当 EMBEDDING_SERVICE_TYPE='local' 时使用）
# 支持的模型及其维度:
# - all-MiniLM-L6-v2: 384维，英文优先，小巧高效
# - all-mpnet-base-v2: 768维，英文优先，效果更好
# - BAAI/bge-small-zh-v1.5: 384维，中文优先
# - BAAI/bge-base-zh-v1.5: 768维，中文优先
# - BAAI/bge-large-zh-v1.5: 1024维，中文优先，最佳质量
# - paraphrase-multilingual-MiniLM-L12-v2: 384维，多语言
LOCAL_EMBEDDING_MODEL = os.environ.get("LOCAL_EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")

# 注意：text-embedding-v4是OpenAI API模型，不是HuggingFace模型
# 确保在使用本地嵌入服务时不使用API模型名称

# 缓存配置 - 优化性能
EMBEDDING_CACHE_ENABLED = os.environ.get("EMBEDDING_CACHE_ENABLED", "True").lower() == "true"
EMBEDDING_CACHE_TIMEOUT = int(os.environ.get("EMBEDDING_CACHE_TIMEOUT", "86400"))  # 24小时

QA_RETRIEVAL_CACHE_ENABLED = os.environ.get("QA_RETRIEVAL_CACHE_ENABLED", "True").lower() == "true"
QA_RETRIEVAL_CACHE_TIMEOUT = int(os.environ.get("QA_RETRIEVAL_CACHE_TIMEOUT", "3600"))  # 1小时

# 向量库配置
VECTOR_STORE_PATH = os.environ.get("VECTOR_STORE_PATH", str(BASE_DIR / "vector_store"))

# 确保向量库目录存在

os.makedirs(VECTOR_STORE_PATH, exist_ok=True)

# Redis配置
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
# REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "smartdocsredis")
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))

# Django缓存配置 - 使用Redis作为缓存后端
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # "PASSWORD": REDIS_PASSWORD,
            "SOCKET_CONNECT_TIMEOUT": 5,  # 连接超时时间(秒)
            "SOCKET_TIMEOUT": 5,  # 读写超时时间(秒)
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",  # 启用zlib压缩
            "IGNORE_EXCEPTIONS": True,  # 忽略Redis连接错误，避免影响网站可用性
        },
        "KEY_PREFIX": "smartdocs",  # 缓存键前缀，避免与其他应用冲突
        "TIMEOUT": 60 * 60 * 24 * 7,  # 默认缓存过期时间(7天)
    }
}

# 使用Redis作为会话后端
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Celery配置
CELERY_RESULT_BACKEND = "django-db"  # 使用数据库存储任务结果
CELERY_BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30分钟超时限制


INSTALLED_APPS += [
    "django_celery_results",
]


# Django Ninja 额外配置
NINJA_PAGINATION_CLASS = "ninja.pagination.LimitOffsetPagination"
NINJA_PAGINATION_PER_PAGE = 20
NINJA_MAX_PER_PAGE_SIZE = 100
NINJA_PAGINATION_MAX_LIMIT = 1000
NINJA_NUM_PROXIES = 0
NINJA_DEFAULT_THROTTLE_RATES = {}
NINJA_FIX_REQUEST_FILES_METHODS = ["PUT", "PATCH"]
