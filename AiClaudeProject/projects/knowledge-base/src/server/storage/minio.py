"""MinIO 对象存储"""
import io
from .base import StorageBackend
from config import settings


class MinioStorage(StorageBackend):
    def __init__(self):
        from minio import Minio
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False,
        )
        self.bucket = settings.MINIO_BUCKET
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    async def read(self, path: str) -> str:
        resp = self.client.get_object(self.bucket, path)
        return resp.read().decode("utf-8")

    async def write(self, path: str, content: str) -> None:
        data = io.BytesIO(content.encode("utf-8"))
        self.client.put_object(self.bucket, path, data, len(content.encode("utf-8")))

    async def delete(self, path: str) -> None:
        self.client.remove_object(self.bucket, path)

    async def exists(self, path: str) -> bool:
        try:
            self.client.stat_object(self.bucket, path)
            return True
        except Exception:
            return False

    async def list(self, prefix: str = "") -> list[str]:
        objects = self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
        return [obj.object_name for obj in objects if obj.object_name.endswith(".md")]