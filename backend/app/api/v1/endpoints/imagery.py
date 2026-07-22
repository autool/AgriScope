"""遥感影像资产与预处理流水线端点。"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import DatabaseSession
from app.schemas.imagery import (
    ImageryAssetCreateRequest,
    ImageryAssetListResponse,
    ImageryAssetResponse,
    ImageryProcessingResponse,
    ImageryQuicklookResponse,
    ImagerySourceLevelAcceptRequest,
    ImageryStepExecuteRequest,
    ImageryStepRunRequest,
)
from app.services.imagery_asset_service import ImageryAssetService
from app.services.imagery_quicklook_service import ImageryQuicklookService
from app.services.imagery_service import ImageryService

router = APIRouter(prefix="/api/v1/imagery-assets", tags=["遥感影像预处理"])
service = ImageryService()
asset_service = ImageryAssetService()
quicklook_service = ImageryQuicklookService()


@router.get("", response_model=ImageryAssetListResponse)
async def list_imagery_assets(
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ImageryAssetListResponse:
    """查询项目影像资产目录和实体文件状态。

    Args:
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。

    Returns:
        ImageryAssetListResponse: 项目影像资产目录。
    """
    return await asset_service.list_assets(db, project_code)


@router.post(
    "",
    response_model=ImageryAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_imagery_asset(
    db: DatabaseSession,
    file: Annotated[UploadFile, File(description="GeoTIFF、IMG 或 HDF 文件")],
    asset_code: Annotated[
        str,
        Form(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$"),
    ],
    asset_name: Annotated[str, Form(min_length=1, max_length=200)],
    operator_code: Annotated[str, Form(min_length=1, max_length=50)],
    sensor_type: Annotated[str | None, Form(max_length=80)] = None,
    acquired_at: Annotated[datetime | None, Form()] = None,
    cloud_cover: Annotated[float | None, Form(ge=0, le=100)] = None,
    processing_level: Annotated[str | None, Form(max_length=30)] = None,
    data_status: Annotated[Literal["operational", "demo"], Form()] = "operational",
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ImageryAssetResponse:
    """上传真实影像文件，自动读取栅格和空间元数据后入库。

    Args:
        db: FastAPI 注入的异步数据库会话。
        file: 遥感影像文件。
        asset_code: 影像资产编号。
        asset_name: 影像资产名称。
        sensor_type: 文件标签缺失时的传感器补录值。
        acquired_at: 文件标签缺失或仅含日期时的带时区补录值。
        operator_code: 入库操作人稳定编码。
        cloud_cover: 云量百分比。
        processing_level: 处理级别。
        data_status: 业务数据或明确演示数据标识。
        project_code: 项目编号。
        task_code: 审计所属任务编号。

    Returns:
        ImageryAssetResponse: 已入库真实影像资产。
    """
    request = ImageryAssetCreateRequest(
        asset_code=asset_code,
        asset_name=asset_name,
        sensor_type=sensor_type,
        acquired_at=acquired_at,
        cloud_cover=cloud_cover,
        processing_level=processing_level,
        data_status=data_status,
        operator_code=operator_code,
    )
    try:
        return await asset_service.upload_asset(
            db,
            project_code,
            task_code,
            request,
            file.filename or "imagery.tif",
            file.file,
        )
    finally:
        await file.close()


@router.get("/{asset_code}/processing", response_model=ImageryProcessingResponse)
async def get_imagery_processing(
    asset_code: str,
    db: DatabaseSession,
) -> ImageryProcessingResponse:
    """查询影像元数据和预处理流水线状态。

    Args:
        asset_code: 影像资产编号。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        ImageryProcessingResponse: 影像处理聚合信息。
    """
    return await service.get_processing(db, asset_code)


@router.get("/{asset_code}/quicklooks", response_model=ImageryQuicklookResponse)
async def get_imagery_quicklooks(
    asset_code: str,
    db: DatabaseSession,
) -> ImageryQuicklookResponse:
    """从当前实体源影像和已校验波段产物生成真实快视图。

    Args:
        asset_code: 影像资产编号。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        ImageryQuicklookResponse: 不参与处理完成度计算的快视图证据。
    """
    return await quicklook_service.get_quicklooks(db, asset_code)


@router.get(
    "/{asset_code}/quicklooks/{product_code}.png",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
async def get_imagery_quicklook_image(
    asset_code: str,
    product_code: Literal["source", "true_color", "false_color", "ndvi"],
    db: DatabaseSession,
) -> Response:
    """读取经来源和 PNG 双重 SHA256 校验的快视图。

    Args:
        asset_code: 影像资产编号。
        product_code: 源影像、真彩色、假彩色或 NDVI。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        Response: 带 ETag 的 RGBA PNG。
    """
    content, etag = await quicklook_service.get_image(
        db,
        asset_code,
        product_code,
    )
    return Response(
        content=content,
        media_type="image/png",
        headers={
            "ETag": f'"{etag}"',
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/{asset_code}/processing/{step_code}/run",
    response_model=ImageryProcessingResponse,
)
async def run_imagery_processing_step(
    asset_code: str,
    step_code: str,
    request: ImageryStepRunRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ImageryProcessingResponse:
    """校验并登记指定影像预处理步骤的实体产物。

    Args:
        asset_code: 影像资产编号。
        step_code: 处理步骤编号。
        request: 操作人和说明。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        ImageryProcessingResponse: 更新后的处理流水线。
    """
    return await service.run_step(db, asset_code, step_code, task_code, request)


@router.post(
    "/{asset_code}/processing/{step_code}/execute",
    response_model=ImageryProcessingResponse,
)
async def execute_imagery_processing_step(
    asset_code: str,
    step_code: str,
    request: ImageryStepExecuteRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ImageryProcessingResponse:
    """使用平台内置 Rasterio 处理器执行指定步骤。

    Args:
        asset_code: 影像资产编号。
        step_code: 处理步骤编号。
        request: 项目用户编码、处理参数和说明。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        ImageryProcessingResponse: 执行后的处理流水线。
    """
    return await service.execute_step(
        db,
        asset_code,
        step_code,
        task_code,
        request,
    )


@router.post(
    "/{asset_code}/processing/{step_code}/accept-source",
    response_model=ImageryProcessingResponse,
)
async def accept_imagery_source_level_step(
    asset_code: str,
    step_code: str,
    request: ImagerySourceLevelAcceptRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ImageryProcessingResponse:
    """以实体源产品级别证据满足定标或大气校正步骤。

    Args:
        asset_code: 影像资产编号。
        step_code: 辐射定标或大气校正步骤编码。
        request: 操作人、预期产品级别、无算法确认和承认依据。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        ImageryProcessingResponse: 承认后的完整流水线状态。
    """
    return await service.accept_source_level_step(
        db,
        asset_code,
        step_code,
        task_code,
        request,
    )
