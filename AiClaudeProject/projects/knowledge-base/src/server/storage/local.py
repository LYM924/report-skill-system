"""本地文件系统存储"""
from pathlib import Path
from .base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    def _full_path(self, path: str) -> Path:
        return self.base_dir / path

    async def read(self, path: str) -> str:
        return self._full_path(path).read_text(encoding="utf-8")

    async def write(self, path: str, content: str) -> None:
        fp = self._full_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")

    async def delete(self, path: str) -> None:
        fp = self._full_path(path)
        if fp.exists():
            fp.unlink()

    async def exists(self, path: str) -> bool:
        return self._full_path(path).exists()

    async def list(self, prefix: str = "") -> list[str]:
        base = self._full_path(prefix)
        if not base.exists():
            return []
        return [str(p.relative_to(self.base_dir)) for p in base.rglob("*.md")]