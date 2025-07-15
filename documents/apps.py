from django.apps import AppConfig
from loguru import logger


class DocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'documents'
    
    def ready(self):
        """
        在应用启动时执行初始化操作
        注意：由于Django可能会多次调用ready()方法，
        特别是在开发环境中使用自动重载服务器时，
        我们已在VectorDBService中实现了防止重复加载的机制
        """
        # 导入这里以避免循环导入问题
        from .services.vector_db_service import VectorDBService
        from django.conf import settings
        
        # 获取默认的嵌入模型版本
        default_embedding_model = settings.EMBEDDING_MODEL_VERSION
        
        # 异步预加载默认模型的向量索引
        logger.info(f"Django应用启动，开始预加载FAISS索引(默认模型版本: {default_embedding_model})...")
        VectorDBService.preload_index_async(default_embedding_model)
        logger.info("FAISS索引预加载任务已启动")
