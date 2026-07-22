"""多景影像匀色、镶嵌、覆盖验收和成果下载端点。"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import DatabaseSession
from app.schemas.imagery_mosaic import (
    ImageryMosaicCreateRequest,
    ImageryMosaicJobResponse,
    ImageryMosaicOverviewResponse,
)
from app.services.imagery_mosaic_service import ImageryMosaicService

router = APIRouter(prefix="/api/v1/imagery-mosaics", tags=["多景影像镶嵌"])
service = ImageryMosaicService()


@router.get("/overview", response_model=ImageryMosaicOverviewResponse)
async def get_imagery_mosaic_overview(
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ImageryMosaicOverviewResponse:
    """查询已校验输入来源和历史镶嵌成果。

    Args:
        db: 异步数据库会话。
        operator_code: 当前稳定用户编码。
        project_code: 项目编号。

    Returns:
        ImageryMosaicOverviewResponse: 镶嵌生产总览。
    """
    return await service.get_overview(db, project_code, operator_code)


@router.post("/jobs", response_model=ImageryMosaicJobResponse)
async def create_imagery_mosaic_job(
    request: ImageryMosaicCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[
        str, Query(min_length=1, max_length=50)
    ] = "RS-2026-045",
) -> ImageryMosaicJobResponse:
    """执行多景匀色、镶嵌和行政区覆盖率验收。

    Args:
        request: 镶嵌来源、目标网格、算法和验收门槛。
        db: 异步数据库会话。
        project_code: 项目编号。
        task_code: 当前作业任务编号。

    Returns:
        ImageryMosaicJobResponse: 通过覆盖门禁的实体成果。
    """
    return await service.create_job(db, project_code, task_code, request)


@router.get(
    "/jobs/{job_code}/download",
    response_class=FileResponse,
    responses={200: {"content": {"image/tiff": {}}}},
)
async def download_imagery_mosaic(
    job_code: str,
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> FileResponse:
    """复核镶嵌成果大小和 SHA-256 后下载。

    Args:
        job_code: 镶嵌任务编号。
        db: 异步数据库会话。
        operator_code: 当前稳定用户编码。
        project_code: 项目编号。

    Returns:
        FileResponse: 校验通过的 GeoTIFF。
    """
    download = await service.get_download(
        db, project_code, job_code, operator_code
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
