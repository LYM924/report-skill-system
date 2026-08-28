"""存储工厂"""
from config import settings
from .local import LocalStorage

_storage = None


def get_storage():
    global _storage
    if _storage is None:
        if settings.STORAGE_BACKEND == "minio":
            from .minio import MinioStorage
            _storage = MinioStorage()
        else:
            # 本地存储：base_dir 是项目根目录（文档路径从项目根开始，如 data/knowledge/...）
            _storage = LocalStorage(settings.PROJECT_DIR)
    return _storage