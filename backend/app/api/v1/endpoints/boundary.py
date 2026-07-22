"""行政区划边界专题图层端点。"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DatabaseSession
from app.schemas.boundary import BoundaryFeatureCollectionResponse
from app.services.boundary_service import BoundaryService

router = APIRouter(prefix="/api/v1/boundaries", tags=["行政区划边界"])
service = BoundaryService()


@router.get("", response_model=BoundaryFeatureCollectionResponse)
async def get_administrative_boundaries(
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> BoundaryFeatureCollectionResponse:
    """查询项目行政区划边界 GeoJSON。

    Args:
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。

    Returns:
        BoundaryFeatureCollectionResponse: 行政区划边界专题图层。
    """
    return await service.get_boundaries(db, project_code)
