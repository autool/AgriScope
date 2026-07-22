"""双景影像自动配准、残差验收和成果下载端点。"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import DatabaseSession
from app.schemas.imagery_registration import (
    ImageryRegistrationCreateRequest,
    ImageryRegistrationJobResponse,
    ImageryRegistrationOverviewResponse,
)
from app.services.imagery_registration_service import ImageryRegistrationService

router = APIRouter(prefix="/api/v1/imagery-registrations", tags=["影像自动配准"])
service = ImageryRegistrationService()


@router.get("/overview", response_model=ImageryRegistrationOverviewResponse)
async def get_imagery_registration_overview(
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ImageryRegistrationOverviewResponse:
    """查询已校验配准来源、项目精度规则和历史成果。

    Args:
        db: 异步数据库会话。
        operator_code: 当前稳定用户编码。
        project_code: 项目编号。

    Returns:
        ImageryRegistrationOverviewResponse: 配准生产总览。
    """
    return await service.get_overview(db, project_code, operator_code)


@router.post("/jobs", response_model=ImageryRegistrationJobResponse)
async def create_imagery_registration_job(
    request: ImageryRegistrationCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[
        str, Query(min_length=1, max_length=50)
    ] = "RS-2026-045",
) -> ImageryRegistrationJobResponse:
    """执行相位相关平移配准并按项目规则验收残差。

    Args:
        request: 双景来源、配准波段、算法和残差门槛。
        db: 异步数据库会话。
        project_code: 项目编号。
        task_code: 当前作业任务编号。

    Returns:
        ImageryRegistrationJobResponse: 通过残差门禁的实体成果。
    """
    return await service.create_job(db, project_code, task_code, request)


@router.get(
    "/jobs/{job_code}/download",
    response_class=FileResponse,
    responses={200: {"content": {"image/tiff": {}}}},
)
async def download_imagery_registration_job(
    job_code: str,
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> FileResponse:
    """重新校验配准实体大小和 SHA-256 后下载。

    Args:
        job_code: 配准任务编号。
        db: 异步数据库会话。
        operator_code: 当前稳定用户编码。
        project_code: 项目编号。

    Returns:
        FileResponse: 校验通过的 GeoTIFF。
    """
    download = await service.get_download(
        db,
        project_code,
        job_code,
        operator_code,
    )
    return FileResponse(
        download.path,
        media_type="image/tiff",
        headers={
            "ETag": f'"{download.checksum_sha256}"',
            "Content-Disposition": (
                "attachment; filename*=UTF-8''" f"{quote(download.filename)}"
            ),
        },
    )
