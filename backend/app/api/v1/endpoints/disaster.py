"""灾害斑块监测与受灾范围评估端点。"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DatabaseSession
from app.schemas.disaster import (
    DisasterGeoJsonImportRequest,
    DisasterGeoJsonImportResponse,
    DisasterPatchResponse,
    DisasterPatchUpdateRequest,
    DisasterSummaryResponse,
)
from app.services.disaster_service import DisasterService

router = APIRouter(prefix="/api/v1/disasters", tags=["灾害斑块监测"])
service = DisasterService()


@router.post("/import-geojson", response_model=DisasterGeoJsonImportResponse)
async def import_disaster_geojson(
    request: DisasterGeoJsonImportRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DisasterGeoJsonImportResponse:
    """导入外部灾害模型 GeoJSON FeatureCollection。

    Args:
        request: 灾害斑块、来源元数据、冲突策略和操作人编码。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        DisasterGeoJsonImportResponse: 导入批次、数量和来源校验摘要。
    """
    return await service.import_geojson(db, task_code, request)


@router.get("/summary", response_model=DisasterSummaryResponse)
async def get_disaster_summary(
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DisasterSummaryResponse:
    """查询灾害斑块、受灾面积和专题图层。

    Args:
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        DisasterSummaryResponse: 灾害评估汇总。
    """
    return await service.get_summary(db, task_code)


@router.patch("/{patch_code}", response_model=DisasterPatchResponse)
async def update_disaster_patch(
    patch_code: str,
    request: DisasterPatchUpdateRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DisasterPatchResponse:
    """人工修正灾害等级和确认状态。

    Args:
        patch_code: 灾害斑块编号。
        request: 修正内容和审核信息。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        DisasterPatchResponse: 修正后的灾害斑块。
    """
    return await service.update_patch(db, task_code, patch_code, request)
