"""数据库连接管理"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import settings

_engine = None
_async_session = None


class Base(DeclarativeBase):
    pass


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=10)
    return _engine


def _get_sessionmaker():
    global _async_session
    if _async_session is None:
        _async_session = async_sessionmaker(_get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _async_session


async def get_db() -> AsyncSession:
    async with _get_sessionmaker()() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """创建所有表"""
    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)