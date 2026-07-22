"""多光谱与全色影像融合生产端点。"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import DatabaseSession
from app.schemas.imagery_fusion import (
    ImageryFusionCreateRequest,
    ImageryFusionJobResponse,
    ImageryFusionOverviewResponse,
)
from app.services.imagery_fusion_service import ImageryFusionService

router = APIRouter(prefix="/api/v1/imagery-fusions", tags=["全色影像融合"])
service = ImageryFusionService()


@router.get("/overview", response_model=ImageryFusionOverviewResponse)
async def get_imagery_fusion_overview(
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ImageryFusionOverviewResponse:
    """查询融合来源资格、输出像元上限和历史成果。

    Args:
        db: 异步数据库会话。
        operator_code: 当前稳定用户编码。
        project_code: 项目编号。

    Returns:
        ImageryFusionOverviewResponse: 融合生产总览。
    """
    return await service.get_overview(db, project_code, operator_code)


@router.post("/jobs", response_model=ImageryFusionJobResponse)
async def create_imagery_fusion_job(
    request: ImageryFusionCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ImageryFusionJobResponse:
    """执行全色融合并按实体质量指标验收。

    Args:
        request: 多光谱、全色、波段和质量参数。
        db: 异步数据库会话。
        project_code: 项目编号。
        task_code: 当前任务编号。

    Returns:
        ImageryFusionJobResponse: 通过门禁的实体融合成果。
    """
    return await service.create_job(db, project_code, task_code, request)


@router.get(
    "/jobs/{job_code}/download",
    response_class=FileResponse,
    responses={200: {"content": {"image/tiff": {}}}},
)
async def download_imagery_fusion_job(
    job_code: str,
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> FileResponse:
    """重新校验融合成果并下载 GeoTIFF。

    Args:
        job_code: 融合任务编号。
        db: 异步数据库会话。
        operator_code: 下载人稳定编码。
        project_code: 项目编号。

    Returns:
        FileResponse: 带 SHA-256 ETag 的 GeoTIFF。
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
