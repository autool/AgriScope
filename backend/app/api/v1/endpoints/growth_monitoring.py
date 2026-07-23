"""多时相 NDVI 作物长势监测端点。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import DatabaseSession
from app.schemas.growth_monitoring import (
    GrowthMonitoringCreateRequest,
    GrowthMonitoringOverviewResponse,
    GrowthMonitoringRunResponse,
    GrowthMonitoringZoneCollectionResponse,
)
from app.services.growth_monitoring_service import GrowthMonitoringService

router = APIRouter(
    prefix="/api/v1/growth-monitoring",
    tags=["多时相 NDVI 长势监测"],
)
service = GrowthMonitoringService()


@router.get("/overview", response_model=GrowthMonitoringOverviewResponse)
async def get_growth_monitoring_overview(
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
    selected_run_code: Annotated[
        str | None,
        Query(min_length=1, max_length=80),
    ] = None,
) -> GrowthMonitoringOverviewResponse:
    """查询可用 NDVI 来源、历史任务和异常区。

    Args:
        db: FastAPI 注入的异步数据库会话。
        operator_code: 当前稳定项目用户编码。
        project_code: 项目编号。
        task_code: 作业任务编号。
        selected_run_code: 可选历史任务编号。

    Returns:
        GrowthMonitoringOverviewResponse: 长势监测总览。
    """
    return await service.get_overview(
        db,
        project_code,
        task_code,
        operator_code,
        selected_run_code,
    )


@router.post("/runs", response_model=GrowthMonitoringRunResponse)
async def create_growth_monitoring_run(
    request: GrowthMonitoringCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> GrowthMonitoringRunResponse:
    """执行一次真实多时相 NDVI 长势监测。

    Args:
        request: 两期影像、阈值、面积门槛和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        GrowthMonitoringRunResponse: 已完成长势任务和成果证据。
    """
    return await service.create_run(db, project_code, task_code, request)


@router.get(
    "/runs/{run_code}/zones",
    response_model=GrowthMonitoringZoneCollectionResponse,
)
async def get_growth_monitoring_zones(
    run_code: str,
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> GrowthMonitoringZoneCollectionResponse:
    """查询指定长势监测任务的异常区 GeoJSON。

    Args:
        run_code: 长势监测任务编号。
        db: FastAPI 注入的异步数据库会话。
        operator_code: 当前稳定项目用户编码。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        GrowthMonitoringZoneCollectionResponse: 异常区集合。
    """
    return await service.get_zones(
        db,
        project_code,
        task_code,
        run_code,
        operator_code,
    )


@router.get("/runs/{run_code}/download", response_class=FileResponse)
async def download_growth_monitoring_artifact(
    run_code: str,
    db: DatabaseSession,
    artifact: Annotated[Literal["classification", "anomalies"], Query()],
    requester_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> FileResponse:
    """鉴权并重新校验后下载长势分级或异常区实体。

    Args:
        run_code: 长势监测任务编号。
        db: FastAPI 注入的异步数据库会话。
        artifact: classification 或 anomalies。
        requester_code: 下载人稳定项目用户编码。
        project_code: 项目编号。

    Returns:
        FileResponse: 已通过大小和 SHA-256 校验的成果文件。
    """
    download = await service.get_download(
        db,
        project_code,
        run_code,
        artifact,
        requester_code,
    )
    return FileResponse(
        path=download.path,
        media_type=download.media_type,
        filename=download.filename,
        headers={"ETag": f'"{download.checksum_sha256}"'},
    )
