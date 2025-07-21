from typing import Optional
from loguru import logger
from django.conf import settings

def get_embedding_service(embedding_model_version: Optional[str] = None):
    """
    根据配置获取合适的嵌入服务
    
    Args:
        embedding_model_version: 嵌入模型版本，如果未指定则使用settings中的配置
        
    Returns:
        嵌入服务实例，可以是API版本或本地版本
        
    Raises:
        ValueError: 当配置的嵌入服务类型无效时抛出
    """
    # 获取嵌入服务类型配置
    service_type = getattr(settings, 'EMBEDDING_SERVICE_TYPE', 'api')
    logger.info(f"使用嵌入服务类型: {service_type}")
    
    if service_type.lower() == 'api':
        # 使用API嵌入服务
        from documents.services.embedding_service import EmbeddingService
        logger.info(f"创建API嵌入服务，模型版本: {embedding_model_version or settings.EMBEDDING_MODEL_VERSION}")
        return EmbeddingService(embedding_model_version=embedding_model_version)
        
    elif service_type.lower() == 'local':
        # 使用本地嵌入服务
        try:
            from documents.services.local_embedding_service import LocalEmbeddingService
            logger.info(f"创建本地嵌入服务，模型版本: {embedding_model_version or settings.LOCAL_EMBEDDING_MODEL}")
            return LocalEmbeddingService(embedding_model_version=embedding_model_version)
        except ImportError as e:
            logger.error(f"加载本地嵌入服务失败: {str(e)}，将回退到API服务")
            from documents.services.embedding_service import EmbeddingService
            return EmbeddingService(embedding_model_version=embedding_model_version)
    
    else:
        # 无效的服务类型，抛出异常
        logger.error(f"无效的嵌入服务类型: {service_type}")
        raise ValueError(f"无效的嵌入服务类型: {service_type}，支持的类型为: 'api', 'local'")