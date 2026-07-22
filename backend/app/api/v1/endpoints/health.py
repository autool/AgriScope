"""应用与数据库健康检查端点。"""

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DatabaseSession

router = APIRouter(tags=["健康检查"])


@router.get("/health", summary="检查应用和数据库连接状态")
async def health_check(db: DatabaseSession) -> dict[str, str]:
    """执行轻量 SQL 检查数据库连通性。

    Args:
        db: FastAPI 注入的异步数据库会话。

    Returns:
        dict[str, str]: 应用及数据库健康状态。
    """
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
