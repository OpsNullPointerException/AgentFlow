from celery import shared_task
from loguru import logger
from documents.services.document_processor import DocumentProcessor
from documents.models import Document
from smartdocs_project.celery_logging import celery_logger


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5分钟后重试
    autoretry_for=(Exception,),  # 自动重试所有异常
    name="documents.process_document",
)
def process_document_task(self, document_id):
    """Celery任务：处理文档并创建索引"""
    # 绑定任务信息到日志
    task_logger = celery_logger.bind(task_id=self.request.id, task_name="process_document")
    task_logger.info(f"开始处理文档 {document_id}")

    try:
        # 更新文档状态为"processing"，添加任务ID
        document = Document.objects.get(id=document_id)
        document.status = "processing"
        document.error_message = f"任务ID: {self.request.id}"
        document.save(update_fields=["status", "error_message"])

        # 处理文档
        processor = DocumentProcessor()
        result = processor.process_document(document_id)

        # 返回处理结果
        return {"document_id": document_id, "success": result, "task_id": self.request.id}
    except Exception as e:
        task_logger.error(f"处理文档 {document_id} 失败: {str(e)}")

        # 尝试更新文档状态
        try:
            document = Document.objects.get(id=document_id)
            document.status = "failed"
            document.error_message = f"处理失败: {str(e)}"
            document.save(update_fields=["status", "error_message"])
        except Exception:
            pass

        # 重新抛出异常以触发重试机制
        raise


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5分钟后重试
    autoretry_for=(Exception,),  # 自动重试所有异常
    name="documents.reprocess_document",
)
def reprocess_document_task(self, document_id, embedding_model_version=None):
    """Celery任务：使用指定的嵌入模型版本重新处理文档"""
    # 绑定任务信息到日志
    task_logger = celery_logger.bind(task_id=self.request.id, task_name="reprocess_document")
    task_logger.info(f"开始重新处理文档 {document_id}, 使用嵌入模型: {embedding_model_version}")

    try:
        # 处理文档
        processor = DocumentProcessor(embedding_model_version=embedding_model_version)
        result = processor.process_document(document_id)

        # 返回处理结果
        return {
            "document_id": document_id,
            "success": result,
            "task_id": self.request.id,
            "embedding_model_version": embedding_model_version,
        }
    except Exception as e:
        task_logger.error(f"重新处理文档 {document_id} 失败: {str(e)}")

        # 尝试更新文档状态
        try:
            document = Document.objects.get(id=document_id)
            document.status = "failed"
            document.error_message = f"处理失败: {str(e)}"
            document.save(update_fields=["status", "error_message"])
        except Exception:
            pass

        # 重新抛出异常以触发重试机制
        raise
