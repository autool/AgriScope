"""任务作用域多格式矢量成果导出端点。"""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import DatabaseSession
from app.schemas.vector_export import (
    VectorExportGenerateRequest,
    VectorExportListResponse,
    VectorExportOptionsResponse,
    VectorExportPackageResponse,
)
from app.services.vector_export_service import VectorExportService

router = APIRouter(prefix="/api/v1/vector-exports", tags=["矢量成果导出"])
service = VectorExportService()


@router.get("", response_model=VectorExportListResponse)
async def list_vector_exports(
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> VectorExportListResponse:
    """查询当前任务矢量成果导出历史。

    Args:
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        VectorExportListResponse: 当前与历史导出版本。
    """
    return await service.list_packages(db, task_code)


@router.get("/options", response_model=VectorExportOptionsResponse)
async def get_vector_export_options(
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> VectorExportOptionsResponse:
    """查询真实县区、地类和支持格式。

    Args:
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        VectorExportOptionsResponse: 真实筛选范围和数量上限。
    """
    return await service.get_options(db, task_code)


@router.post("/generate", response_model=VectorExportPackageResponse)
async def generate_vector_export(
    request: VectorExportGenerateRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> VectorExportPackageResponse:
    """生成真实 GeoJSON、Shapefile、KML 和 FileGDB 成果 ZIP。

    Args:
        request: 格式、筛选、标题、用户和生成依据。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        VectorExportPackageResponse: 新生成导出包。
    """
    return await service.generate_package(db, task_code, request)


@router.get("/{export_code}/download", response_class=FileResponse)
async def download_vector_export(
    export_code: str,
    db: DatabaseSession,
    requester_code: Annotated[str, Query(min_length=1, max_length=50)],
) -> FileResponse:
    """鉴权并完整复核后下载矢量成果 ZIP。

    Args:
        export_code: 导出包业务编号。
        db: FastAPI 注入的异步数据库会话。
        requester_code: 下载人稳定项目用户编码。

    Returns:
        FileResponse: 通过格式、大小和 SHA-256 校验的 ZIP。
    """
    download = await service.authorize_download(
        db,
        export_code,
        requester_code,
    )
    return FileResponse(
        path=download.path,
        filename=download.filename,
        media_type="application/zip",
        headers={"ETag": f'"{download.checksum_sha256}"'},
    )
