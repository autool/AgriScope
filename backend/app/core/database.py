"""异步数据库连接与会话管理。"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

async_engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """为单次 HTTP 请求提供异步数据库会话。

    Args:
        无。

    Returns:
        AsyncGenerator[AsyncSession, None]: 可供 FastAPI 注入的异步会话生成器。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
