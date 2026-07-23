"""多源数据目录、生产批次与县区作业包端点。"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.api.deps import DatabaseSession
from app.core.exceptions import ValidationException
from app.schemas.production import (
    DatasetAssetBatchCreateRequest,
    DatasetAssetBatchResponse,
    DatasetAssetCreateRequest,
    DatasetAssetResponse,
    DatasetAssetUploadRequest,
    DatasetAssetVerificationResponse,
    DatasetAssetVerifyRequest,
    ProductionBatchCreateRequest,
    ProductionBatchResponse,
    ProductionBatchStatusUpdateRequest,
    ProductionOverviewResponse,
    WorkPackageCreateRequest,
    WorkPackageCreateResponse,
    WorkPackageResponse,
    WorkPackageUpdateRequest,
)
from app.services.dataset_asset_batch_service import (
    DatasetAssetBatchService,
    DatasetAssetBatchUploadFile,
)
from app.services.dataset_asset_service import DatasetAssetService
from app.services.production_service import ProductionService

router = APIRouter(prefix="/api/v1/production", tags=["遥感生产调度"])
service = ProductionService()
dataset_asset_service = DatasetAssetService()
dataset_asset_batch_service = DatasetAssetBatchService(
    asset_service=dataset_asset_service,
)


@router.get("/overview", response_model=ProductionOverviewResponse)
async def get_production_overview(
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ProductionOverviewResponse:
    """查询多源数据目录、生产批次和县区作业包。

    Args:
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ProductionOverviewResponse: 生产调度实时聚合结果。
    """
    return await service.get_overview(db, project_code, task_code)


@router.post(
    "/dataset-assets",
    response_model=DatasetAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_dataset_asset(
    request: DatasetAssetCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DatasetAssetResponse:
    """登记多源数据来源、版本、校验值、密级和派生血缘。

    Args:
        request: 资产来源证据和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        DatasetAssetResponse: 已登记、待实体核验的数据资产。
    """
    return await service.register_asset(db, project_code, task_code, request)


@router.post(
    "/dataset-assets/upload",
    response_model=DatasetAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset_asset(
    file: Annotated[UploadFile, File(description="多源数据资产实体文件")],
    metadata_json: Annotated[str, Form(min_length=1)],
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DatasetAssetResponse:
    """上传实体并由服务端计算 SHA-256 后登记为已核验资产。

    Args:
        file: 与资产类型匹配的物理实体文件。
        metadata_json: 来源、范围、密级、血缘和核验依据 JSON。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        DatasetAssetResponse: 已完成实体核验的数据资产。
    """
    try:
        request = DatasetAssetUploadRequest.model_validate_json(metadata_json)
    except ValidationError as exc:
        raise ValidationException("数据资产上传清单格式不合法") from exc
    try:
        return await dataset_asset_service.register_uploaded_asset(
            db,
            project_code,
            task_code,
            request,
            file.filename or "dataset.bin",
            file.content_type,
            file.file,
        )
    finally:
        await file.close()


@router.post(
    "/dataset-assets/batch",
    response_model=DatasetAssetBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset_asset_batch(
    files: Annotated[
        list[UploadFile],
        File(description="1–20 个多源数据资产实体文件"),
    ],
    manifest_json: Annotated[str, Form(min_length=1)],
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DatasetAssetBatchResponse:
    """按逐文件清单原子导入 1–20 个多源数据实体。

    Args:
        files: 批次内全部物理文件。
        manifest_json: 批次编号、逐文件元数据、操作人和依据 JSON。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        DatasetAssetBatchResponse: 批次摘要和全部已核验资产。
    """
    try:
        request = DatasetAssetBatchCreateRequest.model_validate_json(
            manifest_json
        )
    except ValidationError as exc:
        raise ValidationException("数据资产批量入库清单格式不合法") from exc
    try:
        return await dataset_asset_batch_service.upload_assets_batch(
            db,
            project_code,
            task_code,
            request,
            [
                DatasetAssetBatchUploadFile(
                    filename=file.filename or "dataset.bin",
                    file_handle=file.file,
                    reported_media_type=file.content_type,
                )
                for file in files
            ],
        )
    finally:
        for file in files:
            await file.close()


@router.post(
    "/dataset-assets/{asset_code}/verify",
    response_model=DatasetAssetVerificationResponse,
)
async def verify_dataset_asset(
    asset_code: str,
    file: Annotated[UploadFile, File(description="待补传核验的数据资产实体")],
    operator_code: Annotated[str, Form(min_length=1, max_length=50)],
    verification_comment: Annotated[str, Form(min_length=10, max_length=500)],
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DatasetAssetVerificationResponse:
    """为待核验或核验不通过的目录资产补传物理实体。

    Args:
        asset_code: 数据资产编号。
        file: 待检查物理实体。
        operator_code: 当前项目用户稳定编码。
        verification_comment: 人工核验依据。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        DatasetAssetVerificationResponse: 通过或拒绝的不可变核验结果。
    """
    request = DatasetAssetVerifyRequest(
        operator_code=operator_code,
        verification_comment=verification_comment,
    )
    try:
        return await dataset_asset_service.verify_existing_asset(
            db,
            project_code,
            task_code,
            asset_code,
            request,
            file.filename or "dataset.bin",
            file.content_type,
            file.file,
        )
    finally:
        await file.close()


@router.get(
    "/dataset-assets/{asset_code}/download",
    response_class=FileResponse,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def download_dataset_asset(
    asset_code: str,
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> FileResponse:
    """重新校验受控实体后下载多源数据资产。

    Args:
        asset_code: 数据资产编号。
        db: FastAPI 注入的异步数据库会话。
        operator_code: 当前项目用户稳定编码。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        FileResponse: 带内容校验 ETag 的实体下载响应。
    """
    download = await dataset_asset_service.get_download(
        db,
        project_code,
        task_code,
        asset_code,
        operator_code,
    )
    return FileResponse(
        download.path,
        media_type=download.media_type,
        headers={
            "ETag": f'"{download.checksum_sha256}"',
            "Content-Disposition": (
                "attachment; filename*=UTF-8''" + quote(download.filename)
            ),
        },
    )


@router.post(
    "/batches",
    response_model=ProductionBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_production_batch(
    request: ProductionBatchCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ProductionBatchResponse:
    """按当前规则版本创建生产批次。

    Args:
        request: 批次编号、时相资产和计划周期。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ProductionBatchResponse: 新建生产批次。
    """
    return await service.create_batch(db, project_code, task_code, request)


@router.post(
    "/batches/{batch_code}/work-packages",
    response_model=WorkPackageCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_work_packages(
    batch_code: str,
    request: WorkPackageCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> WorkPackageCreateResponse:
    """按真实县区创建作业包并显式关联任务图斑。

    Args:
        batch_code: 生产批次编号。
        request: 县区、负责人、期限和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        WorkPackageCreateResponse: 创建数量和显式分配图斑统计。
    """
    return await service.create_work_packages(
        db,
        project_code,
        task_code,
        batch_code,
        request,
    )


@router.patch(
    "/batches/{batch_code}/status",
    response_model=ProductionBatchResponse,
)
async def update_production_batch_status(
    batch_code: str,
    request: ProductionBatchStatusUpdateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ProductionBatchResponse:
    """按状态机流转生产批次。

    Args:
        batch_code: 生产批次编号。
        request: 目标状态和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ProductionBatchResponse: 更新后的批次。
    """
    return await service.update_batch_status(
        db,
        project_code,
        task_code,
        batch_code,
        request,
    )


@router.patch(
    "/work-packages/{package_code}",
    response_model=WorkPackageResponse,
)
async def update_work_package(
    package_code: str,
    request: WorkPackageUpdateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> WorkPackageResponse:
    """更新作业包负责人、期限和生产状态。

    Args:
        package_code: 作业包编号。
        request: 待修改字段和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        WorkPackageResponse: 更新后的作业包实时进度。
    """
    return await service.update_work_package(
        db,
        project_code,
        task_code,
        package_code,
        request,
    )
