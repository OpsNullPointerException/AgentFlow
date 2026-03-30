from django.apps import AppConfig
from loguru import logger


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "documents"

    def ready(self):
        """
        在应用启动时执行初始化操作
        """
        # 导入这里以避免循环导入问题
        from .services.vector_db_service import VectorDBService
        from django.conf import settings

        # 获取默认的嵌入模型版本
        default_embedding_model = settings.EMBEDDING_MODEL_VERSION

        # 初始化pgvector向量服务（pgvector使用PostgreSQL存储，无需预加载）
        logger.info(f"Django应用启动，初始化pgvector向量服务(默认模型版本: {default_embedding_model})...")
        VectorDBService.get_instance(default_embedding_model)
        logger.info("pgvector向量服务已初始化")
