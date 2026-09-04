"""配置管理 — 从环境变量读取，带默认值"""
import os
from pathlib import Path

# 项目根目录（config.py 位于 src/server/ 下）
_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent


def _load_env():
    """启动时加载项目根目录 .env

    规则：.env 中**非空**的值优先（覆盖 shell 继承的环境变量），
    空值跳过（不覆盖继承的有效值）。
    背景：shell 里可能有其他工具遗留的变量（如 CLAUDE_MODEL=glm-5.1）污染服务进程，
    项目自己的 .env 必须能纠正它；同时 .env 中留空的密钥（如 ANTHROPIC_AUTH_TOKEN=）
    不应清掉 shell 注入的有效值。
    """
    env_file = _PROJECT_DIR / ".env"
    if not env_file.exists():
        return
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and (key not in os.environ or val):
                os.environ[key] = val


_load_env()
os.environ["_KB_ENV_LOADED"] = "1"  # 标记 .env 已加载，供 db_repo.py 兜底检测


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

    # Confluence SSO
    CONFLUENCE_BASE_URL: str = os.getenv("CONFLUENCE_BASE_URL", "https://cf.cai-inc.com")
    SSO_ENABLED: bool = os.getenv("SSO_ENABLED", "1").strip() in ("1", "true", "yes")

    # API Key（兼容旧版）
    KB_API_KEY: str = os.getenv("KB_API_KEY", "")

    @property
    def use_postgres(self) -> bool:
        return "postgresql" in self.DATABASE_URL


settings = Settings()