"""源栅格离线介质容量预估、生成和逐卷下载端点。"""

from typing import Annotated

from fastapi import APIRouter, Path, Query
from fastapi.responses import FileResponse

from app.api.deps import DatabaseSession
from app.schemas.offline_archive import (
    OfflineArchiveGenerateRequest,
    OfflineArchiveOverviewResponse,
    OfflineArchiveResponse,
)
from app.services.offline_archive_service import OfflineArchiveService

router = APIRouter(prefix="/api/v1/offline-archives", tags=["源栅格离线封存"])
service = OfflineArchiveService()


@router.get("", response_model=OfflineArchiveOverviewResponse)
async def get_offline_archive_overview(
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> OfflineArchiveOverviewResponse:
    """查询真实来源容量、生成门禁和离线封存版本历史。

    Args:
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        OfflineArchiveOverviewResponse: 容量预估和版本分卷列表。
    """
    return await service.get_overview(db, task_code)


@router.post("/generate", response_model=OfflineArchiveResponse)
async def generate_offline_archive(
    request: OfflineArchiveGenerateRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> OfflineArchiveResponse:
    """生成当前成果包及全部受控大栅格的 ZIP64 分卷封存。

    Args:
        request: 容量、名称、稳定操作人和生成依据。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        OfflineArchiveResponse: 新封存版本和分卷证据。
    """
    return await service.generate_archive(db, task_code, request)


@router.get("/{archive_code}/manifest", response_class=FileResponse)
async def download_offline_archive_manifest(
    archive_code: Annotated[str, Path(min_length=1, max_length=100)],
    db: DatabaseSession,
    requester_code: Annotated[str, Query(min_length=1, max_length=50)],
) -> FileResponse:
    """下载通过当前性和实体复核的顶层规范清单。

    Args:
        archive_code: 离线封存编号。
        db: FastAPI 注入的异步数据库会话。
        requester_code: 当前项目用户稳定编码。

    Returns:
        FileResponse: 规范 JSON 清单。
    """
    download = await service.get_manifest_for_download(
        db,
        archive_code,
        requester_code,
    )
    return FileResponse(
        path=download.path,
        filename=download.filename,
        media_type=download.media_type,
    )


@router.get(
    "/{archive_code}/volumes/{sequence}/download",
    response_class=FileResponse,
)
async def download_offline_archive_volume(
    archive_code: Annotated[str, Path(min_length=1, max_length=100)],
    sequence: Annotated[int, Path(ge=1, le=9999)],
    db: DatabaseSession,
    requester_code: Annotated[str, Query(min_length=1, max_length=50)],
) -> FileResponse:
    """逐成员复核后下载一个可独立解压的 ZIP64 分卷。

    Args:
        archive_code: 离线封存编号。
        sequence: 分卷序号。
        db: FastAPI 注入的异步数据库会话。
        requester_code: 当前项目用户稳定编码。

    Returns:
        FileResponse: 已通过完整性复核的 ZIP64 分卷。
    """
    download = await service.get_volume_for_download(
        db,
        archive_code,
        sequence,
        requester_code,
    )
    return FileResponse(
        path=download.path,
        filename=download.filename,
        media_type=download.media_type,
    )
