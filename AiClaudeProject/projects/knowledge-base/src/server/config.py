"""配置管理 — 从环境变量读取，带默认值"""
import os
from pathlib import Path


class Settings:
    # 数据库
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://kb_user:kb_pass@localhost:5432/knowledge_base"
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg2://zcy1@localhost:5432/knowledge_base"
    )

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # MinIO
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "knowledge-base")

    # JWT
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-secret-key")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

    # 项目路径
    PROJECT_DIR: Path = Path(__file__).resolve().parent.parent.parent
    RUNTIME_DIR: Path = PROJECT_DIR / "runtime"

    # 存储
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local")
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(PROJECT_DIR / "data")))

    # Claude API
    ANTHROPIC_AUTH_TOKEN: str = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
    ANTHROPIC_BASE_URL: str = os.getenv("ANTHROPIC_BASE_URL", "")

    # API Key（兼容旧版）
    KB_API_KEY: str = os.getenv("KB_API_KEY", "")

    @property
    def use_postgres(self) -> bool:
        return "postgresql" in self.DATABASE_URL


settings = Settings()