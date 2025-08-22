import os
import time
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from loguru import logger
import redis

from documents.models import Document
from documents.services.vector_db_service import VectorDBService
from documents.services.document_processor import DocumentProcessor


class Command(BaseCommand):
    help = "重建向量索引，包括删除旧索引和可选地重新索引所有文档"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reindex",
            action="store_true",
            help="删除索引后立即重新索引所有文档",
        )
        parser.add_argument(
            "--model", type=str, default=None, help="指定重新索引时使用的嵌入模型，例如 BAAI/bge-small-zh-v1.5"
        )

    def handle(self, *args, **options):
        reindex = options["reindex"]
        model_version = options["model"]

        self.stdout.write(self.style.WARNING("=== 开始重建向量索引 ==="))

        # 获取向量索引文件路径
        vector_store_path = settings.VECTOR_STORE_PATH
        index_file = os.path.join(vector_store_path, "faiss_index.bin")
        mapping_file = os.path.join(vector_store_path, "chunk_mapping.pkl")

        # 步骤1: 删除索引文件
        self._delete_index_files(index_file, mapping_file)

        # 步骤2: 清除Redis缓存
        self._clear_redis_cache()

        # 步骤3: 重新索引所有文档 (如果指定了--reindex选项)
        if reindex:
            self._reindex_all_documents(model_version)
        else:
            self.stdout.write(
                self.style.WARNING("索引已清除，但未重新索引文档。若要自动重新索引所有文档，请使用 --reindex 选项。")
            )

        self.stdout.write(self.style.SUCCESS("=== 向量索引重建操作完成 ==="))

    def _delete_index_files(self, index_file, mapping_file):
        """删除索引文件"""
        self.stdout.write("正在删除索引文件...")

        files_deleted = 0
        if os.path.exists(index_file):
            os.remove(index_file)
            self.stdout.write(f"  ✓ 已删除索引文件: {index_file}")
            files_deleted += 1
        else:
            self.stdout.write(f"  - 索引文件不存在: {index_file}")

        if os.path.exists(mapping_file):
            os.remove(mapping_file)
            self.stdout.write(f"  ✓ 已删除映射文件: {mapping_file}")
            files_deleted += 1
        else:
            self.stdout.write(f"  - 映射文件不存在: {mapping_file}")

        if files_deleted > 0:
            self.stdout.write(self.style.SUCCESS(f"成功删除了 {files_deleted} 个索引相关文件"))
        else:
            self.stdout.write(self.style.WARNING("未找到需要删除的索引文件"))

    def _clear_redis_cache(self):
        """清除Redis中的索引相关缓存"""
        self.stdout.write("正在清除Redis缓存...")

        try:
            r = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD if hasattr(settings, "REDIS_PASSWORD") else None,
            )

            # 清除索引更新标记
            pattern_update = "smartdocs:faiss:updated:*"
            keys_update = r.keys(pattern_update)
            if keys_update:
                r.delete(*keys_update)
                self.stdout.write(f"  ✓ 已删除 {len(keys_update)} 个索引更新标记")
            else:
                self.stdout.write("  - 未找到索引更新标记")

            # 清除索引元数据
            pattern_meta = "smartdocs:faiss:meta:*"
            keys_meta = r.keys(pattern_meta)
            if keys_meta:
                r.delete(*keys_meta)
                self.stdout.write(f"  ✓ 已删除 {len(keys_meta)} 个索引元数据")
            else:
                self.stdout.write("  - 未找到索引元数据")

            # 清除向量搜索缓存
            pattern_search = "smartdocs:cache:vector_search:*"
            keys_search = r.keys(pattern_search)
            if keys_search:
                r.delete(*keys_search)
                self.stdout.write(f"  ✓ 已删除 {len(keys_search)} 个向量搜索缓存")
            else:
                self.stdout.write("  - 未找到向量搜索缓存")

            total_keys = len(keys_update) + len(keys_meta) + len(keys_search)
            self.stdout.write(self.style.SUCCESS(f"成功清除了 {total_keys} 个Redis缓存键"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"清除Redis缓存失败: {str(e)}"))

    def _reindex_all_documents(self, model_version):
        """重新索引所有文档"""
        self.stdout.write("正在重新索引所有文档...")

        # 获取所有文档
        documents = Document.objects.all()
        total_count = documents.count()

        if total_count == 0:
            self.stdout.write(self.style.WARNING("没有找到需要索引的文档"))
            return

        self.stdout.write(f"找到 {total_count} 个文档需要重新索引")

        # 创建文档处理器
        processor = DocumentProcessor(embedding_model_version=model_version)

        # 重新索引每个文档
        success_count = 0
        error_count = 0

        for index, document in enumerate(documents, 1):
            self.stdout.write(f"[{index}/{total_count}] 正在处理: {document.title} (ID: {document.id})...")

            try:
                # 更新文档状态
                document.status = "pending"
                document.error_message = ""
                if model_version:
                    document.embedding_model_version = model_version
                document.save()

                # 处理文档
                processor.process_document(document.id)
                success_count += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ 成功重新索引文档 {document.id}"))

            except Exception as e:
                error_count += 1
                error_msg = str(e)
                self.stdout.write(self.style.ERROR(f"  ✗ 处理文档 {document.id} 失败: {error_msg}"))

                # 更新文档状态
                document.status = "failed"
                document.error_message = error_msg[:255]  # 限制错误消息长度
                document.save()

            # 等待一小段时间，避免系统负载过高
            time.sleep(0.2)

        # 输出统计信息
        self.stdout.write("=" * 50)
        self.stdout.write(f"总计处理了 {total_count} 个文档")
        self.stdout.write(self.style.SUCCESS(f"成功: {success_count}"))

        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"失败: {error_count}"))
