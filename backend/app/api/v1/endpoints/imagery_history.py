"""历史影像覆盖矩阵与问题追溯端点。"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DatabaseSession
from app.schemas.imagery_history import ImageryHistoryOverviewResponse
from app.services.imagery_history_service import ImageryHistoryService

router = APIRouter(prefix="/api/v1/imagery-history", tags=["历史影像覆盖与追溯"])
service = ImageryHistoryService()


@router.get("/overview", response_model=ImageryHistoryOverviewResponse)
async def get_imagery_history_overview(
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ImageryHistoryOverviewResponse:
    """查询真实行政区覆盖矩阵和影像处理证据时间线。

    Args:
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        ImageryHistoryOverviewResponse: 历史时相、县区覆盖和问题事件。
    """
    return await service.get_overview(db, project_code)
