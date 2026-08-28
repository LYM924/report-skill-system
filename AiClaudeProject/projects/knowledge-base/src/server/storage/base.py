"""存储后端抽象接口"""
from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    async def read(self, path: str) -> str:
        """读取文档内容"""
        ...

    @abstractmethod
    async def write(self, path: str, content: str) -> None:
        """写入文档"""
        ...

    @abstractmethod
    async def delete(self, path: str) -> None:
        """删除文档"""
        ...

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """检查文档是否存在"""
        ...

    @abstractmethod
    async def list(self, prefix: str = "") -> list[str]:
        """列出文档路径"""
        ...