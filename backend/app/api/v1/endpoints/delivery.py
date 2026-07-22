"""成果交付包生成、清单与下载端点。"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import DatabaseSession
from app.schemas.delivery import (
    DeliveryGenerateRequest,
    DeliveryListResponse,
    DeliveryPackageResponse,
)
from app.services.delivery_service import DeliveryService

router = APIRouter(prefix="/api/v1/deliveries", tags=["成果验收交付"])
service = DeliveryService()


@router.get("", response_model=DeliveryListResponse)
async def list_delivery_packages(
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DeliveryListResponse:
    """查询任务交付条件和历史成果包。

    Args:
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        DeliveryListResponse: 交付包列表和生成条件。
    """
    return await service.list_packages(db, task_code)


@router.post("/generate", response_model=DeliveryPackageResponse)
async def generate_delivery_package(
    request: DeliveryGenerateRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DeliveryPackageResponse:
    """生成完整成果 ZIP 交付包。

    Args:
        request: 操作人和成果包名称。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        DeliveryPackageResponse: 已生成成果包。
    """
    return await service.generate_package(db, task_code, request)


@router.get("/{package_code}/download", response_class=FileResponse)
async def download_delivery_package(
    package_code: str,
    db: DatabaseSession,
    user_code: Annotated[str, Query(min_length=1, max_length=50)],
) -> FileResponse:
    """下载已完成的成果 ZIP 包。

    Args:
        package_code: 成果包编号。
        db: FastAPI 注入的异步数据库会话。
        user_code: 当前项目用户稳定编码。

    Returns:
        FileResponse: ZIP 文件下载响应。
    """
    package = await service.get_package_for_download(db, package_code, user_code)
    return FileResponse(
        path=Path(package.file_uri),
        filename=f"{package.package_code}.zip",
        media_type="application/zip",
    )
